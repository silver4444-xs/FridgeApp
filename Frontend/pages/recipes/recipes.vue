<template>
	<view class="page-shell">
		<scroll-view class="page" scroll-y>
			<!-- Header -->
			<view class="recipe-header">
				<text class="recipe-title">智能食谱</text>
				<text class="recipe-sub">基于冰箱食材，AI 为你推荐能做的美味</text>
			</view>

			<!-- Compact Stats Bar -->
			<view class="stats-bar">
				<view class="stat-card">
					<view class="stat-icon-box icon-food">
						<text class="material-icons">restaurant</text>
					</view>
					<view class="stat-body">
						<text class="stat-value">{{ totalFoods }}</text>
						<text class="stat-label">食材种类</text>
					</view>
				</view>
				<view class="stat-card">
					<view class="stat-icon-box icon-cook">
						<text class="material-icons">menu_book</text>
					</view>
					<view class="stat-body">
						<text class="stat-value highlight">{{ matchedRecipes.length }}</text>
						<text class="stat-label">可做菜谱</text>
					</view>
				</view>
				<view class="stat-card">
					<view class="stat-icon-box icon-rate">
						<text class="material-icons">trending_up</text>
					</view>
					<view class="stat-body">
						<text class="stat-value green">{{ matchPercent }}%</text>
						<text class="stat-label">覆盖率</text>
					</view>
				</view>
			</view>

			<!-- Tab Bar -->
			<view class="tab-bar">
				<view
					v-for="tab in tabs"
					:key="tab.key"
					class="tab-item"
					:class="{ active: activeTab === tab.key }"
					@click="switchTab(tab.key)"
				>
					<text class="material-icons tab-icon">{{ tab.icon }}</text>
					<text class="tab-label">{{ tab.label }}</text>
				</view>
			</view>

			<!-- ===== Tab 1: AI 推荐 ===== -->
			<view v-show="activeTab === 'recommend'">
				<!-- Loading -->
				<view v-if="loading" class="loading-state">
					<view class="loading-spinner"></view>
					<text class="loading-text">AI 正在分析冰箱食材...</text>
				</view>

				<!-- Top Matches Horizontal Scroll -->
				<view v-if="!loading && topMatches.length > 0" class="section">
					<text class="section-title">最佳匹配</text>
					<scroll-view scroll-x class="h-scroll" :show-scrollbar="false">
						<view
							v-for="recipe in topMatches"
							:key="recipe.id"
							class="card-h"
							@click="openRecipe(recipe)"
						>
							<view class="card-h-img-wrap">
								<image :src="recipe.image" mode="aspectFill" class="card-h-img" />
								<view class="card-h-badge" :class="getMatchLevel(recipe)">
									<text>{{ recipe.matchCount }}/{{ recipe.ingredients.length }}种</text>
								</view>
							</view>
							<view class="card-h-body">
								<text class="card-h-name">{{ recipe.name }}</text>
								<view class="card-h-meta">
									<text>⏱ {{ recipe.time }}</text>
									<text class="meta-sep">·</text>
									<text>{{ recipe.difficulty }}</text>
								</view>
							</view>
						</view>
					</scroll-view>
				</view>

				<!-- More Matches Grid -->
				<view v-if="!loading && moreMatches.length > 0" class="section">
					<text class="section-title">更多推荐</text>
					<view class="recipe-grid">
						<view
							v-for="recipe in moreMatches"
							:key="recipe.id"
							class="card-v"
							@click="openRecipe(recipe)"
						>
							<image :src="recipe.image" mode="aspectFill" class="card-v-img" />
							<view class="card-v-body">
								<text class="card-v-name">{{ recipe.name }}</text>
								<view class="card-v-ingredients">
									<text
										v-for="ing in recipe.ingredients.slice(0, 4)"
										:key="ing"
										class="ing-chip"
										:class="{ owned: isIngredientOwnedInRecipe(recipe, ing) }"
									>{{ ing }}</text>
									<text v-if="recipe.ingredients.length > 4" class="ing-more">+{{ recipe.ingredients.length - 4 }}</text>
								</view>
								<view class="card-v-footer">
									<view class="match-tag" :class="getMatchLevel(recipe)">
										<text>{{ recipe.matchCount }}/{{ recipe.ingredients.length }} 种</text>
									</view>
									<text class="card-v-time">{{ recipe.time }}</text>
								</view>
							</view>
						</view>
					</view>
				</view>

				<!-- Empty State -->
				<view v-if="!loading && topMatches.length === 0" class="empty-state">
					<text class="material-icons empty-icon">kitchen</text>
					<text class="empty-text">冰箱里还没有食材</text>
					<text class="empty-hint">添加食材后自动推荐可做菜谱</text>
				</view>
			</view>

			<!-- ===== Tab 2: 搜索食谱 ===== -->
			<view v-show="activeTab === 'search'">
				<!-- Search Mode Toggle -->
				<view class="search-mode-row">
					<view
						class="mode-chip"
						:class="{ active: searchMode === 'name' }"
						@click="searchMode = 'name'"
					><text>按菜名</text></view>
					<view
						class="mode-chip"
						:class="{ active: searchMode === 'ingredient' }"
						@click="searchMode = 'ingredient'"
					><text>按食材</text></view>
				</view>

				<!-- Search by Name -->
				<view v-if="searchMode === 'name'" class="search-box">
					<view class="search-input-row">
						<text class="material-icons search-icon">search</text>
						<input
							v-model="searchQuery"
							class="search-field"
							placeholder="输入菜名，如 红烧肉、宫保鸡丁"
							confirm-type="search"
							@confirm="searchRecipes"
						/>
						<view class="search-btn" @click="searchRecipes">
							<text>搜索</text>
						</view>
					</view>
				</view>

				<!-- Search by Ingredients -->
				<view v-if="searchMode === 'ingredient'" class="search-box">
					<view class="search-input-row">
						<text class="material-icons search-icon">auto_awesome</text>
						<input
							v-model="ingredientQuery"
							class="search-field"
							placeholder="输入食材，逗号分隔（如 鸡胸肉, 西红柿）"
							confirm-type="search"
							@confirm="fetchIngredientSearch"
						/>
						<view class="search-btn accent" @click="fetchIngredientSearch">
							<text>推荐</text>
						</view>
					</view>
				</view>

				<!-- Search Loading -->
				<view v-if="searchLoading || ingredientLoading" class="loading-state">
					<view class="loading-spinner"></view>
					<text class="loading-text">{{ searchLoading ? '搜索中...' : 'AI 正在匹配菜谱...' }}</text>
				</view>

				<!-- Search Results (by name) -->
				<view v-if="!searchLoading && searchPerformed && searchMode === 'name'" class="recipe-grid">
					<view
						v-for="r in searchResults"
						:key="r.id"
						class="card-v"
						@click="openSearchResult(r)"
					>
						<image :src="r.image || fallbackImg" mode="aspectFill" class="card-v-img" />
						<view class="card-v-body">
							<text class="card-v-name">{{ r.name }}</text>
							<view class="card-v-footer">
								<view class="cat-tag"><text>{{ r.category || '其他' }}</text></view>
								<text class="card-v-time">{{ r.difficulty || '未知' }}</text>
							</view>
						</view>
					</view>
				</view>

				<!-- Search Results (by ingredient) -->
				<view v-if="!ingredientLoading && ingredientSearched && searchMode === 'ingredient'" class="recipe-grid">
					<view
						v-for="r in ingredientResults"
						:key="r.id"
						class="card-v"
						@click="openRecipe(r)"
					>
						<image :src="r.image" mode="aspectFill" class="card-v-img" />
						<view class="card-v-body">
							<text class="card-v-name">{{ r.name }}</text>
							<view class="card-v-ingredients">
								<text
									v-for="ing in r.ingredients.slice(0, 4)"
									:key="ing"
									class="ing-chip"
									:class="{ owned: isIngredientOwnedInRecipe(r, ing) }"
								>{{ ing }}</text>
								<text v-if="r.ingredients.length > 4" class="ing-more">+{{ r.ingredients.length - 4 }}</text>
							</view>
							<view class="card-v-footer">
								<view class="match-tag" :class="getMatchLevel(r)">
									<text>{{ r.matchCount }}/{{ r.ingredients.length }} 种</text>
								</view>
								<text class="card-v-time">{{ r.time }}</text>
							</view>
						</view>
					</view>
				</view>

				<!-- Empty Search State -->
				<view v-if="!searchLoading && !ingredientLoading && ((searchMode === 'name' && searchPerformed && searchResults.length === 0) || (searchMode === 'ingredient' && ingredientSearched && ingredientResults.length === 0))" class="empty-state">
					<text class="material-icons empty-icon">search_off</text>
					<text class="empty-text">未找到匹配的菜谱</text>
					<text class="empty-hint">试试其他关键词</text>
				</view>
			</view>

			<!-- ===== Tab 3: 全部食谱 ===== -->
			<view v-show="activeTab === 'all'">
				<!-- Tag Filters -->
				<scroll-view v-if="availableTags.length > 0" scroll-x class="tag-scroll" :show-scrollbar="false">
					<view
						v-for="tag in availableTags"
						:key="tag"
						class="tag-chip"
						:class="{ active: activeTag === tag }"
						@click="filterByTag(tag)"
					>
						<text>{{ tag }}</text>
					</view>
				</scroll-view>

				<!-- Recipe Grid -->
				<view v-if="!loading && filteredRecipes.length > 0" class="recipe-grid">
					<view
						v-for="recipe in filteredRecipes"
						:key="recipe.id"
						class="card-v"
						@click="openRecipe(recipe)"
					>
						<image :src="recipe.image" mode="aspectFill" class="card-v-img" />
						<view class="card-v-body">
							<text class="card-v-name">{{ recipe.name }}</text>
							<view class="card-v-ingredients">
								<text
									v-for="ing in recipe.ingredients.slice(0, 4)"
									:key="ing"
									class="ing-chip"
									:class="{ owned: isIngredientOwnedInRecipe(recipe, ing) }"
								>{{ ing }}</text>
								<text v-if="recipe.ingredients.length > 4" class="ing-more">+{{ recipe.ingredients.length - 4 }}</text>
							</view>
							<view class="card-v-footer">
								<view class="match-tag" :class="getMatchLevel(recipe)">
									<text>{{ recipe.matchCount }}/{{ recipe.ingredients.length }} 种</text>
								</view>
								<view class="card-v-meta">
									<text>{{ recipe.time }}</text>
									<text class="meta-sep">·</text>
									<text>{{ recipe.difficulty }}</text>
								</view>
							</view>
						</view>
					</view>
				</view>

				<!-- Empty -->
				<view v-if="!loading && filteredRecipes.length === 0" class="empty-state">
					<text class="material-icons empty-icon">search_off</text>
					<text class="empty-text">没有匹配的食谱</text>
					<text class="empty-hint">试试添加更多食材到冰箱</text>
				</view>
			</view>

			<!-- Agent Chat Box -->
			<view class="chat-section">
				<AgentChatBox ref="chatBox" />
			</view>
		</scroll-view>

		<!-- Recipe Detail Modal -->
		<RecipeDetailModal v-if="activeRecipe" :recipe="activeRecipe" :ownedKeywords="ownedKeywords" @close="closeRecipe" />
	</view>
