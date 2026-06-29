<template>
	<view class="page-shell">
		<view class="page">
			<!-- Header -->
			<view class="recipe-header">
				<text class="recipe-title">智能食谱</text>
				<text class="recipe-sub">基于冰箱食材，为你推荐能做的美味</text>
			</view>

			<!-- ===== Module 1: 冰箱食材统计信息 ===== -->
			<view class="module module-stats">
				<!-- Corner brackets -->
				<view class="corner corner-tl"></view>
				<view class="corner corner-tr"></view>
				<view class="corner corner-bl"></view>
				<view class="corner corner-br"></view>
				<!-- Scan line -->
				<view class="stats-scanline"></view>
				<!-- Data particles -->
				<view class="particle p1"></view>
				<view class="particle p2"></view>
				<view class="particle p3"></view>

				<view class="module-header stats-header">
					<view class="stats-header-icon">
						<text class="material-icons module-icon">memory</text>
						<view class="pulse-ring"></view>
					</view>
					<view>
						<view class="stats-title-row">
							<text class="module-title">冰箱食材统计</text>
							<view class="live-badge">
								<view class="live-dot"></view>
								<text>实时</text>
							</view>
						</view>
						<text class="module-desc">当前冰箱库存智能监控面板</text>
					</view>
				</view>

				<view class="stats-row">
					<view class="stat-item">
						<view class="stat-ring ring-cyan">
							<view class="ring-inner">
								<text class="stat-value stat-gradient-cyan">{{ totalFoods }}</text>
								<text class="stat-unit">种</text>
							</view>
						</view>
						<text class="stat-label">食材种类</text>
					</view>
					<view class="stat-item">
						<view class="stat-ring ring-purple">
							<view class="ring-inner">
								<text class="stat-value stat-gradient-purple">{{ matchedRecipes.length }}</text>
								<text class="stat-unit">道</text>
							</view>
						</view>
						<text class="stat-label">可做菜谱</text>
					</view>
					<view class="stat-item">
						<view class="stat-ring ring-green">
							<view class="ring-inner">
								<text class="stat-value stat-gradient-green">{{ matchPercent }}</text>
								<text class="stat-unit">%</text>
							</view>
						</view>
						<text class="stat-label">覆盖率</text>
					</view>
				</view>

				<!-- Data bars -->
				<view class="stats-bars">
					<view class="data-bar-row">
						<text class="data-bar-label">食材库存</text>
						<view class="data-bar-track">
							<view class="data-bar-fill bar-cyan" :style="{width: Math.min(totalFoods / 20 * 100, 100) + '%'}"></view>
						</view>
					</view>
					<view class="data-bar-row">
						<text class="data-bar-label">菜谱匹配</text>
						<view class="data-bar-track">
							<view class="data-bar-fill bar-purple" :style="{width: Math.min(matchedRecipes.length / Math.max(allRecipes.length, 1) * 100, 100) + '%'}"></view>
						</view>
					</view>
					<view class="data-bar-row">
						<text class="data-bar-label">综合覆盖</text>
						<view class="data-bar-track">
							<view class="data-bar-fill bar-green" :style="{width: matchPercent + '%'}"></view>
						</view>
					</view>
				</view>
			</view>

			<!-- ===== Module 2: 搜索菜谱 ===== -->
			<view class="module">
				<view class="module-header">
					<text class="material-icons module-icon">search</text>
					<view>
						<text class="module-title">搜索菜谱</text>
						<text class="module-desc">按菜名搜索，查看详细做法</text>
					</view>
				</view>

				<view class="search-row">
					<view class="search-input-box">
						<text class="material-icons search-input-icon">search</text>
						<input
							v-model="searchQuery"
							class="search-input-field"
							placeholder="输入菜名（如 红烧肉、宫保鸡丁）"
							confirm-type="search"
							@confirm="searchRecipes"
						/>
					</view>
					<view class="action-btn" @click="searchRecipes">
						<text>搜索</text>
					</view>
				</view>

				<!-- Search Loading -->
				<view v-if="searchLoading" class="loading-state">
					<text class="material-icons loading-icon">hourglass_top</text>
					<text class="loading-text">搜索中...</text>
				</view>

				<!-- Search Results -->
				<view v-if="!searchLoading && searchPerformed && searchResults.length > 0" class="recipe-list">
					<view
						v-for="r in searchResults"
						:key="r.id"
						class="recipe-card-v"
						@click="openSearchResult(r)"
					>
						<image :src="r.image || fallbackImg" mode="aspectFill" class="recipe-img-v" />
						<view class="recipe-card-v-body">
							<view class="recipe-card-v-top">
								<text class="recipe-name-v">{{ r.name }}</text>
								<view class="recipe-cat-tag">
									<text>{{ r.category || '其他' }}</text>
								</view>
							</view>
							<view class="recipe-card-v-bottom">
								<view class="recipe-stat">
									<text class="material-icons" style="font-size:13px;color:var(--text-muted);">speed</text>
									<text>{{ r.difficulty || '未知' }}</text>
								</view>
							</view>
						</view>
					</view>
				</view>

				<view v-if="!searchLoading && searchPerformed && searchResults.length === 0" class="empty-state">
					<text class="material-icons empty-icon">search_off</text>
					<text class="empty-text">未找到相关菜谱</text>
					<text class="empty-hint">试试其他关键词</text>
				</view>
			</view>

			<!-- ===== Module 3: 搜索食材 ===== -->
			<view class="module">
				<view class="module-header">
					<text class="material-icons module-icon">auto_awesome</text>
					<view>
						<text class="module-title">搜索食材</text>
						<text class="module-desc">输入你想用的食材，智能推荐可做菜谱</text>
					</view>
				</view>

				<view class="search-row">
					<view class="search-input-box">
						<text class="material-icons search-input-icon">restaurant</text>
						<input
							v-model="ingredientQuery"
							class="search-input-field"
							placeholder="输入食材，逗号分隔（如 鸡胸肉, 西红柿）"
							confirm-type="search"
							@confirm="fetchIngredientSearch"
						/>
					</view>
					<view class="action-btn" @click="fetchIngredientSearch">
						<text class="material-icons" style="font-size:14px;">auto_awesome</text>
						<text>推荐</text>
					</view>
				</view>

				<!-- Ingredient Search Loading -->
				<view v-if="ingredientLoading" class="loading-state">
					<text class="material-icons loading-icon">hourglass_top</text>
					<text class="loading-text">AI 正在匹配菜谱...</text>
				</view>

				<!-- Ingredient Search Results -->
				<view v-if="!ingredientLoading && ingredientSearched && ingredientResults.length > 0" class="recipe-list">
					<view
						v-for="r in ingredientResults"
						:key="r.id"
						class="recipe-card-v"
						@click="openRecipe(r)"
					>
						<image :src="r.image" mode="aspectFill" class="recipe-img-v" />
						<view class="recipe-card-v-body">
							<view class="recipe-card-v-top">
								<text class="recipe-name-v">{{ r.name }}</text>
								<view class="match-badge-v" :class="getMatchLevel(r)">
									<text>{{ r.matchCount }}/{{ r.ingredients.length }} 种</text>
								</view>
							</view>
							<view class="recipe-ingredients">
								<text
									v-for="ing in r.ingredients"
									:key="ing"
									class="ing-tag"
									:class="{ owned: isIngredientOwnedInRecipe(r, ing) }"
								>{{ ing }}</text>
							</view>
							<view class="recipe-card-v-bottom">
								<view class="recipe-stat">
									<text class="material-icons" style="font-size:13px;color:var(--text-muted);">schedule</text>
									<text>{{ r.time }}</text>
								</view>
								<view class="recipe-stat">
									<text class="material-icons" style="font-size:13px;color:var(--text-muted);">speed</text>
									<text>{{ r.difficulty }}</text>
								</view>
							</view>
						</view>
					</view>
				</view>

				<view v-if="!ingredientLoading && ingredientSearched && ingredientResults.length === 0" class="empty-state">
					<text class="material-icons empty-icon">search_off</text>
					<text class="empty-text">未找到匹配的菜谱</text>
					<text class="empty-hint">试试调整食材组合</text>
				</view>
			</view>

			<!-- ===== Module 4: AI 冰箱推荐 ===== -->
			<view class="module">
				<view class="module-header">
					<text class="material-icons module-icon">stars</text>
					<view>
						<text class="module-title">AI 冰箱推荐</text>
						<text class="module-desc">根据冰箱现有食材，智能推荐最佳匹配菜谱</text>
					</view>
				</view>

				<view v-if="loading" class="loading-state">
					<text class="material-icons loading-icon">hourglass_top</text>
					<text class="loading-text">AI 正在分析冰箱食材...</text>
				</view>

				<view v-if="!loading && topMatches.length > 0" class="recipe-h-scroll-wrap">
					<scroll-view scroll-x class="recipe-h-scroll" :show-scrollbar="false">
						<view
							v-for="recipe in topMatches"
							:key="recipe.id"
							class="recipe-card-h"
							@click="openRecipe(recipe)"
						>
							<image :src="recipe.image" mode="aspectFill" class="recipe-img-h" />
							<view class="recipe-card-h-overlay">
								<view class="match-badge-h" :class="getMatchLevel(recipe)">
									<text>{{ recipe.matchCount }}/{{ recipe.ingredients.length }} 种</text>
								</view>
							</view>
							<view class="recipe-card-h-body">
								<text class="recipe-name-h">{{ recipe.name }}</text>
								<view class="recipe-meta-h">
									<text class="material-icons" style="font-size:12px;color:var(--text-muted);">schedule</text>
									<text>{{ recipe.time }}</text>
									<text class="recipe-dot">·</text>
									<text>{{ recipe.difficulty }}</text>
								</view>
							</view>
						</view>
					</scroll-view>
				</view>

				<view v-if="!loading && topMatches.length === 0" class="empty-state">
					<text class="material-icons empty-icon">kitchen</text>
					<text class="empty-text">冰箱里还没有食材</text>
					<text class="empty-hint">添加食材后自动推荐可做菜谱</text>
				</view>
			</view>

			<!-- ===== Module 5: 食谱列表 ===== -->
			<view class="module">
				<view class="module-header">
					<text class="material-icons module-icon">restaurant_menu</text>
					<view>
						<text class="module-title">食谱列表</text>
						<text class="module-desc">{{ activeTag ? activeTag + ' · ' : '' }}共 {{ filteredRecipes.length }} 道可做菜谱</text>
					</view>
				</view>

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

				<view v-if="!loading && filteredRecipes.length > 0" class="recipe-list">
					<view
						v-for="recipe in filteredRecipes"
						:key="recipe.id"
						class="recipe-card-v"
						@click="openRecipe(recipe)"
					>
						<image :src="recipe.image" mode="aspectFill" class="recipe-img-v" />
						<view class="recipe-card-v-body">
							<view class="recipe-card-v-top">
								<text class="recipe-name-v">{{ recipe.name }}</text>
								<view class="match-badge-v" :class="getMatchLevel(recipe)">
									<text>{{ recipe.matchCount }}/{{ recipe.ingredients.length }} 种</text>
								</view>
							</view>
							<view class="recipe-ingredients">
								<text
									v-for="ing in recipe.ingredients"
									:key="ing"
									class="ing-tag"
									:class="{ owned: isIngredientOwnedInRecipe(recipe, ing) }"
								>{{ ing }}</text>
							</view>
							<view class="recipe-card-v-bottom">
								<view class="recipe-stat">
									<text class="material-icons" style="font-size:13px;color:var(--text-muted);">schedule</text>
									<text>{{ recipe.time }}</text>
								</view>
								<view class="recipe-stat">
									<text class="material-icons" style="font-size:13px;color:var(--text-muted);">restaurant</text>
									<text>{{ recipe.difficulty }}</text>
								</view>
								<view class="recipe-stat">
									<text class="material-icons" style="font-size:13px;color:var(--text-muted);">local_fire_department</text>
									<text>{{ recipe.calories }}</text>
								</view>
							</view>
						</view>
					</view>
				</view>

				<view v-if="!loading && filteredRecipes.length === 0" class="empty-state">
					<text class="material-icons empty-icon">search_off</text>
					<text class="empty-text">没有匹配的食谱</text>
					<text class="empty-hint">试试添加更多食材到冰箱</text>
				</view>
			</view>
		</view>

		<!-- ============ Recipe Detail Modal ============ -->
		<view v-if="activeRecipe" class="modal-overlay" @click="closeRecipe">
			<view class="modal-sheet" @click.stop>
				<image v-if="activeRecipe.image" :src="activeRecipe.image" mode="aspectFill" class="modal-img" />

				<view class="modal-header">
					<view class="modal-title-row">
						<text class="modal-name">{{ activeRecipe.name }}</text>
						<view
							v-if="!activeRecipe.ownedIngredients || activeRecipe.ownedIngredients.length > 0"
							class="match-badge-v"
							:class="getMatchLevel(activeRecipe)"
						>
							<text>{{ activeRecipe.matchCount }}/{{ activeRecipe.ingredients.length }} 种食材</text>
						</view>
					</view>
					<view class="modal-meta">
						<view class="meta-item">
							<text class="material-icons meta-icon">schedule</text>
							<text>{{ activeRecipe.time }}</text>
						</view>
						<view class="meta-item">
							<text class="material-icons meta-icon">local_fire_department</text>
							<text>{{ activeRecipe.calories }}</text>
						</view>
						<view class="meta-item">
							<text class="material-icons meta-icon">speed</text>
							<text>{{ activeRecipe.difficulty }}</text>
						</view>
					</view>
				</view>

				<view class="modal-divider"></view>

				<view class="modal-section">
					<text class="modal-section-title">
						<text class="material-icons" style="font-size:16px;color:var(--accent-cyan);">checklist</text>
						所需食材
					</text>
					<view class="modal-ingredients">
						<view
							v-for="ing in activeRecipe.ingredients"
							:key="typeof ing === 'string' ? ing : (ing.name || ing)"
							class="modal-ing-chip"
							:class="{ owned: isIngredientOwned(ing), missing: !isIngredientOwned(ing) }"
						>
							<text class="material-icons ing-status-icon">
								{{ isIngredientOwned(ing) ? 'check_circle' : 'cancel' }}
							</text>
							<text>{{ typeof ing === 'string' ? ing : (ing.name || '') }}</text>
							<text v-if="isIngredientOwned(ing)" class="ing-label">已有</text>
							<text v-else class="ing-label missing-label">缺少</text>
						</view>
					</view>
				</view>

				<view class="modal-section">
					<text class="modal-section-title">
						<text class="material-icons" style="font-size:16px;color:var(--accent-cyan);">menu_book</text>
						制作流程
					</text>
					<view class="steps-list">
						<view v-for="(step, idx) in activeRecipe.steps" :key="idx" class="step-item">
							<view class="step-num">{{ idx + 1 }}</view>
							<text class="step-text">{{ step }}</text>
						</view>
					</view>
				</view>

				<view class="modal-close-btn" @click="closeRecipe">
					<text>关闭</text>
				</view>
			</view>
		</view>

	</view>
		</view>

		<!-- ============ Phase 8: Agent 聊天模块 ============ -->
		<view class="module module-chat">
			<view class="corner corner-tl"></view>
			<view class="corner corner-tr"></view>
			<view class="corner corner-bl"></view>
			<view class="corner corner-br"></view>

			<view class="module-header">
				<view class="stats-header-icon">
					<text class="material-icons module-icon">psychology</text>
					<view class="pulse-ring" :class="{ active: chatStreaming }"></view>
				</view>
				<view>
					<view class="stats-title-row">
						<text class="module-title">AI 对话</text>
						<view class="live-badge" v-if="chatConnected">
							<view class="live-dot"></view>
							<text>在线</text>
						</view>
					</view>
					<text class="module-desc">告诉冰箱你想吃什么，AI 帮你推荐</text>
				</view>
			</view>

			<!-- 流式输出中 -->
			<view v-if="chatStreaming && chatStreamText" class="chat-stream-box">
				<text class="chat-cursor">|</text>
				<text class="chat-stream-text">{{ chatStreamText }}</text>
			</view>

			<!-- 工具状态 -->
			<view v-if="chatToolStatus" class="chat-tool-status">
				<text class="material-icons" style="font-size:14px;">build</text>
				<text>{{ chatToolStatus }}</text>
			</view>

			<!-- 快捷提问 -->
			<view class="chat-quick-actions" v-if="chatMessages.length === 0 && !chatStreaming">
				<text class="quick-label">试试问：</text>
				<view class="quick-btns">
					<view class="quick-btn" @click="sendQuickChat('能做什么菜?')">能做什么菜?</view>
					<view class="quick-btn" @click="sendQuickChat('推荐3道简单快手的菜')">推荐3道快手菜</view>
					<view class="quick-btn" @click="sendQuickChat('冰箱里有什么?')">冰箱里有什么?</view>
				</view>
			</view>

			<!-- 输入区 -->
			<view class="chat-input-row">
				<input class="chat-input" v-model="chatInput" placeholder="告诉冰箱你想吃什么..."
					:disabled="chatStreaming" @confirm="sendChat" />
				<view class="chat-send-btn" :class="{ disabled: chatStreaming || !chatInput.trim() }"
					@click="sendChat">
					<text class="material-icons" style="font-size:20px;color:#fff;">send</text>
				</view>
			</view>
		</view>

