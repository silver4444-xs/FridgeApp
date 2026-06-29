/**
 * FridgeAI 集中式数据 Store
 */

import { reactive, computed } from 'vue'
import { ONENET_CONFIG } from '@/config/onenet.js'
import { getIngredientImage } from '@/utils/imageResolver.js'

const CN_CAT_MAP = {
	'水果': 'fruit', '蔬菜': 'vegetable', '肉蛋生鲜': 'meat_egg', '肉蛋生鲜类': 'meat_egg',
	'肉类': 'meat_egg', '鸡蛋': 'meat_egg', '海鲜': 'meat_egg',
	'饮料': 'beverage_dairy', '乳品': 'beverage_dairy', '饮料乳品': 'beverage_dairy', '饮料乳品类': 'beverage_dairy',
	'包装食品': 'packaged', '包装食品类': 'packaged', '零食': 'packaged',
}

export const store = reactive({
	_foods: [],
	_nextId: 1,

	deviceStatus: {
		temperature: null, freezerTemp: null, humidity: null, doorStatus: null, power: null, updatedAt: null,
	},

	backendWsConnected: false,
	cloudConnected: false,
	cloudError: '',
	cloudProductId: ONENET_CONFIG.productId,
	cloudDeviceName: ONENET_CONFIG.deviceName,
	cloudLastSync: null,

	settings: { autoSync: true },

	get foods() {
		const seen = new Map(), merged = []
		for (const f of this._foods) {
			const key = f.name + '|' + f.cat
			if (seen.has(key)) { seen.get(key).qty += f.qty }
			else { const copy = { ...f }; seen.set(key, copy); merged.push(copy) }
		}
		return merged
	},

	get totalCount() { return this.foods.reduce((s, f) => s + f.qty, 0) },

	// Fix #18: WS 未连接时从 localStorage 加载缓存作为离线回退
	// 原有逻辑: init() 不加载本地缓存 → WS 连接失败时用户看到空冰箱
	// 修复后: 优先等待 WS 数据，但先从 localStorage 加载作为初始显示
	init() {
		try {
			const cached = uni.getStorageSync('fridgeai_foods')
			if (cached && Array.isArray(cached) && cached.length > 0) {
				this._foods = cached
				this._nextId = Math.max(...cached.map(f => f.id || 0), 0) + 1
				this._resolvePhotos()
				this._normalizeCats()
				console.log('[Store] Loaded', cached.length, 'items from localStorage cache')
			}
		} catch (e) {
			console.warn('[Store] localStorage cache unavailable:', e)
		}
		console.log('[Store] Waiting for cloud data via WS...')
	},

	_normalizeCats() {
		for (const f of this._foods) { if (CN_CAT_MAP[f.cat]) f.cat = CN_CAT_MAP[f.cat] }
	},

	_resolvePhotos() {
		this._foods.forEach(f => { const r = getIngredientImage(f.name); if (r) f.photo = r })
	},

	_save() {
		try { uni.setStorageSync('fridgeai_foods', this._foods) }
		catch (e) { console.warn('[Store] 保存本地存储失败:', e) }
	},

	_dedup() {
		const seen = new Map(), keep = []
		for (const f of this._foods) {
			const key = f.name + '|' + f.cat
			if (seen.has(key)) { seen.get(key).qty += f.qty }
			else { seen.set(key, f); keep.push(f) }
		}
		this._foods = keep
	},

	getByCat(cat) {
		if (cat === 'all') return this.foods
		return this.foods.filter((f) => f.cat === cat)
	},

	addFood(item) {
		const info = item._classified || classifyFood(item.name)
		const name = info.zhName
		const cat = item.cat || info.cat
		const exist = this._foods.find((f) => f.name === name && f.cat === cat)
		if (exist) {
			exist.qty += parseFloat(item.qty) || 1
			if (item.unit) exist.unit = item.unit
			exist.fromCloud = item.fromCloud || exist.fromCloud
			this._save()
			return { merged: true, into: exist }
		}
		const food = {
			id: this._nextId++, name, enName: info.enName, cat,
			qty: parseFloat(item.qty) || 1, unit: item.unit || '个',
			calories: info.calories,
			photo: item.photo || getIngredientImage(name) || this._defaultPhoto(),
			fromCloud: item.fromCloud || false,
			addedAt: new Date().toISOString(),
		}
		this._foods.push(food)
		this._save()
		return food
	},

	updateFood(id, updates) {
		const idx = this._foods.findIndex((f) => f.id === id)
		if (idx === -1) return null
		if (updates.qty !== undefined && parseFloat(updates.qty) <= 0) {
			const name = this._foods[idx].name
			this._foods.splice(idx, 1); this._save()
			return { deleted: true, name }
		}
		this._foods.splice(idx, 1, { ...this._foods[idx], ...updates })
		this._save()
		return this._foods[idx]
	},

	removeFood(id) {
		const idx = this._foods.findIndex((f) => f.id === id)
		if (idx === -1) return false
		this._foods.splice(idx, 1); this._save()
		return true
	},

	updateQty(id, qty) {
		const idx = this._foods.findIndex((f) => f.id === id)
		if (idx === -1) return null
		if (qty <= 0) {
			const name = this._foods[idx].name
			this._foods.splice(idx, 1); this._save()
			return { deleted: true, name }
		}
		this._foods.splice(idx, 1, { ...this._foods[idx], qty })
		this._save()
		return { deleted: false }
	},

	updateDeviceStatus(data) {
		if (data.temperature) this.deviceStatus.temperature = data.temperature
		if (data.freezerTemp) this.deviceStatus.freezerTemp = data.freezerTemp
		if (data.humidity) this.deviceStatus.humidity = data.humidity
		if (data.doorStatus !== undefined) this.deviceStatus.doorStatus = data.doorStatus
		if (data.power) this.deviceStatus.power = data.power
		this.deviceStatus.updatedAt = new Date().toISOString()
	},

	mergeCloudFoods(cloudFoods) {
		this._normalizeCats()
		const cloudKeys = new Set()
		const changes = []
		for (const cf of cloudFoods) {
			cf.name = translateFoodName(cf.name)
			cf.cat = classifyFood(cf.name).cat
			const key = cf.name + '|' + cf.cat
			cloudKeys.add(key)
			const exist = this._foods.find((f) => f.name === cf.name && f.cat === cf.cat)
			if (exist) {
				const oldQty = exist.qty
				// Fix #1: 增量合并 — 云端数量不覆盖本地新增
				// 原有逻辑: exist.qty = cf.qty ?? exist.qty  → 本地新增被覆盖
				// 修复后: 仅当云端数量更大时更新；数量减少由 cloudKeys 缺失→删除机制处理
				const cloudQty = cf.qty ?? 0
				if (cloudQty > exist.qty) {
					exist.qty = cloudQty
				}
				if (cf.unit) exist.unit = cf.unit
				exist.fromCloud = true
				const delta = cloudQty - oldQty
				if (delta > 0) changes.push({ type: 'add', name: cf.name, delta, unit: exist.unit })
				else if (delta < 0) changes.push({ type: 'remove', name: cf.name, delta: Math.abs(delta), unit: exist.unit })
			} else {
				this.addFood({ ...cf, fromCloud: true })
				changes.push({ type: 'new', name: cf.name })
			}
		}
		const removed = this._foods.filter(f => f.fromCloud && !cloudKeys.has(f.name + '|' + f.cat))
		for (const r of removed) {
			this._foods.splice(this._foods.indexOf(r), 1)
			changes.push({ type: 'remove', name: r.name, delta: r.qty, unit: r.unit || '个' })
		}
		this._dedup(); this._save(); this._notifyChanges(changes)
	},

	clearAll() { this._foods = []; this._nextId = 1; this._save() },

	
	_notifyChanges(changes) {
		if (changes.length === 0) return
		if (changes.length <= 3) {
			const parts = changes.map(c => {
				const sign = c.type === 'remove' ? '-' : '+'
				const amt = c.type === 'new' ? 1 : (c.delta || 1)
				return c.name + sign + amt + (c.unit || '个')
			})
			uni.showToast({ title: parts.join('  '), icon: 'none', duration: 2500 })
		} else {
			const adds = changes.filter(c => c.type === 'new' || c.type === 'add').length
			const rms = changes.filter(c => c.type === 'remove').length
			let msg = ''
			if (adds) msg += '+' + adds + '样'
			if (adds && rms) msg += '  '
			if (rms) msg += '-' + rms + '样'
			uni.showToast({ title: msg, icon: 'none', duration: 2500 })
		}
	},
	_defaultPhoto() {
		return 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=400&h=300&fit=crop'
	},
})