</template>

<script>
import { store } from '@/utils/store.js'
import RecipeDetailModal from '@/components/recipes/RecipeDetailModal.vue'
import AgentChatBox from '@/components/recipes/AgentChatBox.vue'

import { getRecipeImage, FALLBACK_RECIPE } from '@/utils/imageResolver.js'

function getApiBase() {
	try {
		const stored = uni.getStorageSync('backend_url')
		if (stored) return stored.replace(/\/+$/, '') + '/api'
	} catch (e) { /* ignore */ }
	return 'http://localhost:8000/api'
}
const FALLBACK_IMG = FALLBACK_RECIPE

// ======================== 食谱数据库（Fallback） ========================
const RECIPES = [
	{
		id: 1,
		name: '西红柿炒鸡蛋',
		image: null,
		ingredients: ['番茄', '鸡蛋', '葱', '糖', '盐'],
		steps: [
			'番茄洗净切小块；鸡蛋打入碗中加少许盐搅散。',
			'热锅倒油，油热后倒入蛋液，炒至凝固划散盛出。',
			'锅中再加少许油，放入番茄块中火翻炒出汁。',
			'加半勺糖中和酸味，番茄软烂后倒回鸡蛋。',
			'翻炒均匀，加盐调味，撒葱花出锅。'
		],
		time: '10分钟', difficulty: '非常简单', calories: '150大卡',
		tags: ['中式', '快手', '家常']
	},
	{
		id: 2,
		name: '西红柿牛腩',
		image: null,
		ingredients: ['牛肉', '番茄', '胡萝卜', '洋葱', '姜'],
		steps: [
			'牛腩切块，冷水下锅加姜片焯水5分钟，捞出洗净。',
			'番茄烫去外皮切块，胡萝卜切滚刀块，洋葱切块。',
			'热锅少油，洋葱炒香，加番茄炒出红油。',
			'倒入牛腩翻炒上色，加生抽、老抽、冰糖调味。',
			'加足量热水没过食材，大火烧开转小火炖40分钟。',
			'加胡萝卜再炖15分钟，大火收汁出锅。'
		],
		time: '60分钟', difficulty: '中等', calories: '380大卡',
		tags: ['中式', '炖煮', '硬菜']
	},
	{
		id: 3,
		name: '蛋炒饭',
		image: null,
		ingredients: ['米饭', '鸡蛋', '胡萝卜', '葱', '盐'],
		steps: [
			'隔夜米饭抓散备用；鸡蛋打散；胡萝卜切小丁。',
			'热锅倒油，倒入蛋液快速划散至凝固盛出。',
			'锅中补少许油，下胡萝卜丁翻炒至变软。',
			'倒入米饭大火翻炒，用铲子压散米粒。',
			'倒回鸡蛋，加盐调味，撒葱花翻炒均匀出锅。'
		],
		time: '10分钟', difficulty: '简单', calories: '280大卡',
		tags: ['中式', '快手', '主食']
	},
	{
		id: 4,
		name: '可乐鸡翅',
		image: null,
		ingredients: ['鸡翅', '可乐', '酱油', '姜', '料酒'],
		steps: [
			'鸡翅洗净，正反面各划两刀方便入味。',
			'冷水下锅加姜片料酒焯水，捞出沥干。',
			'热锅少油，鸡翅皮面朝下煎至两面金黄。',
			'倒入可乐没过鸡翅，加生抽老抽调味。',
			'大火烧开转中小火焖15分钟。',
			'开盖大火收汁至浓稠挂满鸡翅即可。'
		],
		time: '25分钟', difficulty: '简单', calories: '320大卡',
		tags: ['中式', '快手', '下饭']
	},
	{
		id: 5,
		name: '麻婆豆腐',
		image: null,
		ingredients: ['豆腐', '猪肉', '豆瓣酱', '大蒜', '姜', '淀粉'],
		steps: [
			'豆腐切2cm方块，淡盐水中浸泡10分钟。',
			'猪肉剁碎；蒜姜切末；淀粉加水调成水淀粉。',
			'沸水加盐，豆腐焯烫1分钟捞出。',
			'热锅少油，下肉末炒至变色，加豆瓣酱炒出红油。',
			'加蒜姜末炒香，倒入适量清水烧开。',
			'放入豆腐小火煮3分钟入味，淋水淀粉勾芡。',
			'撒花椒粉和葱花出锅。'
		],
		time: '20分钟', difficulty: '中等', calories: '260大卡',
		tags: ['中式', '麻辣', '下饭']
	},
	{
		id: 6,
		name: '蒜蓉西兰花',
		image: null,
		ingredients: ['西兰花', '大蒜', '盐', '食用油'],
		steps: [
			'西兰花掰小朵，淡盐水中浸泡10分钟后洗净。',
			'大蒜剁成蒜蓉。',
			'沸水加盐和几滴油，西兰花焯烫1分钟捞出过凉。',
			'热锅少油，小火将蒜蓉炒出香味。',
			'倒入西兰花大火翻炒均匀，加盐调味出锅。'
		],
		time: '10分钟', difficulty: '非常简单', calories: '80大卡',
		tags: ['中式', '快手', '轻食']
	},
	{
		id: 7,
		name: '白灼虾',
		image: null,
		ingredients: ['虾', '姜', '料酒', '酱油', '醋'],
		steps: [
			'鲜虾剪去虾须虾枪，挑去虾线洗净。',
			'锅中加足量水，放入姜片和料酒烧开。',
			'水沸后倒入虾，煮至虾身变红弯曲（约2分钟）。',
			'捞出立即过冰水，沥干摆盘。',
			'姜丝加生抽、醋调成蘸料。'
		],
		time: '10分钟', difficulty: '非常简单', calories: '120大卡',
		tags: ['中式', '海鲜', '快手']
	},
	{
		id: 8,
		name: '土豆炖排骨',
		image: null,
		ingredients: ['排骨', '土豆', '胡萝卜', '姜', '酱油', '料酒'],
		steps: [
			'排骨斩小段，冷水下锅加姜片料酒焯水5分钟。',
			'土豆胡萝卜去皮切滚刀块。',
			'热锅少油，排骨煎至表面微黄。',
			'加生抽老抽翻炒上色，倒热水没过排骨。',
			'大火烧开转小火炖30分钟。',
			'加入土豆和胡萝卜，继续炖15分钟至软烂。',
			'加盐调味，大火收汁出锅。'
		],
		time: '50分钟', difficulty: '中等', calories: '420大卡',
		tags: ['中式', '炖煮', '硬菜']
	},
	{
		id: 9,
		name: '宫保鸡丁',
		image: null,
		ingredients: ['鸡胸肉', '花生', '黄瓜', '胡萝卜', '酱油', '醋', '糖', '淀粉'],
		steps: [
			'鸡胸肉切1.5cm丁，加料酒、淀粉、盐抓匀腌制15分钟。',
			'黄瓜胡萝卜切丁；花生米小火炒至微焦放凉。',
			'调碗汁：生抽、醋、糖、淀粉、水搅匀。',
			'热锅多油，鸡丁滑炒至变白盛出。',
			'底油爆香干辣椒和花椒，下胡萝卜丁炒断生。',
			'倒回鸡丁加黄瓜丁翻炒，淋碗汁快速翻炒均匀。',
			'撒花生米翻匀出锅。'
		],
		time: '25分钟', difficulty: '中等', calories: '350大卡',
		tags: ['中式', '快炒', '下饭']
	},
	{
		id: 10,
		name: '酸辣土豆丝',
		image: null,
		ingredients: ['土豆', '青椒', '红椒', '醋', '盐', '大蒜'],
		steps: [
			'土豆去皮切细丝，冷水浸泡洗去多余淀粉，沥干。',
			'青红椒切丝；蒜切片。',
			'热锅倒油，蒜片爆香。',
			'倒入土豆丝大火快速翻炒至半透明。',
			'加青红椒丝翻炒，沿锅边淋入醋。',
			'加盐调味，翻炒均匀出锅。'
		],
		time: '10分钟', difficulty: '简单', calories: '130大卡',
		tags: ['中式', '快手', '下饭']
	},
]