</template>

<script>
import { store } from '@/utils/store.js'
import { connectAgentChat, sendAgentMessage, onAgentChat, offAgentChat, disconnectAgentChat } from '@/utils/agentChat.js'  # Phase 8

import { getRecipeImage, getIngredientImage, FALLBACK_RECIPE, FALLBACK_FOOD } from '@/utils/imageResolver.js'

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
	// Fix #5: 循环去除前缀，而非只去一层
	// 原有逻辑: name.replace(/^(有机|鲜|...)/, '') → 只去一层，"有机鲜牛奶"→"鲜牛奶"
	// 修复后: 循环去除直到没有更多前缀可去，"有机鲜牛奶"→"鲜牛奶"→"牛奶"
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
	// Fix #6: 精确优先匹配，子串匹配作为回退
	// 原有逻辑: kw.includes(alias) || alias.includes(kw) → "鸡"匹配"鸡精"/"火鸡"
	// 修复后: 先尝试精确别名匹配，再尝试边界感知子串匹配
	const aliases = INGREDIENT_ALIASES[recipeIng]
	const ownedArr = [...ownedKeywords]

	if (aliases) {
		// 优先级1: 精确别名匹配 (owned keyword 与 alias 完全相等)
		if (aliases.some(alias => ownedArr.some(kw => kw === alias))) {
			return true
		}
		// 优先级2: 单字别名字串匹配加长度校验
		// "鸡"只匹配单字食材，不匹配"鸡精""火鸡"
		return aliases.some(alias => {
			return ownedArr.some(kw => {
				if (kw === alias) return true
				if (alias.length <= 1) return false  // 单字不过滤
				if (kw.length <= 1) return false
				if (alias.length >= 3 && kw.length >= 3) {
					return kw.includes(alias) || alias.includes(kw)
				}
				return false
			})
		})
	}

	// 无别名表: 保守子串匹配 (双方长度都 ≥2 才生效)
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

	data() {
		return {
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
		}
	},
	computed: {
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
			return this.matchedRecipes.filter(r => r.matchCount >= 2).slice(0, 8)
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

		onLoad() { this.fetchRecommend(); this.initAgentChat() },
		onUnload() { disconnectAgentChat() },
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
	display: flex;
	flex-direction: column;
	height: 100%;
	overflow: hidden;
	background: var(--bg-deep);
}
.page {
	flex: 1;
	padding: 0 20px;
	overflow-y: auto;
	-webkit-overflow-scrolling: touch;
}

