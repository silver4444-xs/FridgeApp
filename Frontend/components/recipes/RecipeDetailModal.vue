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
				<text class="modal-section-title"><text class="material-icons section-title-icon">checklist</text> 所需食材</text>
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
				<text class="modal-section-title"><text class="material-icons section-title-icon">menu_book</text> 制作流程</text>
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

<style scoped>
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
	background: #0d1117;
	border-radius: 20px 20px 0 0;
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

.modal-name {
	font-size: 22px;
	font-weight: 900;
	color: #e0e0e0;
	flex: 1;
}

.match-badge-v {
	padding: 3px 10px;
	border-radius: 10px;
	font-size: 11px;
	font-weight: 700;
	white-space: nowrap;
	flex-shrink: 0;
}
.match-badge-v.high { color: #22c55e;  background: rgba(34,197,94,0.1); }
.match-badge-v.mid  { color: #f59e0b; background: rgba(245,158,11,0.1); }
.match-badge-v.low  { color: #ef4444; background: rgba(239,68,68,0.1); }

.modal-meta { display: flex; gap: 20px; margin-top: 12px; }

.meta-item {
	display: flex;
	align-items: center;
	gap: 5px;
	font-size: 13px;
	color: #c0c0c0;
}

.meta-icon { font-size: 16px !important; color: #8b949e; }

.modal-divider {
	height: 1px;
	margin: 16px 20px;
	background: linear-gradient(to right, rgba(255,255,255,0.06), transparent);
}

.modal-section { padding: 0 20px; margin-bottom: 20px; }

.modal-section-title {
	display: flex;
	align-items: center;
	gap: 6px;
	font-size: 15px;
	font-weight: 700;
	color: #e0e0e0;
	margin-bottom: 12px;
}

.section-title-icon { font-size: 16px !important; color: #00d4ff; }

.modal-ingredients { display: flex; flex-wrap: wrap; gap: 8px; }

.modal-ing-chip {
	display: flex;
	align-items: center;
	gap: 6px;
	padding: 6px 12px;
	border-radius: 10px;
	font-size: 13px;
	border: 1px solid rgba(255,255,255,0.06);
	transition: all 0.2s ease;
}

.modal-ing-chip.owned {
	color: #22c55e;
	background: rgba(34,197,94,0.08);
	border-color: rgba(34,197,94,0.2);
}

.modal-ing-chip.missing {
	color: #8b949e;
	background: rgba(255,255,255,0.03);
}

.ing-status-icon { font-size: 16px !important; }

.ing-label {
	font-size: 10px;
	font-weight: 500;
	padding: 1px 6px;
	border-radius: 8px;
}

.modal-ing-chip.owned .ing-label {
	color: #22c55e;
	background: rgba(34,197,94,0.15);
}

.missing-label {
	color: #8b949e;
	background: rgba(255,255,255,0.05);
}

.steps-list { display: flex; flex-direction: column; }

.step-item {
	display: flex;
	gap: 12px;
	padding: 12px 0;
	border-bottom: 1px solid rgba(255,255,255,0.04);
}

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

.step-text {
	font-size: 13px;
	color: #c0c0c0;
	line-height: 1.7;
	flex: 1;
}

.modal-close-btn {
	margin: 10px 20px 0;
	padding: 14px;
	border-radius: 12px;
	background: rgba(255,255,255,0.03);
	border: 1px solid rgba(255,255,255,0.06);
	text-align: center;
	font-size: 14px;
	font-weight: 600;
	color: #e0e0e0;
	transition: all 0.2s ease;
}

.modal-close-btn:active {
	background: rgba(255,255,255,0.06);
	transform: scale(0.98);
}
</style>