// ======================== 食材别名引擎 ========================
const INGREDIENT_ALIASES = {
	'牛肉':   ['牛肉', '牛排', '牛腩', '肥牛', '澳洲牛排', '和牛'],
	'牛排':   ['牛排', '牛肉', '澳洲牛排', '和牛'],
	'鸡肉':   ['鸡肉', '鸡胸肉', '鸡腿肉', '鸡翅', '鸡', '有机鸡胸肉'],
	'鸡胸肉': ['鸡胸肉', '鸡肉', '有机鸡胸肉', '鸡'],
	'猪肉':   ['猪肉', '猪'],
	'三文鱼': ['三文鱼', '鲑鱼', '三文鱼排'],
	'鸡蛋':   ['鸡蛋', '蛋', '有机鸡蛋', '土鸡蛋', '鲜鸡蛋'],
	'牛奶':   ['牛奶', '鲜牛奶', '纯牛奶', '奶', '鲜奶'],
	'酸奶':   ['酸奶', '希腊酸奶', '优格', '酸牛奶'],
	'苹果':   ['苹果', '红富士苹果', '红苹果'],
	'草莓':   ['草莓'],
	'橙子':   ['橙子', '橙汁', '橙', '甜橙'],
	'胡萝卜': ['胡萝卜', '红萝卜', '胡萝卜'],
	'西兰花': ['西兰花', '花椰菜', '青花菜', '西兰花'],
	'菠菜':   ['菠菜'],
	'生菜':   ['生菜', '叶生菜'],
	'番茄':   ['番茄', '西红柿'],
	'洋葱':   ['洋葱', '洋葱头'],
	'豆腐':   ['豆腐', '嫩豆腐', '老豆腐'],
	'柠檬':   ['柠檬'],
	'大蒜':   ['大蒜', '蒜', '蒜头'],
	'姜':     ['姜', '生姜', '姜片'],
	'黄油':   ['黄油', '牛油'],
	'蜂蜜':   ['蜂蜜', '蜜糖'],
	'酱油':   ['酱油', '生抽', '老抽'],
	'糖':     ['糖', '白糖', '细砂糖', '冰糖'],
	'米饭':   ['米饭', '米', '大米', '剩饭'],
	'燕麦':   ['燕麦', '即食燕麦', '燕麦片'],
	'黑胡椒': ['黑胡椒', '黑胡椒粉', '胡椒'],
	'橄榄油': ['橄榄油', '食用油', '植物油'],
}