/* Header */
.recipe-header { padding: 8px 0 16px; }
.recipe-title {
	font-size: 28px;
	font-weight: 900;
	color: var(--text-primary);
	letter-spacing: -0.5px;
	display: block;
}
.recipe-sub {
	font-size: 13px;
	color: var(--text-secondary);
	margin-top: 4px;
	display: block;
}

/* ===== Module ===== */
.module {
	background: var(--bg-card);
	backdrop-filter: var(--glass-blur);
	-webkit-backdrop-filter: var(--glass-blur);
	border: 1px solid var(--border-card);
	border-radius: var(--radius-lg);
	padding: 20px;
	margin-bottom: 20px;
}
/* ===== Module 1: Tech Stats Dashboard ===== */
.module-stats {
	position: relative;
	background:
		/* hex grid pattern */
		url("data:image/svg+xml,%3Csvg width='60' height='52' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M30 0L60 15v22l-30 15L0 37V15z' fill='none' stroke='rgba(0,212,255,0.04)' stroke-width='0.5'/%3E%3C/svg%3E") repeat,
		radial-gradient(ellipse at 50% 0%, rgba(0, 212, 255, 0.1) 0%, transparent 60%),
		radial-gradient(ellipse at 80% 100%, rgba(124, 58, 237, 0.06) 0%, transparent 50%),
		linear-gradient(180deg, rgba(8, 12, 20, 0.97) 0%, rgba(12, 18, 30, 0.95) 100%);
	border: 1px solid rgba(0, 212, 255, 0.15);
	border-radius: var(--radius-lg);
	box-shadow:
		0 0 40px rgba(0, 212, 255, 0.06),
		0 0 80px rgba(0, 212, 255, 0.03),
		0 8px 32px rgba(0, 0, 0, 0.5),
		inset 0 1px 0 rgba(255, 255, 255, 0.02);
	overflow: hidden;
}

