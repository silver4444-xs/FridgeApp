<template>
	<view class="module module-stats">
		<!--
		Phase 8: 拆分自 recipes.vue Module 1 (食材统计)
		原代码: recipes.vue 内联 ~1700行单文件
		改进后: 独立组件，Props 接口清晰
		-->
		<view class="corner corner-tl"></view>
		<view class="corner corner-tr"></view>
		<view class="corner corner-bl"></view>
		<view class="corner corner-br"></view>
		<view class="stats-scanline"></view>
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
					<view class="live-badge"><view class="live-dot"></view><text>实时</text></view>
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
						<text class="stat-value stat-gradient-purple">{{ matchedCount }}</text>
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
					<view class="data-bar-fill bar-purple" :style="{width: Math.min(matchedCount / Math.max(totalRecipes, 1) * 100, 100) + '%'}"></view>
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
</template>

<script>
export default {
	name: 'RecipeStats',
	props: {
		totalFoods: { type: Number, default: 0 },
		matchedCount: { type: Number, default: 0 },
		totalRecipes: { type: Number, default: 0 },
		matchPercent: { type: Number, default: 0 },
	},
}
</script>