export const CAT_META = {
	all: { name: '全部', emoji: '📦' },
	fruit: { name: '水果', emoji: '🍎' },
	vegetable: { name: '蔬菜', emoji: '🥬' },
	meat_egg: { name: '肉蛋生鲜类', emoji: '🥩' },
	beverage_dairy: { name: '饮料乳品类', emoji: '🥛' },
	packaged: { name: '包装食品类', emoji: '📦' },
}

// ======== 完整食材映射表 ========

export const EN_TO_ZH = {
	// 水果 Fruit
	apple: '苹果', banana: '香蕉', blueberry: '蓝莓', grape: '葡萄',
	kiwi: '猕猴桃', lemon: '柠檬', lime: '青柠', mango: '芒果',
	orange: '橙子', peach: '桃子', pear: '梨', pineapple: '菠萝',
	strawberry: '草莓', watermelon: '西瓜',
	// 蔬菜 Vegetable
	bell_pepper: '彩椒', cabbage: '卷心菜', carrot: '胡萝卜',
	cauliflower: '花椰菜', chilli_pepper: '辣椒', corn: '玉米',
	cucumber: '黄瓜', eggplant: '茄子', garlic: '大蒜', ginger: '生姜',
	green_beans: '四季豆', leek: '韭菜', lettuce: '生菜',
	mushroom: '蘑菇', onion: '洋葱', potato: '土豆',
	spinach: '菠菜', 'sweet potato': '红薯', sweetpotato: '红薯',
	tomato: '番茄', 'green leaves': '绿叶菜',
	// 饮品 Beverage
	cola: '可乐', drink: '饮料', fanta: '芬达', milk: '牛奶', sprite: '雪碧',
	water: '水', yogurt: '酸奶',
	// 肉蛋生鲜 Meat & Egg
	chicken: '鸡肉', egg: '鸡蛋', meat: '肉类', shrimp: '虾',
	// 烘焙零食 Snack
	bread: '面包', cheese: '奶酪', chocolate: '巧克力',
}