/* Corner brackets */
.corner {
	position: absolute;
	width: 20px; height: 20px;
	z-index: 3;
	pointer-events: none;
}
.corner::before, .corner::after {
	content: '';
	position: absolute;
	background: rgba(0, 212, 255, 0.4);
	box-shadow: 0 0 6px rgba(0, 212, 255, 0.3);
}
.corner-tl { top: 8px; left: 8px; }
.corner-tl::before { top: 0; left: 0; width: 12px; height: 1px; }
.corner-tl::after  { top: 0; left: 0; width: 1px; height: 12px; }
.corner-tr { top: 8px; right: 8px; }
.corner-tr::before { top: 0; right: 0; width: 12px; height: 1px; }
.corner-tr::after  { top: 0; right: 0; width: 1px; height: 12px; }
.corner-bl { bottom: 8px; left: 8px; }
.corner-bl::before { bottom: 0; left: 0; width: 12px; height: 1px; }
.corner-bl::after  { bottom: 0; left: 0; width: 1px; height: 12px; }
.corner-br { bottom: 8px; right: 8px; }
.corner-br::before { bottom: 0; right: 0; width: 12px; height: 1px; }
.corner-br::after  { bottom: 0; right: 0; width: 1px; height: 12px; }

/* Scan line */
.stats-scanline {
	position: absolute;
	top: 0; left: 0; right: 0;
	height: 2px;
	background: linear-gradient(90deg, transparent, rgba(0, 212, 255, 0.5), rgba(124, 58, 237, 0.3), transparent);
	animation: scanline-sweep 5s ease-in-out infinite;
	pointer-events: none;
	z-index: 4;
}
@keyframes scanline-sweep {
	0%, 100% { top: -2px; opacity: 0; }
	15% { opacity: 1; }
	85% { top: 100%; opacity: 0.3; }
}

