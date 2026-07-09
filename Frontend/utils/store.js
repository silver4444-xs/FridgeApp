/**
 * FridgeAI 集中式数据 Store
 */

import { reactive, computed } from 'vue'
import { ONENET_CONFIG } from '@/config/onenet.js'
import { getIngredientImage } from '@/utils/imageResolver.js'
import { EN_TO_ZH, EN_TO_CAT, FOOD_CALORIES, ZH_TO_EN, translateFoodName, classifyFood } from './foodData.js'

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

// 食材映射表 → 详见 ./foodData.js (统一来源)
export { EN_TO_ZH, EN_TO_CAT, FOOD_CALORIES, ZH_TO_EN, translateFoodName, classifyFood } from './foodData.js'

export const UNIT_OPTIONS = ['颗', 'g', 'kg', '瓶', '根', '盒', '袋', '个', '把', 'L', 'mL']

store.init()