const MODIFIER_PREFIXES = ['有机', '鲜', '澳洲', '红富士', '希腊', '进口', '土', '纯', '精品', '新鲜', '精选', '特级', '散养']

function buildOwnedKeywords() {
	const keywords = new Set()
	store.foods.forEach(f => {
		const name = f.name
		keywords.add(name)
		let stripped = name
		let changed = true
		while (changed) {
			changed = false
			for (const prefix of MODIFIER_PREFIXES) {
				if (stripped.startsWith(prefix) && stripped.length > prefix.length) {
					stripped = stripped.slice(prefix.length)
					changed = true
					break
				}
			}
		}
		if (stripped !== name) keywords.add(stripped)
	})
	return keywords
}

function matchIngredient(recipeIng, ownedKeywords) {
	const aliases = INGREDIENT_ALIASES[recipeIng]
	const ownedArr = [...ownedKeywords]

	if (aliases) {
		if (aliases.some(alias => ownedArr.some(kw => kw === alias))) {
			return true
		}
		return aliases.some(alias => {
			return ownedArr.some(kw => {
				if (kw === alias) return true
				if (alias.length <= 1) return false
				if (kw.length <= 1) return false
				if (alias.length >= 3 && kw.length >= 3) {
					return kw.includes(alias) || alias.includes(kw)
				}
				return false
			})
		})
	}

	const lower = recipeIng.toLowerCase()
	return ownedArr.some(kw => {
		const k = kw.toLowerCase()
		if (lower.length <= 1 || k.length <= 1) return false
		if (lower.length >= 2 && k.length >= 2) {
			return k.includes(lower) || lower.includes(k)
		}
		return false
	})
}

