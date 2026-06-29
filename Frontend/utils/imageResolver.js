/**
 * 图片解析器 — 优先使用本地 static/images 缓存，未命中时回退 Unsplash
 */

import imageMapping from '@/data/image_mapping.json'

const _mapping = imageMapping || { ingredients: {}, recipes: {} }

function getImageBase() {
	try {
		const stored = uni.getStorageSync('backend_url')
		if (stored) return stored.replace(/\/+$/, '') + '/static/images/'
	} catch (e) { /* ignore */ }
	return 'http://localhost:8000/static/images/'
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

const ZH_TO_EN = {
	// 水果
	'苹果': 'apple', '香蕉': 'banana', '蓝莓': 'blueberry', '葡萄': 'grape',
	'猕猴桃': 'kiwi', '柠檬': 'lemon', '青柠': 'lime', '芒果': 'mango',
	'橙子': 'orange', '桃子': 'peach', '梨': 'pear', '菠萝': 'pineapple',
	'草莓': 'strawberry', '西瓜': 'watermelon',
	// 蔬菜
	'彩椒': 'bell_pepper', '卷心菜': 'cabbage', '胡萝卜': 'carrot',
	'花椰菜': 'cauliflower', '辣椒': 'chilli_pepper', '玉米': 'corn',
	'黄瓜': 'cucumber', '茄子': 'eggplant', '大蒜': 'garlic', '生姜': 'ginger',
	'四季豆': 'green_beans', '韭菜': 'leek', '生菜': 'lettuce',
	'蘑菇': 'mushroom', '洋葱': 'onion', '土豆': 'potato',
	'菠菜': 'spinach', '红薯': 'sweet potato', '番茄': 'tomato', '绿叶菜': 'green leaves',
	// 肉蛋
	'鸡肉': 'chicken', '鸡蛋': 'egg', '肉类': 'meat', '虾': 'shrimp',
	// 饮品
	'牛奶': 'milk', '酸奶': 'yogurt', '奶酪': 'cheese', '可乐': 'cola',
	'水': 'water', '芬达': 'fanta', '雪碧': 'sprite', '饮料': 'drink',
	// 零食
	'面包': 'bread', '巧克力': 'chocolate',
}

export function getIngredientImage(name) {
	const mapping = _mapping
	if (mapping.ingredients[name]) return resolveImagePath(mapping.ingredients[name])
	const stripped = (name || '').replace(/^(有机|鲜|澳洲|红富士|希腊|进口|土|纯)/, '')
	if (stripped !== name && mapping.ingredients[stripped]) return resolveImagePath(mapping.ingredients[stripped])
	const enKey = ZH_TO_EN[name] || ZH_TO_EN[stripped]
	if (enKey && mapping.ingredients[enKey]) return resolveImagePath(mapping.ingredients[enKey])
	for (const key of Object.keys(mapping.ingredients)) {
		if (name.includes(key) || key.includes(name)) return resolveImagePath(mapping.ingredients[key])
	}
	return DEMO_PHOTOS[name] || FALLBACK_FOOD
}

export function getRecipeImage(name) {
	const mapping = _mapping
	if (mapping.recipes[name]) return resolveImagePath(mapping.recipes[name])
	const cleaned = (name || '').replace(/\s*(的)?(做法|制作方法)\s*$/, '')
	if (cleaned !== name && mapping.recipes[cleaned]) return resolveImagePath(mapping.recipes[cleaned])
	for (const key of Object.keys(mapping.recipes)) {
		if (name.includes(key) || key.includes(name)) return resolveImagePath(mapping.recipes[key])
	}
	return FALLBACK_RECIPE
}

export function resolveImage(url, name, type) {
	if (url && !url.startsWith('http')) return url
	if (url && url.startsWith('http')) return url
	return type === 'ingredient' ? getIngredientImage(name) : getRecipeImage(name)
}
