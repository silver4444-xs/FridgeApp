<!-- Phase 8: 拆分自 recipes.vue Recipe Detail Modal -->
<template>
	<view v-if="recipe" class="modal-overlay" @click="$emit('close')">
		<view class="modal-sheet" @click.stop>
			<image v-if="recipe.image" :src="recipe.image" mode="aspectFill" class="modal-img" />
			<view class="modal-header">
				<view class="modal-title-row">
					<text class="modal-name">{{ recipe.name }}</text>
					<view v-if="!recipe.ownedIngredients || recipe.ownedIngredients.length > 0" class="match-badge-v" :class="matchLevel">
						<text>{{ recipe.matchCount }}/{{ recipe.ingredients.length }} 种食材</text>
					</view>
				</view>
				<view class="modal-meta">
					<view class="meta-item"><text class="material-icons meta-icon">schedule</text><text>{{ recipe.time }}</text></view>
					<view class="meta-item"><text class="material-icons meta-icon">local_fire_department</text><text>{{ recipe.calories }}</text></view>
					<view class="meta-item"><text class="material-icons meta-icon">speed</text><text>{{ recipe.difficulty }}</text></view>
				</view>
			</view>
			<view class="modal-divider"></view>
			<view class="modal-section">
				<text class="modal-section-title"><text class="material-icons" style="font-size:16px;color:var(--accent-cyan);">checklist</text> 所需食材</text>
				<view class="modal-ingredients">
					<view v-for="ing in recipe.ingredients" :key="typeof ing === 'string' ? ing : (ing.name || ing)" class="modal-ing-chip" :class="{ owned: isOwned(ing), missing: !isOwned(ing) }">
						<text class="material-icons ing-status-icon">{{ isOwned(ing) ? 'check_circle' : 'cancel' }}</text>
						<text>{{ typeof ing === 'string' ? ing : (ing.name || '') }}</text>
						<text v-if="isOwned(ing)" class="ing-label">已有</text>
						<text v-else class="ing-label missing-label">缺少</text>
					</view>
				</view>
			</view>
			<view class="modal-section">
				<text class="modal-section-title"><text class="material-icons" style="font-size:16px;color:var(--accent-cyan);">menu_book</text> 制作流程</text>
				<view class="steps-list">
					<view v-for="(step, idx) in recipe.steps" :key="idx" class="step-item">
						<view class="step-num">{{ idx + 1 }}</view>
						<text class="step-text">{{ step }}</text>
					</view>
				</view>
			</view>
			<view class="modal-close-btn" @click="$emit('close')"><text>关闭</text></view>
		</view>
	</view>
</template>

<script>
export default {
	name: 'RecipeDetailModal',
	props: {
		recipe: { type: Object, default: null },
		ownedKeywords: { type: Array, default: () => [] },
	},
	emits: ['close'],
	computed: {
		matchLevel() {
			if (!this.recipe) return ''
			const r = this.recipe.matchCount / Math.max(this.recipe.ingredients.length, 1)
			return r >= 0.8 ? 'high' : r >= 0.4 ? 'mid' : 'low'
		},
	},
	methods: {
		isOwned(ing) {
			const name = typeof ing === 'string' ? ing : (ing.name || ing)
			return this.ownedKeywords.some(kw => kw === name || name.includes(kw) || kw.includes(name))
		},
	},
}
</script>