export default {
	components: { RecipeDetailModal, AgentChatBox },

	data() {
		return {
			activeTab: 'recommend',
			searchMode: 'name',
			activeTag: '',
			activeRecipe: null,
			loading: false,
			error: null,
			recommendRecipes: [],
			searchResults: [],
			searchPerformed: false,
			searchLoading: false,
			ingredientResults: [],
			ingredientQuery: '',
			ingredientLoading: false,
			ingredientSearched: false,
			useFallback: false,
			searchQuery: '',
			fallbackImg: FALLBACK_IMG,
			tabs: [
				{ key: 'recommend', label: 'AI 推荐', icon: 'stars' },
				{ key: 'search', label: '搜索', icon: 'search' },
				{ key: 'all', label: '全部食谱', icon: 'apps' },
			],
		}
	},
	computed: {
		ownedKeywords() { return [...buildOwnedKeywords()] },
		totalFoods() { return store.totalCount },

		isServerMode() { return this.recommendRecipes.length > 0 },

		allRecipes() {
			if (this.recommendRecipes.length > 0) return this.recommendRecipes
			const keywords = buildOwnedKeywords()
			return RECIPES.map(r => {
				const matchCount = r.ingredients.filter(ing => matchIngredient(ing, keywords)).length
				return { ...r, image: getRecipeImage(r.name) || r.image, matchCount }
			}).sort((a, b) => b.matchCount - a.matchCount)
		},

		matchedRecipes() {
			return this.allRecipes.filter(r => r.matchCount > 0)
		},

		matchPercent() {
			const total = this.isServerMode ? this.allRecipes.length : RECIPES.length
			if (total === 0) return 0
			return Math.round((this.matchedRecipes.length / total) * 100)
		},

		topMatches() {
			return this.matchedRecipes.filter(r => r.matchCount >= 2).slice(0, 6)
		},

		moreMatches() {
			return this.matchedRecipes.filter(r => r.matchCount >= 1).slice(6)
		},

		filteredRecipes() {
			if (!this.activeTag) return this.matchedRecipes
			return this.matchedRecipes.filter(r => r.tags.includes(this.activeTag))
		},

		availableTags() {
			const set = new Set()
			this.matchedRecipes.forEach(r => r.tags.forEach(t => set.add(t)))
			return [...set]
		},
	},
	methods: {
		switchTab(key) {
			this.activeTab = key
		},

		resolveImage(img, name) {
			if (img && (img.startsWith('http') || img.startsWith('/'))) return img
			return getRecipeImage(name) || FALLBACK_IMG
		},

		async fetchRecommend() {
			this.loading = true
			this.error = null
			try {
				const ingredients = store.foods.map(f => ({ name: f.name, cat: f.cat, qty: f.qty, unit: f.unit }))
				const payload = { ingredients, limit: 50, min_match: 1 }
				const res = await uni.request({
					url: getApiBase() + '/recipes/recommend',
					method: 'POST',
					data: payload,
					timeout: 10000
				})
				if (res.statusCode === 200 && res.data && res.data.recipes) {
					this.recommendRecipes = res.data.recipes.map(r => ({
						...r,
						image: (r.image && (r.image.startsWith('http') || r.image.startsWith('/'))) ? r.image : (getRecipeImage(r.name) || FALLBACK_IMG),
						calories: '--'
					}))
					this.useFallback = false
				} else {
					throw new Error('API response invalid')
				}
			} catch (e) {
				console.warn('[Recipes] API unreachable, using fallback:', e.message || e)
				this.useFallback = true
				this.error = '无法连接到服务器，使用本地数据'
			} finally {
				this.loading = false
			}
		},

		async fetchIngredientSearch() {
			const q = this.ingredientQuery.trim()
			if (!q) return
			this.ingredientLoading = true
			this.ingredientSearched = true
			this.error = null
			try {
				const ingredients = q.split(/[,，、\s]+/).filter(Boolean).map(name => ({
					name: name.trim(), cat: 'packaged', qty: 1, unit: '个'
				}))
				const payload = { ingredients, limit: 30, min_match: 1 }
				const res = await uni.request({
					url: getApiBase() + '/recipes/recommend',
					method: 'POST',
					data: payload,
					timeout: 10000
				})
				if (res.statusCode === 200 && res.data && res.data.recipes) {
					this.ingredientResults = res.data.recipes.map(r => ({
						...r,
						image: (r.image && (r.image.startsWith('http') || r.image.startsWith('/'))) ? r.image : (getRecipeImage(r.name) || FALLBACK_IMG),
						calories: '--'
					}))
				} else {
					this.ingredientResults = []
				}
			} catch (e) {
				console.warn('[Recipes] Ingredient search failed:', e.message || e)
				this.ingredientResults = []
			} finally {
				this.ingredientLoading = false
			}
		},

		async searchRecipes() {
			const q = this.searchQuery.trim()
			if (!q) return
			this.searchLoading = true
			this.searchPerformed = true
			this.error = null
			try {
				const res = await uni.request({
					url: getApiBase() + "/recipes/search?q=" + encodeURIComponent(q) + "&limit=20",
					method: "GET",
					timeout: 10000
				})
				if (res.statusCode === 200 && res.data && res.data.results) {
					this.searchResults = res.data.results.map(r => ({
						...r,
						image: getRecipeImage(r.name) || FALLBACK_IMG,
					}))
				} else {
					this.searchResults = []
				}
			} catch (e) {
				console.warn("[Recipes] Search failed:", e.message || e)
				this.searchResults = []
			} finally {
				this.searchLoading = false
			}
		},

		async openSearchResult(recipe) {
			try {
				const res = await uni.request({
					url: getApiBase() + '/recipes/' + recipe.id,
					method: 'GET',
					timeout: 10000
				})
				if (res.statusCode === 200 && res.data) {
					const detail = res.data
					this.activeRecipe = {
						...detail,
						image: this.resolveImage(detail.image, detail.name),
						calories: detail.calories || '--',
						matchCount: 0,
						ownedIngredients: [],
						missingIngredients: (detail.ingredients || []).map(i => typeof i === 'string' ? i : (i.name || '')),
						ingredients: (detail.ingredients || []).map(i => typeof i === 'string' ? i : (i.name || ''))
					}
					return
				}
			} catch (e) {
				console.warn("[Recipes] Fetch detail failed:", e.message || e)
			}
			this.activeRecipe = {
				...recipe,
				image: getRecipeImage(recipe.name) || FALLBACK_IMG,
				calories: '--',
				matchCount: 0,
				ownedIngredients: [],
				missingIngredients: [],
				ingredients: [],
				steps: [],
				tags: [],
				time: recipe.time || '未知',
				difficulty: recipe.difficulty || '未知'
			}
		},

		onLoad() { this.fetchRecommend() },
		onShow() { if (this.recommendRecipes.length === 0 && !this.loading) this.fetchRecommend() },

		isIngredientOwned(recipeIng) {
			const ingName = typeof recipeIng === 'string' ? recipeIng : (recipeIng.name || '')
			if (this.isServerMode && this.activeRecipe) {
				return this.activeRecipe.ownedIngredients.some(
					o => o.includes(ingName) || ingName.includes(o)
				)
			}
			const keywords = buildOwnedKeywords()
			return matchIngredient(ingName, keywords)
		},

		isIngredientOwnedInRecipe(recipe, ing) {
			if (this.isServerMode) {
				return recipe.ownedIngredients.some(
					o => o.includes(ing) || ing.includes(o)
				)
			}
			const keywords = buildOwnedKeywords()
			return matchIngredient(ing, keywords)
		},

		getMatchLevel(recipe) {
			if (!recipe.ingredients || recipe.ingredients.length === 0) return 'low'
			const ratio = recipe.matchCount / recipe.ingredients.length
			if (ratio >= 0.8) return 'high'
			if (ratio >= 0.5) return 'mid'
			return 'low'
		},

		filterByTag(tag) {
			this.activeTag = this.activeTag === tag ? '' : tag
		},

		openRecipe(recipe) {
			this.activeRecipe = { ...recipe, image: this.resolveImage(recipe.image, recipe.name) }
		},

		closeRecipe() {
			this.activeRecipe = null
		},
	},
}
</script>

