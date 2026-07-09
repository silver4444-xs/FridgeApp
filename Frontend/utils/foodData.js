/**
 * 食材共享数据 — EN/ZH 映射、分类、卡路里
 * store.js 和 imageResolver.js 共用此文件，消除映射表重复
 */

export const EN_TO_ZH = {
	apple: '苹果', banana: '香蕉', blueberry: '蓝莓', grape: '葡萄',
	kiwi: '猕猴桃', lemon: '柠檬', lime: '青柠', mango: '芒果',
	orange: '橙子', peach: '桃子', pear: '梨', pineapple: '菠萝',
	strawberry: '草莓', watermelon: '西瓜',
	bell_pepper: '彩椒', cabbage: '卷心菜', carrot: '胡萝卜',
	cauliflower: '花椰菜', chilli_pepper: '辣椒', corn: '玉米',
	cucumber: '黄瓜', eggplant: '茄子', garlic: '大蒜', ginger: '生姜',
	green_beans: '四季豆', leek: '韭菜', lettuce: '生菜',
	mushroom: '蘑菇', onion: '洋葱', potato: '土豆',
	spinach: '菠菜', 'sweet potato': '红薯', sweetpotato: '红薯',
	tomato: '番茄', 'green leaves': '绿叶菜',
	cola: '可乐', drink: '饮料', fanta: '芬达', milk: '牛奶', sprite: '雪碧',
	water: '水', yogurt: '酸奶',
	chicken: '鸡肉', egg: '鸡蛋', meat: '肉类', shrimp: '虾',
	bread: '面包', cheese: '奶酪', chocolate: '巧克力',
}

export const EN_TO_CAT = {
	apple: 'fruit', banana: 'fruit', blueberry: 'fruit', grape: 'fruit',
	kiwi: 'fruit', lemon: 'fruit', lime: 'fruit', mango: 'fruit',
	orange: 'fruit', peach: 'fruit', pear: 'fruit', pineapple: 'fruit',
	strawberry: 'fruit', watermelon: 'fruit',
	bell_pepper: 'vegetable', cabbage: 'vegetable', carrot: 'vegetable',
	cauliflower: 'vegetable', chilli_pepper: 'vegetable', corn: 'vegetable',
	cucumber: 'vegetable', eggplant: 'vegetable', garlic: 'vegetable',
	ginger: 'vegetable', green_beans: 'vegetable', leek: 'vegetable',
	lettuce: 'vegetable', mushroom: 'vegetable', onion: 'vegetable',
	potato: 'vegetable', spinach: 'vegetable',
	'sweet potato': 'vegetable', sweetpotato: 'vegetable',
	tomato: 'vegetable', 'green leaves': 'vegetable',
	cola: 'beverage_dairy', drink: 'beverage_dairy', fanta: 'beverage_dairy',
	milk: 'beverage_dairy', sprite: 'beverage_dairy',
	water: 'beverage_dairy', yogurt: 'beverage_dairy',
	chicken: 'meat_egg', egg: 'meat_egg', meat: 'meat_egg', shrimp: 'meat_egg',
	bread: 'packaged', cheese: 'packaged', chocolate: 'packaged',
}

export const FOOD_CALORIES = {
	apple: 52, banana: 89, blueberry: 57, grape: 69,
	kiwi: 61, lemon: 29, lime: 30, mango: 60,
	orange: 47, peach: 39, pear: 57, pineapple: 50,
	strawberry: 32, watermelon: 30,
	bell_pepper: 20, cabbage: 25, carrot: 41,
	cauliflower: 25, chilli_pepper: 40, corn: 86,
	cucumber: 15, eggplant: 25, garlic: 149, ginger: 80,
	green_beans: 31, leek: 61, lettuce: 15,
	mushroom: 22, onion: 40, potato: 77,
	spinach: 23, 'sweet potato': 86, sweetpotato: 86,
	tomato: 18, 'green leaves': 20,
	cola: 43, drink: 40, fanta: 48, milk: 70, sprite: 41, water: 0, yogurt: 63,
	chicken: 167, egg: 155, meat: 250, shrimp: 99,
	bread: 265, cheese: 350, chocolate: 546,
}

// ZH→EN 反向映射 (自动生成，保证一致性)
export const ZH_TO_EN = {}
for (const [en, zh] of Object.entries(EN_TO_ZH)) {
	if (!ZH_TO_EN[zh]) ZH_TO_EN[zh] = en
}

export function translateFoodName(name) {
	if (!name) return name
	const lower = name.toLowerCase().trim()
	return EN_TO_ZH[lower] || name
}

export function classifyFood(input) {
	const trimmed = (input || '').trim(); const lower = trimmed.toLowerCase()
	if (EN_TO_ZH[lower]) return { enName: lower, zhName: EN_TO_ZH[lower], cat: EN_TO_CAT[lower] || 'packaged', calories: FOOD_CALORIES[lower] ?? null }
	const en = ZH_TO_EN[trimmed]
	if (en) return { enName: en, zhName: trimmed, cat: EN_TO_CAT[en] || 'packaged', calories: FOOD_CALORIES[en] ?? null }
	return { enName: lower, zhName: trimmed, cat: 'packaged', calories: null }
}
