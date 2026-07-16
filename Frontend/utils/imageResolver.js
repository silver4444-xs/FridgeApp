/**
 * 图片解析器 — 优先使用本地 static/images 缓存，未命中时回退 Unsplash
 */

import imageMapping from '@/data/image_mapping.json'
import { ZH_TO_EN } from './foodData.js'
import { getStaticUrl } from '@/config/app.js'

const _mapping = imageMapping || { ingredients: {}, recipes: {} }

function getImageBase() {
	return getStaticUrl('')
}

function resolveImagePath(relativePath) {
	if (!relativePath) return null
	if (relativePath.startsWith('http')) return relativePath
	return getImageBase() + relativePath
}

export const FALLBACK_FOOD = 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=400&h=300&fit=crop'
export const FALLBACK_RECIPE = 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=600&h=400&fit=crop'

const DEMO_PHOTOS = {
	// 水果
	'苹果': 'https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?w=400&h=300&fit=crop',
	'香蕉': 'https://images.unsplash.com/photo-1603833665858-e61d17a86224?w=400&h=300&fit=crop',
	'蓝莓': 'https://images.unsplash.com/photo-1498557850523-fd3d118b962e?w=400&h=300&fit=crop',
	'葡萄': 'https://images.unsplash.com/photo-1537640538966-79f369143f8f?w=400&h=300&fit=crop',
	'猕猴桃': 'https://images.unsplash.com/photo-1618897996318-5a901fa6ca71?w=400&h=300&fit=crop',
	'柠檬': 'https://images.unsplash.com/photo-1590502593747-42a996133562?w=400&h=300&fit=crop',
	'芒果': 'https://images.unsplash.com/photo-1605027990121-cbae9e0642df?w=400&h=300&fit=crop',
	'橙子': 'https://images.unsplash.com/photo-1547514701-42782101795e?w=400&h=300&fit=crop',
	'桃子': 'https://images.unsplash.com/photo-1602706760226-857fe39e2bcf?w=400&h=300&fit=crop',
	'梨': 'https://images.unsplash.com/photo-1519163241601-f6a393521b26?w=400&h=300&fit=crop',
	'菠萝': 'https://images.unsplash.com/photo-1550828520-4cb496926fc9?w=400&h=300&fit=crop',
	'草莓': 'https://images.unsplash.com/photo-1601004890684-d8cbf643f5f2?w=400&h=300&fit=crop',
	'西瓜': 'https://images.unsplash.com/photo-1587049352846-4a222e784d38?w=400&h=300&fit=crop',
	// 蔬菜
	'彩椒': 'https://images.unsplash.com/photo-1563565375-f3fdfdbefa83?w=400&h=300&fit=crop',
	'卷心菜': 'https://images.unsplash.com/photo-1594282486552-05b4d80fbb9f?w=400&h=300&fit=crop',
	'胡萝卜': 'https://images.unsplash.com/photo-1598170845058-32b9d6a5da37?w=400&h=300&fit=crop',
	'花椰菜': 'https://images.unsplash.com/photo-1459411621453-7b03977f4bfc?w=400&h=300&fit=crop',
	'辣椒': 'https://images.unsplash.com/photo-1588252303782-cb80119abd6d?w=400&h=300&fit=crop',
	'玉米': 'https://images.unsplash.com/photo-1601593768799-76e1c3e2ed1b?w=400&h=300&fit=crop',
	'黄瓜': 'https://images.unsplash.com/photo-1604977042946-1eecc30f269e?w=400&h=300&fit=crop',
	'茄子': 'https://images.unsplash.com/photo-1605370511616-1ec0b2cfb69d?w=400&h=300&fit=crop',
	'大蒜': 'https://images.unsplash.com/photo-1615477550927-6ec8445fcf81?w=400&h=300&fit=crop',
	'生姜': 'https://images.unsplash.com/photo-1618164435739-413d3b066c9f?w=400&h=300&fit=crop',
	'四季豆': 'https://images.unsplash.com/photo-1567375698348-7d6d0ae5706f?w=400&h=300&fit=crop',
	'韭菜': 'https://images.unsplash.com/photo-1589810828015-2b3fe2a2b01c?w=400&h=300&fit=crop',
	'生菜': 'https://images.unsplash.com/photo-1556801712-76c8eb07bbc9?w=400&h=300&fit=crop',
	'蘑菇': 'https://images.unsplash.com/photo-1574158622682-e40e69881006?w=400&h=300&fit=crop',
	'洋葱': 'https://images.unsplash.com/photo-1618745492237-c6831270a1f8?w=400&h=300&fit=crop',
	'土豆': 'https://images.unsplash.com/photo-1590165482129-1b8b27698780?w=400&h=300&fit=crop',
	'菠菜': 'https://images.unsplash.com/photo-1576045057995-9d1ad5bdb2f3?w=400&h=300&fit=crop',
	'红薯': 'https://images.unsplash.com/photo-1596097635176-0bd8ea1c3742?w=400&h=300&fit=crop',
	'番茄': 'https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=400&h=300&fit=crop',
	'绿叶菜': 'https://images.unsplash.com/photo-1556801712-76c8eb07bbc9?w=400&h=300&fit=crop',
	// 肉蛋
	'鸡肉': 'https://images.unsplash.com/photo-1604503468506-a8da13d82791?w=400&h=300&fit=crop',
	'鸡蛋': 'https://images.unsplash.com/photo-1582722872445-44dc5f7e3c8f?w=400&h=300&fit=crop',
	'肉类': 'https://images.unsplash.com/photo-1603048297172-bf27e2fc79e6?w=400&h=300&fit=crop',
	'虾': 'https://images.unsplash.com/photo-1565680018434-b513d5e5fd47?w=400&h=300&fit=crop',
	// 饮品
	'牛奶': 'https://images.unsplash.com/photo-1563636619-e9143da7973b?w=400&h=300&fit=crop',
	'酸奶': 'https://images.unsplash.com/photo-1488477181946-6428a0291777?w=400&h=300&fit=crop',
	'可乐': 'https://images.unsplash.com/photo-1629203851122-3b7c62e6ce5e?w=400&h=300&fit=crop',
	'芬达': 'https://images.unsplash.com/photo-1625772299848-3917ab7ac5b4?w=400&h=300&fit=crop',
	'雪碧': 'https://images.unsplash.com/photo-1625772299848-3917ab7ac5b4?w=400&h=300&fit=crop',
	'饮料': 'https://images.unsplash.com/photo-1629203851122-3b7c62e6ce5e?w=400&h=300&fit=crop',
	'水': 'https://images.unsplash.com/photo-1523362628745-0c100150b504?w=400&h=300&fit=crop',
	// 零食
	'面包': 'https://images.unsplash.com/photo-1608198093002-ad4e005484ec?w=400&h=300&fit=crop',
	'奶酪': 'https://images.unsplash.com/photo-1552767059-ce182ead6c1b?w=400&h=300&fit=crop',
	'巧克力': 'https://images.unsplash.com/photo-1606312619070-d48b4c652a52?w=400&h=300&fit=crop',
	// 其他已存在
	'红富士苹果': 'https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?w=400&h=300&fit=crop',
	'有机鸡胸肉': 'https://images.unsplash.com/photo-1604503468506-a8da13d82791?w=400&h=300&fit=crop',
	'鲜牛奶': 'https://images.unsplash.com/photo-1563636619-e9143da7973b?w=400&h=300&fit=crop',
	'西兰花': 'https://images.unsplash.com/photo-1459411621453-7b03977f4bfc?w=400&h=300&fit=crop',
	'有机鸡蛋': 'https://images.unsplash.com/photo-1582722872445-44dc5f7e3c8f?w=400&h=300&fit=crop',
	'希腊酸奶': 'https://images.unsplash.com/photo-1488477181946-6428a0291777?w=400&h=300&fit=crop',
	'澳洲牛排': 'https://images.unsplash.com/photo-1603048297172-bf27e2fc79e6?w=400&h=300&fit=crop',
	'橙汁': 'https://images.unsplash.com/photo-1600271886742-f049cd451bba?w=400&h=300&fit=crop',
	'三文鱼': 'https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=400&h=300&fit=crop',
}