/* Floating data particles */
.particle {
	position: absolute;
	width: 3px; height: 3px;
	border-radius: 50%;
	background: var(--accent-cyan);
	box-shadow: 0 0 6px var(--accent-cyan), 0 0 12px rgba(0, 212, 255, 0.5);
	pointer-events: none;
	z-index: 1;
}
.p1 { top: 25%; left: 10%; animation: particle-float 6s ease-in-out infinite; }
.p2 { top: 60%; right: 15%; animation: particle-float 8s ease-in-out 2s infinite; background: rgba(124, 58, 237, 0.8); box-shadow: 0 0 6px rgba(124, 58, 237, 0.8); }
.p3 { top: 40%; left: 75%; animation: particle-float 7s ease-in-out 4s infinite; background: rgba(0, 230, 118, 0.8); box-shadow: 0 0 6px rgba(0, 230, 118, 0.8); }
@keyframes particle-float {
	0%, 100% { transform: translateY(0) scale(1); opacity: 0.3; }
	50% { transform: translateY(-12px) scale(1.8); opacity: 1; }
}

/* Header */
.stats-header {
	border-bottom: 1px solid rgba(0, 212, 255, 0.08);
}
.stats-header-icon {
	position: relative;
	display: flex;
	align-items: center;
	justify-content: center;
}
.pulse-ring {
	position: absolute;
	width: 100%; height: 100%;
	border-radius: 50%;
	border: 1px solid rgba(0, 212, 255, 0.3);
	animation: pulse-ring-expand 2.5s ease-out infinite;
}
@keyframes pulse-ring-expand {
	0% { transform: scale(0.8); opacity: 0.8; }
	100% { transform: scale(2); opacity: 0; }
}
.stats-title-row {
	display: flex;
	align-items: center;
	gap: 10px;
}
.live-badge {
	display: flex;
	align-items: center;
	gap: 4px;
	padding: 2px 8px;
	border-radius: 10px;
	font-size: 9px;
	font-weight: 700;
	letter-spacing: 1px;
	color: var(--accent-green);
	background: rgba(0, 230, 118, 0.08);
	border: 1px solid rgba(0, 230, 118, 0.2);
}
.live-dot {
	width: 5px; height: 5px;
	border-radius: 50%;
	background: var(--accent-green);
	box-shadow: 0 0 4px var(--accent-green);
	animation: live-pulse 1s ease-in-out infinite;
}
@keyframes live-pulse {
	0%, 100% { opacity: 1; box-shadow: 0 0 4px var(--accent-green); }
	50% { opacity: 0.3; box-shadow: 0 0 2px var(--accent-green); }
}

.module-header {
	display: flex;
	align-items: center;
	gap: 12px;
	margin-bottom: 16px;
	padding-bottom: 14px;
	border-bottom: 1px solid rgba(255,255,255,0.06);
	position: relative;
	z-index: 2;
}
.module-icon {
	font-size: 26px !important;
	color: var(--accent-cyan);
	flex-shrink: 0;
}
.module-title {
	font-size: 16px;
	font-weight: 700;
	color: var(--text-primary);
	display: block;
}
.module-desc {
	font-size: 12px;
	color: var(--text-muted);
	display: block;
	margin-top: 2px;
}