export const EN_TO_CAT = {
	// 水果
	apple: 'fruit', banana: 'fruit', blueberry: 'fruit', grape: 'fruit',
	kiwi: 'fruit', lemon: 'fruit', lime: 'fruit', mango: 'fruit',
	orange: 'fruit', peach: 'fruit', pear: 'fruit', pineapple: 'fruit',
	strawberry: 'fruit', watermelon: 'fruit',
	// 蔬菜
	bell_pepper: 'vegetable', cabbage: 'vegetable', carrot: 'vegetable',
	cauliflower: 'vegetable', chilli_pepper: 'vegetable', corn: 'vegetable',
	cucumber: 'vegetable', eggplant: 'vegetable', garlic: 'vegetable',
	ginger: 'vegetable', green_beans: 'vegetable', leek: 'vegetable',
	lettuce: 'vegetable', mushroom: 'vegetable', onion: 'vegetable',
	potato: 'vegetable', spinach: 'vegetable',
	'sweet potato': 'vegetable', sweetpotato: 'vegetable',
	tomato: 'vegetable', 'green leaves': 'vegetable',
	// 饮品
	cola: 'beverage_dairy', drink: 'beverage_dairy', fanta: 'beverage_dairy',
	milk: 'beverage_dairy', sprite: 'beverage_dairy',
	water: 'beverage_dairy', yogurt: 'beverage_dairy',
	// 肉蛋
	chicken: 'meat_egg', egg: 'meat_egg', meat: 'meat_egg', shrimp: 'meat_egg',
	// 零食
	bread: 'packaged', cheese: 'packaged', chocolate: 'packaged',
}

export const FOOD_CALORIES = {
	// 水果
	apple: 52, banana: 89, blueberry: 57, grape: 69,
	kiwi: 61, lemon: 29, lime: 30, mango: 60,
	orange: 47, peach: 39, pear: 57, pineapple: 50,
	strawberry: 32, watermelon: 30,
	// 蔬菜
	bell_pepper: 20, cabbage: 25, carrot: 41,
	cauliflower: 25, chilli_pepper: 40, corn: 86,
	cucumber: 15, eggplant: 25, garlic: 149, ginger: 80,
	green_beans: 31, leek: 61, lettuce: 15,
	mushroom: 22, onion: 40, potato: 77,
	spinach: 23, 'sweet potato': 86, sweetpotato: 86,
	tomato: 18, 'green leaves': 20,
	// 饮品
	cola: 43, drink: 40, fanta: 48, milk: 70, sprite: 41, water: 0, yogurt: 63,
	// 肉蛋
	chicken: 167, egg: 155, meat: 250, shrimp: 99,
	// 零食
	bread: 265, cheese: 350, chocolate: 546,
}

export function translateFoodName(name) {
	if (!name) return name
	const lower = name.toLowerCase().trim()
	return EN_TO_ZH[lower] || name
}

export const ZH_TO_EN = {}
for (const [en, zh] of Object.entries(EN_TO_ZH)) { ZH_TO_EN[zh] = en }

export function classifyFood(input) {
	const trimmed = (input || '').trim(), lower = trimmed.toLowerCase()
	if (EN_TO_ZH[lower]) return { enName: lower, zhName: EN_TO_ZH[lower], cat: EN_TO_CAT[lower] || 'packaged', calories: FOOD_CALORIES[lower] ?? null }
	const en = ZH_TO_EN[trimmed]
	if (en) return { enName: en, zhName: trimmed, cat: EN_TO_CAT[en] || 'packaged', calories: FOOD_CALORIES[en] ?? null }
	return { enName: lower, zhName: trimmed, cat: 'packaged', calories: null }
}

export const UNIT_OPTIONS = ['颗', 'g', 'kg', '瓶', '根', '盒', '袋', '个', '把', 'L', 'mL']

store.init()