const _imgCache = new Map()
const _ingredientKeys = Object.keys(_mapping.ingredients || {})
const _recipeKeys = Object.keys(_mapping.recipes || {})

export function getIngredientImage(name) {
	if (!name) return FALLBACK_FOOD
	const cached = _imgCache.get(name)
	if (cached !== undefined) return cached

	const mapping = _mapping
	let result = null
	if (mapping.ingredients[name]) result = resolveImagePath(mapping.ingredients[name])
	if (!result) {
		const stripped = name.replace(/^(有机|鲜|澳洲|红富士|希腊|进口|土|纯)/, '')
		if (stripped !== name && mapping.ingredients[stripped]) result = resolveImagePath(mapping.ingredients[stripped])
	}
	if (!result) {
		const enKey = ZH_TO_EN[name]
		if (enKey && mapping.ingredients[enKey]) result = resolveImagePath(mapping.ingredients[enKey])
	}
	if (!result) {
		for (const key of _ingredientKeys) {
			if (name.includes(key) || key.includes(name)) { result = resolveImagePath(mapping.ingredients[key]); break }
		}
	}
	result = result || DEMO_PHOTOS[name] || FALLBACK_FOOD
	_imgCache.set(name, result)
	return result
}

const _recipeCache = new Map()

export function getRecipeImage(name) {
	if (!name) return FALLBACK_RECIPE
	const cached = _recipeCache.get(name)
	if (cached !== undefined) return cached

	const mapping = _mapping
	let result = null
	if (mapping.recipes[name]) result = resolveImagePath(mapping.recipes[name])
	if (!result) {
		const cleaned = name.replace(/\s*(的)?(做法|制作方法)\s*$/, '')
		if (cleaned !== name && mapping.recipes[cleaned]) result = resolveImagePath(mapping.recipes[cleaned])
	}
	if (!result) {
		for (const key of _recipeKeys) {
			if (name.includes(key) || key.includes(name)) { result = resolveImagePath(mapping.recipes[key]); break }
		}
	}
	result = result || FALLBACK_RECIPE
	_recipeCache.set(name, result)
	return result
}

export function resolveImage(url, name, type) {
	if (url && !url.startsWith('http')) return url
	if (url && url.startsWith('http')) return url
	return type === 'ingredient' ? getIngredientImage(name) : getRecipeImage(name)
}