/* ===== Stats Rings ===== */
.stats-row {
	display: flex;
	align-items: flex-start;
	justify-content: space-around;
	padding: 14px 0 6px;
	position: relative;
	z-index: 2;
}
.stat-item {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 12px;
	flex: 1;
}
.stat-ring {
	width: 82px; height: 82px;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	position: relative;
}
.ring-cyan {
	background: radial-gradient(circle at 40% 40%, rgba(0, 212, 255, 0.15) 0%, rgba(0, 0, 0, 0) 65%);
	border: 2px solid transparent;
	border-top-color: rgba(0, 212, 255, 0.5);
	border-right-color: rgba(0, 212, 255, 0.2);
	border-bottom-color: rgba(0, 212, 255, 0.08);
	border-left-color: rgba(0, 212, 255, 0.08);
	box-shadow: 0 0 24px rgba(0, 212, 255, 0.12), inset 0 0 16px rgba(0, 212, 255, 0.04);
}
.ring-purple {
	background: radial-gradient(circle at 40% 40%, rgba(124, 58, 237, 0.15) 0%, rgba(0, 0, 0, 0) 65%);
	border: 2px solid transparent;
	border-top-color: rgba(124, 58, 237, 0.5);
	border-right-color: rgba(124, 58, 237, 0.2);
	border-bottom-color: rgba(124, 58, 237, 0.08);
	border-left-color: rgba(124, 58, 237, 0.08);
	box-shadow: 0 0 24px rgba(124, 58, 237, 0.12), inset 0 0 16px rgba(124, 58, 237, 0.04);
}
.ring-green {
	background: radial-gradient(circle at 40% 40%, rgba(0, 230, 118, 0.15) 0%, rgba(0, 0, 0, 0) 65%);
	border: 2px solid transparent;
	border-top-color: rgba(0, 230, 118, 0.5);
	border-right-color: rgba(0, 230, 118, 0.2);
	border-bottom-color: rgba(0, 230, 118, 0.08);
	border-left-color: rgba(0, 230, 118, 0.08);
	box-shadow: 0 0 24px rgba(0, 230, 118, 0.12), inset 0 0 16px rgba(0, 230, 118, 0.04);
}
.ring-inner {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
}
.stat-value {
	font-size: 24px;
	font-weight: 900;
	line-height: 1;
	letter-spacing: -1px;
}
.stat-unit {
	font-size: 10px;
	font-weight: 600;
	margin-top: 1px;
}
.stat-gradient-cyan {
	background: linear-gradient(180deg, #00d4ff, #60e0ff);
	-webkit-background-clip: text;
	-webkit-text-fill-color: transparent;
	background-clip: text;
	filter: drop-shadow(0 0 8px rgba(0, 212, 255, 0.5));
}
.stat-gradient-purple {
	background: linear-gradient(180deg, #c4b5fd, #7c3aed);
	-webkit-background-clip: text;
	-webkit-text-fill-color: transparent;
	background-clip: text;
	filter: drop-shadow(0 0 8px rgba(124, 58, 237, 0.5));
}
.stat-gradient-green {
	background: linear-gradient(180deg, #4ade80, #00e676);
	-webkit-background-clip: text;
	-webkit-text-fill-color: transparent;
	background-clip: text;
	filter: drop-shadow(0 0 8px rgba(0, 230, 118, 0.5));
}
.stat-label {
	font-size: 12px;
	font-weight: 600;
	color: var(--text-secondary);
	letter-spacing: 0.5px;
}

/* ===== Data Bars ===== */
.stats-bars {
	display: flex;
	flex-direction: column;
	gap: 8px;
	padding: 10px 0 4px;
	position: relative;
	z-index: 2;
}
.data-bar-row {
	display: flex;
	align-items: center;
	gap: 10px;
}
.data-bar-label {
	width: 52px;
	font-size: 10px;
	font-weight: 600;
	color: var(--text-muted);
	text-align: right;
	flex-shrink: 0;
	letter-spacing: 0.5px;
}
.data-bar-track {
	flex: 1;
	height: 4px;
	border-radius: 2px;
	background: rgba(255, 255, 255, 0.04);
	overflow: hidden;
}
.data-bar-fill {
	height: 100%;
	border-radius: 2px;
	transition: width 0.8s cubic-bezier(0.16, 0.8, 0.32, 1);
	position: relative;
}
.data-bar-fill::after {
	content: '';
	position: absolute;
	top: 0; right: 0; bottom: 0;
	width: 20px;
	background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4));
	animation: bar-sheen 2s ease-in-out infinite;
}
@keyframes bar-sheen {
	0%, 100% { opacity: 0; }
	50% { opacity: 1; }
}
.bar-cyan {
	background: linear-gradient(90deg, rgba(0, 212, 255, 0.4), rgba(0, 212, 255, 0.8));
	box-shadow: 0 0 6px rgba(0, 212, 255, 0.3);
}
.bar-purple {
	background: linear-gradient(90deg, rgba(124, 58, 237, 0.4), rgba(124, 58, 237, 0.8));
	box-shadow: 0 0 6px rgba(124, 58, 237, 0.3);
}
.bar-green {
	background: linear-gradient(90deg, rgba(0, 230, 118, 0.4), rgba(0, 230, 118, 0.8));
	box-shadow: 0 0 6px rgba(0, 230, 118, 0.3);
}

/* ===== Action Button ===== */
.action-btn {
	display: flex;
	align-items: center;
	gap: 4px;
	background: linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(124, 58, 237, 0.12));
	border: 1px solid rgba(0, 212, 255, 0.25);
	border-radius: 14px;
	padding: 6px 14px;
	font-size: 12px;
	font-weight: 600;
	color: var(--accent-cyan);
	flex-shrink: 0;
	transition: var(--transition);
}
.action-btn:active {
	background: linear-gradient(135deg, rgba(0, 212, 255, 0.25), rgba(124, 58, 237, 0.2));
	transform: scale(0.96);
}

/* ===== Search Row ===== */
.search-row {
	display: flex;
	align-items: center;
	gap: 10px;
}
.search-input-box {
	flex: 1;
	display: flex;
	align-items: center;
	gap: 8px;
	background: rgba(255,255,255,0.04);
	border: 1px solid rgba(255,255,255,0.08);
	border-radius: var(--radius-md);
	padding: 10px 14px;
}
.search-input-icon {
	font-size: 18px !important;
	color: var(--text-muted);
	flex-shrink: 0;
}
.search-input-field {
	flex: 1;
	font-size: 14px;
	color: var(--text-primary);
	border: none;
	background: transparent;
	outline: none;
}
.search-input-field::placeholder {
	color: var(--text-muted);
	font-size: 13px;
}

/* ===== Recipe Category Tag ===== */
.recipe-cat-tag {
	padding: 2px 8px;
	border-radius: 10px;
	font-size: 10px;
	font-weight: 600;
	color: var(--accent-cyan);
	background: rgba(0, 212, 255, 0.08);
	border: 1px solid rgba(0, 212, 255, 0.15);
	white-space: nowrap;
	flex-shrink: 0;
}

/* ===== Loading State ===== */
.loading-state {
	text-align: center;
	padding: 28px 20px;
}
.loading-icon {
	font-size: 32px !important;
	color: var(--accent-cyan);
	display: block;
	margin-bottom: 8px;
	animation: spin 1.5s linear infinite;
}
@keyframes spin {
	from { transform: rotate(0deg); }
	to { transform: rotate(360deg); }
}
.loading-text {
	font-size: 13px;
	color: var(--text-secondary);
	display: block;
}