<style scoped>
.page-shell {
	flex: 1;
	display: flex;
	flex-direction: column;
	height: 100%;
	overflow: hidden;
	background: #0d1117;
}

.page {
	flex: 1;
	overflow-y: auto;
	-webkit-overflow-scrolling: touch;
}

/* ===== Header ===== */
.recipe-header {
	padding: 16px 20px 0;
}
.recipe-title {
	font-size: 28px;
	font-weight: 900;
	color: #f0f0f0;
	letter-spacing: -0.5px;
	display: block;
}
.recipe-sub {
	font-size: 13px;
	color: #8b949e;
	margin-top: 4px;
	display: block;
}

/* ===== Stats Bar ===== */
.stats-bar {
	display: flex;
	gap: 10px;
	padding: 16px 20px;
}

.stat-card {
	flex: 1;
	display: flex;
	align-items: center;
	gap: 10px;
	background: rgba(255, 255, 255, 0.04);
	border: 1px solid rgba(255, 255, 255, 0.06);
	border-radius: 14px;
	padding: 12px 14px;
}

.stat-icon-box {
	width: 40px;
	height: 40px;
	border-radius: 12px;
	display: flex;
	align-items: center;
	justify-content: center;
	flex-shrink: 0;
}
.stat-icon-box .material-icons {
	font-size: 20px !important;
}
.icon-food {
	background: rgba(0, 212, 255, 0.12);
}
.icon-food .material-icons {
	color: #00d4ff;
}
.icon-cook {
	background: rgba(168, 85, 247, 0.12);
}
.icon-cook .material-icons {
	color: #a855f7;
}
.icon-rate {
	background: rgba(34, 197, 94, 0.12);
}
.icon-rate .material-icons {
	color: #22c55e;
}

.stat-body {
	display: flex;
	flex-direction: column;
	min-width: 0;
}
.stat-body .stat-value {
	font-size: 20px;
	font-weight: 800;
	color: #f0f0f0;
	line-height: 1.1;
}
.stat-body .stat-value.highlight {
	color: #a855f7;
}
.stat-body .stat-value.green {
	color: #22c55e;
}
.stat-body .stat-label {
	font-size: 11px;
	color: #8b949e;
	margin-top: 2px;
}

/* ===== Tab Bar ===== */
.tab-bar {
	display: flex;
	margin: 0 20px 16px;
	background: rgba(255, 255, 255, 0.03);
	border: 1px solid rgba(255, 255, 255, 0.06);
	border-radius: 14px;
	padding: 4px;
}

.tab-item {
	flex: 1;
	display: flex;
	align-items: center;
	justify-content: center;
	gap: 6px;
	padding: 10px 0;
	border-radius: 11px;
	font-size: 13px;
	font-weight: 600;
	color: #8b949e;
	transition: all 0.25s ease;
}

.tab-item.active {
	background: rgba(0, 212, 255, 0.12);
	color: #00d4ff;
	box-shadow: 0 0 12px rgba(0, 212, 255, 0.08);
}

.tab-icon {
	font-size: 17px !important;
}

/* ===== Section ===== */
.section {
	padding: 0 20px 20px;
}

.section-title {
	font-size: 15px;
	font-weight: 700;
	color: #e0e0e0;
	margin-bottom: 12px;
	display: block;
}

/* ===== Horizontal Scroll Cards ===== */
.h-scroll {
	white-space: nowrap;
	width: 100%;
	padding-bottom: 4px;
}

.card-h {
	display: inline-block;
	width: 170px;
	margin-right: 12px;
	vertical-align: top;
	background: rgba(255, 255, 255, 0.03);
	border: 1px solid rgba(255, 255, 255, 0.06);
	border-radius: 16px;
	overflow: hidden;
	transition: transform 0.2s ease;
}
.card-h:active {
	transform: scale(0.97);
}

.card-h-img-wrap {
	position: relative;
}
.card-h-img {
	width: 100%;
	height: 140px;
	object-fit: cover;
	display: block;
}
.card-h-badge {
	position: absolute;
	top: 8px;
	right: 8px;
	padding: 3px 10px;
	border-radius: 10px;
	font-size: 10px;
	font-weight: 700;
	backdrop-filter: blur(10px);
	-webkit-backdrop-filter: blur(10px);
}
.card-h-badge.high {
	color: #22c55e;
	background: rgba(34, 197, 94, 0.2);
}
.card-h-badge.mid {
	color: #f59e0b;
	background: rgba(245, 158, 11, 0.2);
}
.card-h-badge.low {
	color: #ef4444;
	background: rgba(239, 68, 68, 0.2);
}

.card-h-body {
	padding: 12px;
}
.card-h-name {
	font-size: 14px;
	font-weight: 700;
	color: #e0e0e0;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	display: block;
}
.card-h-meta {
	display: flex;
	align-items: center;
	gap: 4px;
	margin-top: 6px;
	font-size: 11px;
	color: #8b949e;
}

.meta-sep {
	color: #484f58;
	margin: 0 2px;
}

/* ===== Recipe Grid (2 cols) ===== */
.recipe-grid {
	display: flex;
	flex-wrap: wrap;
	gap: 12px;
	padding: 0 20px 16px;
}

.card-v {
	width: calc(50% - 6px);
	background: rgba(255, 255, 255, 0.03);
	border: 1px solid rgba(255, 255, 255, 0.06);
	border-radius: 16px;
	overflow: hidden;
	transition: transform 0.2s ease;
}
.card-v:active {
	transform: scale(0.97);
}

.card-v-img {
	width: 100%;
	height: 130px;
	object-fit: cover;
	display: block;
}

.card-v-body {
	padding: 10px 12px 12px;
}