/* ===== Tag Scroll ===== */
.tag-scroll { display: flex; gap: 8px; white-space: nowrap; padding-bottom: 12px; }
.tag-chip {
	display: inline-flex;
	flex-shrink: 0;
	padding: 7px 16px;
	border-radius: 16px;
	font-size: 12px;
	font-weight: 600;
	color: var(--text-secondary);
	background: rgba(255,255,255,0.04);
	border: 1px solid rgba(255,255,255,0.08);
	transition: var(--transition);
}
.tag-chip.active {
	color: #fff;
	background: rgba(0, 212, 255, 0.15);
	border-color: var(--accent-cyan);
	box-shadow: 0 0 12px rgba(0, 212, 255, 0.1);
}

/* ===== Horizontal Cards (Module 4 Best Matches) ===== */
.recipe-h-scroll-wrap { margin-top: 4px; }
.recipe-h-scroll { white-space: nowrap; padding-bottom: 4px; width: 100%; }
.recipe-card-h {
	display: inline-block;
	width: 200px;
	margin-right: 12px;
	vertical-align: top;
	position: relative;
	background: rgba(255,255,255,0.03);
	border: 1px solid rgba(255,255,255,0.06);
	border-radius: var(--radius-lg);
	overflow: hidden;
	transition: var(--transition);
}
.recipe-card-h:active { transform: scale(0.97); }
.recipe-img-h { width: 100%; height: 130px; object-fit: cover; display: block; position: relative; }
.recipe-card-h-overlay {
	position: absolute;
	margin-top: -130px;
	padding: 10px;
	display: flex;
	justify-content: flex-end;
	width: 100%;
}
.match-badge-h {
	padding: 3px 10px;
	border-radius: 12px;
	font-size: 11px;
	font-weight: 700;
	backdrop-filter: blur(10px);
	-webkit-backdrop-filter: blur(10px);
}
.match-badge-h.high { color: var(--accent-green);  background: rgba(0,230,118,0.15); }
.match-badge-h.mid  { color: var(--accent-orange); background: rgba(245,158,11,0.15); }
.match-badge-h.low  { color: var(--accent-red);    background: rgba(239,68,68,0.15); }

.recipe-card-h-body { padding: 12px 14px; }
.recipe-name-h {
	font-size: 14px;
	font-weight: 700;
	color: var(--text-primary);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	display: block;
}
.recipe-meta-h {
	display: flex;
	align-items: center;
	gap: 4px;
	margin-top: 6px;
	font-size: 11px;
	color: var(--text-secondary);
}
.recipe-dot { color: var(--text-muted); margin: 0 2px; }

/* ===== Vertical Cards (List) ===== */
.recipe-list { display: flex; flex-direction: column; gap: 12px; padding-bottom: 4px; }
.recipe-card-v {
	display: flex;
	gap: 14px;
	background: rgba(255,255,255,0.03);
	border: 1px solid rgba(255,255,255,0.06);
	border-radius: var(--radius-md);
	overflow: hidden;
	padding: 12px;
	transition: var(--transition);
}
.recipe-card-v:active { transform: scale(0.98); }
.recipe-img-v { width: 100px; height: 100px; border-radius: var(--radius-sm); object-fit: cover; flex-shrink: 0; }
.recipe-card-v-body { flex: 1; display: flex; flex-direction: column; justify-content: space-between; min-width: 0; }
.recipe-card-v-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.recipe-name-v {
	font-size: 15px;
	font-weight: 700;
	color: var(--text-primary);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	flex: 1;
}
.match-badge-v {
	padding: 2px 8px;
	border-radius: 10px;
	font-size: 10px;
	font-weight: 700;
	white-space: nowrap;
	flex-shrink: 0;
}
.match-badge-v.high { color: var(--accent-green);  background: rgba(0,230,118,0.1); }
.match-badge-v.mid  { color: var(--accent-orange); background: rgba(245,158,11,0.1); }
.match-badge-v.low  { color: var(--accent-red);    background: rgba(239,68,68,0.1); }

/* Ingredient Tags */
.recipe-ingredients { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.ing-tag {
	padding: 2px 8px;
	border-radius: 8px;
	font-size: 10px;
	font-weight: 500;
	color: var(--text-muted);
	background: rgba(255,255,255,0.04);
	border: 1px solid rgba(255,255,255,0.06);
}
.ing-tag.owned {
	color: var(--accent-cyan);
	background: rgba(0, 212, 255, 0.08);
	border-color: rgba(0, 212, 255, 0.15);
}

/* Recipe Stats */
.recipe-card-v-bottom { display: flex; gap: 14px; margin-top: 10px; }
.recipe-stat { display: flex; align-items: center; gap: 3px; font-size: 11px; color: var(--text-secondary); }

/* Empty State */
.empty-state { text-align: center; padding: 28px 20px; }
.empty-icon { font-size: 48px !important; color: var(--text-muted); margin-bottom: 8px; display: block; }
.empty-text { font-size: 14px; color: var(--text-secondary); display: block; }
.empty-hint { font-size: 12px; color: var(--text-muted); margin-top: 4px; display: block; }

/* ======================== Recipe Detail Modal ======================== */
.modal-overlay {
	position: fixed;
	top: 0; left: 0; right: 0; bottom: 0;
	background: rgba(0, 0, 0, 0.7);
	backdrop-filter: blur(8px);
	-webkit-backdrop-filter: blur(8px);
	z-index: 200;
	display: flex;
	align-items: flex-end;
	justify-content: center;
}
.modal-sheet {
	width: 100%;
	max-width: 430px;
	max-height: 85vh;
	background: var(--bg-panel);
	border-radius: var(--radius-xl) var(--radius-xl) 0 0;
	overflow-y: auto;
	-webkit-overflow-scrolling: touch;
	padding-bottom: 30px;
}
.modal-img {
	width: 100%;
	height: 200px;
	object-fit: cover;
	display: block;
}
.modal-header { padding: 16px 20px 0; }
.modal-title-row {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
}
.modal-name { font-size: 22px; font-weight: 900; color: var(--text-primary); flex: 1; }
.modal-meta { display: flex; gap: 20px; margin-top: 12px; }
.meta-item { display: flex; align-items: center; gap: 5px; font-size: 13px; color: var(--text-secondary); }
.meta-icon { font-size: 16px !important; color: var(--text-muted); }
.modal-divider {
	height: 1px;
	margin: 16px 20px;
	background: linear-gradient(to right, var(--border-card), transparent);
}

/* Modal Sections */
.modal-section { padding: 0 20px; margin-bottom: 20px; }
.modal-section-title {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 15px;
	font-weight: 700;
	color: var(--text-primary);
	margin-bottom: 12px;
}

/* Ingredient Chips in Modal */
.modal-ingredients { display: flex; flex-wrap: wrap; gap: 8px; }
.modal-ing-chip {
	display: flex;
	align-items: center;
	gap: 6px;
	padding: 6px 12px;
	border-radius: 20px;
	font-size: 13px;
	font-weight: 600;
	transition: var(--transition);
}
.modal-ing-chip.owned {
	color: var(--accent-green);
	background: rgba(0, 230, 118, 0.08);
	border: 1px solid rgba(0, 230, 118, 0.2);
}
.modal-ing-chip.missing {
	color: var(--text-muted);
	background: rgba(255, 255, 255, 0.03);
	border: 1px solid rgba(255, 255, 255, 0.06);
}
.ing-status-icon { font-size: 16px !important; }
.ing-label { font-size: 10px; font-weight: 500; padding: 1px 6px; border-radius: 8px; }
.modal-ing-chip.owned .ing-label {
	color: var(--accent-green);
	background: rgba(0, 230, 118, 0.15);
}
.missing-label {
	color: var(--text-muted);
	background: rgba(255,255,255,0.05);
}

/* Steps */
.steps-list { display: flex; flex-direction: column; gap: 0; }
.step-item { display: flex; gap: 12px; padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
.step-item:last-child { border-bottom: none; }
.step-num {
	width: 24px; height: 24px;
	border-radius: 50%;
	background: linear-gradient(135deg, #00d4ff, #7c3aed);
	color: #fff;
	font-size: 12px;
	font-weight: 700;
	display: flex;
	align-items: center;
	justify-content: center;
	flex-shrink: 0;
	margin-top: 1px;
}
.step-text { font-size: 13px; color: var(--text-secondary); line-height: 1.7; flex: 1; }

/* Close Button */
.modal-close-btn {
	margin: 10px 20px 0;
	padding: 14px;
	border-radius: var(--radius-md);
	background: var(--bg-card);
	border: 1px solid var(--border-card);
	text-align: center;
	font-size: 14px;
	font-weight: 600;
	color: var(--text-primary);
	transition: var(--transition);
}
.modal-close-btn:active { background: var(--bg-card-hover); transform: scale(0.98); }

/* ===== Phase 8: Agent 聊天模块 ===== */
.module-chat { margin-top: 24px; }

/* 流式输出盒 */
.chat-stream-box {
	background: rgba(0,255,136,0.05);
	border: 1px solid rgba(0,255,136,0.15);
	border-radius: 12px;
	padding: 14px 16px;
	margin: 12px 0;
	min-height: 48px;
	display: flex;
	align-items: flex-start;
	gap: 8px;
}
.chat-stream-text {
	color: #e0e0e0;
	font-size: 14px;
	line-height: 1.6;
	flex: 1;
}
.chat-cursor {
	color: #00ff88;
	font-weight: bold;
	animation: blink 1s infinite;
}
@keyframes blink { 0%,100% { opacity:1 } 50% { opacity:0 } }

/* 工具状态 */
.chat-tool-status {
	background: rgba(102,126,234,0.1);
	border: 1px solid rgba(102,126,234,0.2);
	border-radius: 8px;
	padding: 8px 14px;
	margin: 8px 0;
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 13px;
	color: #a0b4f0;
}

/* 快捷提问 */
.chat-quick-actions { margin: 16px 0 12px; }
.quick-label { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; display: block; }
.quick-btns { display: flex; flex-wrap: wrap; gap: 8px; }
.quick-btn {
	background: rgba(0,204,255,0.08);
	border: 1px solid rgba(0,204,255,0.2);
	border-radius: 20px;
	padding: 6px 14px;
	font-size: 13px;
	color: #0cf;
	cursor: pointer;
}
.quick-btn:active { background: rgba(0,204,255,0.15); }

/* 输入行 */
.chat-input-row {
	display: flex;
	gap: 10px;
	align-items: center;
	margin-top: 12px;
}
.chat-input {
	flex: 1;
	background: rgba(255,255,255,0.06);
	border: 1px solid rgba(255,255,255,0.12);
	border-radius: 24px;
	padding: 10px 16px;
	color: #e0e0e0;
	font-size: 14px;
	height: 40px;
}
.chat-send-btn {
	width: 40px; height: 40px;
	background: linear-gradient(135deg, #00ccff, #667eea);
	border-radius: 50%;
	display: flex; align-items: center; justify-content: center;
	cursor: pointer;
	transition: opacity 0.2s;
}
.chat-send-btn.disabled { opacity: 0.3; pointer-events: none; }

/* 消息区 */
.chat-messages { margin-bottom: 8px; }
.chat-msg {
	margin: 8px 0;
	padding: 10px 14px;
	border-radius: 12px;
	font-size: 14px;
	line-height: 1.6;
}
.chat-msg-user {
	background: rgba(0,204,255,0.1);
	border: 1px solid rgba(0,204,255,0.2);
}
.chat-msg-ai {
	background: rgba(255,255,255,0.04);
	border: 1px solid rgba(255,255,255,0.08);
}
.chat-role {
	font-size: 11px;
	color: var(--text-muted);
	display: block;
	margin-bottom: 4px;
}
.chat-text { color: #e0e0e0; }
</style>