.card-v-name {
	font-size: 14px;
	font-weight: 700;
	color: #e0e0e0;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	display: block;
}

.card-v-ingredients {
	display: flex;
	flex-wrap: wrap;
	gap: 4px;
	margin-top: 8px;
}

.ing-chip {
	padding: 2px 7px;
	border-radius: 6px;
	font-size: 10px;
	font-weight: 500;
	color: #8b949e;
	background: rgba(255, 255, 255, 0.04);
	border: 1px solid rgba(255, 255, 255, 0.05);
}
.ing-chip.owned {
	color: #00d4ff;
	background: rgba(0, 212, 255, 0.08);
	border-color: rgba(0, 212, 255, 0.15);
}
.ing-more {
	font-size: 10px;
	color: #8b949e;
	padding: 2px 4px;
}

.card-v-footer {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-top: 10px;
}

.match-tag {
	padding: 2px 8px;
	border-radius: 8px;
	font-size: 10px;
	font-weight: 700;
	white-space: nowrap;
}
.match-tag.high {
	color: #22c55e;
	background: rgba(34, 197, 94, 0.1);
}
.match-tag.mid {
	color: #f59e0b;
	background: rgba(245, 158, 11, 0.1);
}
.match-tag.low {
	color: #ef4444;
	background: rgba(239, 68, 68, 0.1);
}

.cat-tag {
	padding: 2px 8px;
	border-radius: 8px;
	font-size: 10px;
	font-weight: 600;
	color: #00d4ff;
	background: rgba(0, 212, 255, 0.08);
	border: 1px solid rgba(0, 212, 255, 0.12);
}

.card-v-time {
	font-size: 11px;
	color: #8b949e;
}

.card-v-meta {
	font-size: 11px;
	color: #8b949e;
	display: flex;
	align-items: center;
	gap: 2px;
}

/* ===== Search ===== */
.search-mode-row {
	display: flex;
	gap: 8px;
	padding: 0 20px 12px;
}

.mode-chip {
	padding: 7px 18px;
	border-radius: 20px;
	font-size: 12px;
	font-weight: 600;
	color: #8b949e;
	background: rgba(255, 255, 255, 0.04);
	border: 1px solid rgba(255, 255, 255, 0.06);
	transition: all 0.25s ease;
}
.mode-chip.active {
	color: #00d4ff;
	background: rgba(0, 212, 255, 0.1);
	border-color: rgba(0, 212, 255, 0.2);
}

.search-box {
	padding: 0 20px 16px;
}

.search-input-row {
	display: flex;
	align-items: center;
	gap: 10px;
	background: rgba(255, 255, 255, 0.04);
	border: 1px solid rgba(255, 255, 255, 0.08);
	border-radius: 14px;
	padding: 10px 14px;
}

.search-icon {
	font-size: 18px !important;
	color: #8b949e;
	flex-shrink: 0;
}

.search-field {
	flex: 1;
	font-size: 14px;
	color: #e0e0e0;
	border: none;
	background: transparent;
	outline: none;
}
.search-field::placeholder {
	color: #484f58;
	font-size: 13px;
}

.search-btn {
	padding: 8px 18px;
	border-radius: 10px;
	font-size: 13px;
	font-weight: 700;
	color: #fff;
	background: linear-gradient(135deg, #00d4ff, #0098ff);
	flex-shrink: 0;
}
.search-btn.accent {
	background: linear-gradient(135deg, #a855f7, #7c3aed);
}
.search-btn:active {
	opacity: 0.8;
	transform: scale(0.97);
}

/* ===== Tag Scroll ===== */
.tag-scroll {
	display: flex;
	gap: 8px;
	white-space: nowrap;
	padding: 0 20px 14px;
}

.tag-chip {
	display: inline-flex;
	flex-shrink: 0;
	padding: 7px 16px;
	border-radius: 20px;
	font-size: 12px;
	font-weight: 600;
	color: #8b949e;
	background: rgba(255, 255, 255, 0.04);
	border: 1px solid rgba(255, 255, 255, 0.06);
	transition: all 0.25s ease;
}

.tag-chip.active {
	color: #00d4ff;
	background: rgba(0, 212, 255, 0.12);
	border-color: rgba(0, 212, 255, 0.25);
	box-shadow: 0 0 12px rgba(0, 212, 255, 0.08);
}

/* ===== Loading ===== */
.loading-state {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	padding: 40px 20px;
	gap: 12px;
}

.loading-spinner {
	width: 32px;
	height: 32px;
	border: 3px solid rgba(0, 212, 255, 0.15);
	border-top-color: #00d4ff;
	border-radius: 50%;
	animation: spin 0.8s linear infinite;
}

@keyframes spin {
	to { transform: rotate(360deg); }
}

.loading-text {
	font-size: 13px;
	color: #8b949e;
}

/* ===== Empty State ===== */
.empty-state {
	display: flex;
	flex-direction: column;
	align-items: center;
	padding: 48px 20px;
}

.empty-icon {
	font-size: 52px !important;
	color: #30363d;
	margin-bottom: 12px;
}

.empty-text {
	font-size: 15px;
	color: #8b949e;
	font-weight: 600;
}

.empty-hint {
	font-size: 12px;
	color: #484f58;
	margin-top: 6px;
}

/* ===== Chat Section ===== */
.chat-section {
	padding: 0 20px 24px;
}
</style>
