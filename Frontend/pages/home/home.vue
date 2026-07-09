<template>
	<view class="page-shell">
		<scroll-view class="page" scroll-y refresher-enabled :refresher-triggered="refreshing" @refresherrefresh="onRefresh">
			<view class="fridge-header">
				<view class="title-group">
					<text class="title-main">我的冰箱</text>
					<text class="title-sub">云端同步 · OneNET IoT</text>
				</view>
				<view class="cloud-badge" :class="{ connected: cloudConnected }">
					<view class="dot"></view>
					<text>{{ cloudConnected ? '在线' : '离线' }}</text>
				</view>
			</view>

			<view class="stats-row">
				<view class="stat-chip"><text class="stat-num">{{ totalCount }}</text><text class="stat-label">食材总数</text></view>
				<view class="stat-chip category"><text class="stat-num">{{ catCount }}</text><text class="stat-label">食材种类</text></view>
				<view class="stat-chip calorie"><text class="stat-num">{{ totalCalories }}</text><text class="stat-label">总卡路里 (kcal)</text></view>
			</view>

			<scroll-view scroll-x class="cat-scroll" :show-scrollbar="false">
				<view v-for="cat in categories" :key="cat.key" class="cat-chip" :class="{ active: activeCat === cat.key }" @click="switchCat(cat.key)">
					<text class="cat-emoji">{{ cat.emoji }}</text><text>{{ cat.name }}</text>
				</view>
			</scroll-view>

			<view v-if="filteredFoods.length > 0" class="food-grid">
				<view v-for="food in filteredFoods" :key="food.id" class="food-card" @click="openEdit(food)">
					<image class="card-img" :src="food.photo" mode="aspectFill" />
					<view class="card-body">
						<text class="card-name">{{ food.name }}</text>
						<view class="card-cal" v-if="food.calories"><text class="cal-icon">🔥</text><text class="cal-val">{{ food.calories }}</text><text class="cal-unit">kcal</text></view>
						<view class="card-meta">
							<view class="qty-editor" @click.stop>
								<view class="qty-btn" @click="changeQty(food, -1)">-</view>
								<input class="qty-input" type="number" :value="food.qty" @input="setQty(food, $event)" />
								<view class="qty-btn" @click="changeQty(food, 1)">+</view>
							</view>
							<text class="card-unit">{{ food.qty }}{{ food.unit }}</text>
						</view>
					</view>
				</view>
			</view>

			<view v-else class="empty-state">
				<text class="material-icons empty-icon">kitchen</text>
				<text class="empty-text">冰箱空空如也</text>
				<text class="empty-hint">点击 + 添加食材</text>
			</view>

			<view class="modal-overlay" :class="{ show: editVisible }" @click="closeEdit">
				<view class="modal-sheet" @click.stop>
					<view class="modal-handle"></view>
					<text class="modal-title">编辑食材</text>
					<view class="form-group"><text class="form-label">食材名称</text><input class="form-input" v-model="editForm.name" /></view>
					<view class="form-row">
						<view class="form-group flex-1"><text class="form-label">数量</text><input class="form-input" v-model.number="editForm.qty" type="number" /></view>
						<view class="form-group flex-1"><text class="form-label">单位</text><picker :value="unitIndex" :range="unitOptions" @change="onUnitChange"><view class="form-input picker-input">{{ editForm.unit }}</view></picker></view>
					</view>
					<view class="btn-row">
						<view class="btn-save" @click="saveEdit">保存</view>
						<view class="btn-delete" @click="deleteEdit">删除</view>
					</view>
				</view>
			</view>

			<view class="toast" :class="{ show: toastVisible }">{{ toastMsg }}</view>
		</scroll-view>
	</view>
</template>

<script>
import { store, CAT_META, UNIT_OPTIONS } from '@/utils/store.js'
import { uploadViaWs, requestSync } from '@/utils/cloudSync.js'

const CALORIE_BY_CAT = { fruit: 70, vegetable: 35, meat_egg: 200, beverage_dairy: 150, packaged: 80 }

export default {

	data() {
		return {
			activeCat: 'all',
			categories: Object.entries(CAT_META).map(([k, v]) => ({ key: k, ...v })),
			unitOptions: UNIT_OPTIONS,
			editVisible: false,
			editForm: { id: null, name: '', qty: 0, unit: '个' },
			toastVisible: false, toastMsg: '', toastTimer: null,
			refreshing: false,
		}
	},
	computed: {
		filteredFoods() { return store.getByCat(this.activeCat) },
		totalCount() { return store.totalCount },
		catCount() { return new Set(store.foods.map(f => f.cat)).size },
		totalCalories() { return this.calcTotalCalories() },
		cloudConnected() { return store.cloudConnected },
		unitIndex() { return this.unitOptions.indexOf(this.editForm.unit) },
	},
	onLoad() {},
	onShow() {},
	methods: {
		onRefresh() {
			this.refreshing = true
			requestSync()
			setTimeout(() => { this.refreshing = false }, 800)
		},
		calcTotalCalories() {
			let total = 0
			store.foods.forEach(f => { total += Math.round((f.calories || CALORIE_BY_CAT[f.cat] || 80) * f.qty) })
			return total
		},
		switchCat(cat) { this.activeCat = cat },
		changeQty(food, delta) {
			const isInt = ['颗', '个', '瓶', '盒', '袋', '根', '把'].includes(food.unit)
			const oldQty = food.qty
			let n = oldQty + delta
			if (isInt) n = Math.max(0, Math.round(n))
			else n = Math.max(0, Math.round(n * 10) / 10)
			const result = store.updateQty(food.id, n)
			const amt = result && result.deleted ? oldQty : Math.abs(delta)
			if (result && result.deleted) this.showToast('拿出' + amt + food.unit + result.name)
			else if (delta > 0) this.showToast('放入' + amt + food.unit + food.name)
			else this.showToast('拿出' + amt + food.unit + food.name)
			this.syncToCloud()
		},
		setQty(food, e) {
			const val = parseFloat(e.detail.value)
			if (isNaN(val)) return
			const n = Math.max(0, val), oldQty = food.qty
			const result = store.updateQty(food.id, n)
			if (result && result.deleted) this.showToast('拿出' + oldQty + food.unit + result.name)
			else if (n > oldQty) this.showToast('放入' + (n - oldQty) + food.unit + food.name)
			else if (n < oldQty) this.showToast('拿出' + (oldQty - n) + food.unit + food.name)
			this.syncToCloud()
		},
		openEdit(food) { this.editForm = { ...food, oldQty: food.qty }; this.editVisible = true },
		closeEdit() { this.editVisible = false },
		onUnitChange(e) { this.editForm.unit = this.unitOptions[e.detail.value] },
		saveEdit() {
			if (!this.editForm.id) return
			const oldQty = this.editForm.oldQty != null ? this.editForm.oldQty : this.editForm.qty
			const result = store.updateFood(this.editForm.id, { name: this.editForm.name, qty: parseFloat(this.editForm.qty) || 0, unit: this.editForm.unit })
			this.closeEdit()
			const newQty = parseFloat(this.editForm.qty) || 0
			if (result && result.deleted) this.showToast('拿出' + oldQty + this.editForm.unit + result.name)
			else if (newQty > oldQty) this.showToast('放入' + (newQty - oldQty) + this.editForm.unit + this.editForm.name)
			else if (newQty < oldQty) this.showToast('拿出' + (oldQty - newQty) + this.editForm.unit + this.editForm.name)
			this.syncToCloud()
		},
		deleteEdit() {
			if (!this.editForm.id) return
			const food = store._foods.find(f => f.id === this.editForm.id)
			const amt = food ? food.qty : this.editForm.qty
			store.removeFood(this.editForm.id)
			this.closeEdit()
			this.showToast('拿出' + amt + this.editForm.unit + this.editForm.name)
			this.syncToCloud()
		},
		// Fix #2: 上传防抖 — 300ms 内多次操作合并为一次上传
		// 原有逻辑: 每次 changeQty/setQty/saveEdit/deleteEdit 都触发全量上传
		// 修复后: 连续操作合并，只在最后一次操作后 300ms 发送
		syncToCloud() {
			clearTimeout(this._syncTimer)
			this._syncTimer = setTimeout(() => { uploadViaWs(store._foods) }, 300)
		},
		showToast(msg) {
			this.toastMsg = msg; this.toastVisible = true
			clearTimeout(this.toastTimer)
			this.toastTimer = setTimeout(() => { this.toastVisible = false }, 1800)
		},
	},
}
</script>

<style scoped>
.page-shell { flex: 1; display: flex; flex-direction: column; height: 100%; overflow: hidden; background: var(--bg-deep); }
.page { flex: 1; padding: 0 20px; overflow-y: auto; -webkit-overflow-scrolling: touch; }
.fridge-header { padding: 8px 0 16px; display: flex; justify-content: space-between; align-items: flex-start; }
.title-group { display: flex; flex-direction: column; }
.title-main { font-size: 32px; font-weight: 900; color: var(--text-primary); letter-spacing: -0.5px; background: linear-gradient(135deg, #e6edf3 0%, #00d4ff 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.title-sub { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }
.cloud-badge { display: flex; align-items: center; gap: 6px; background: rgba(0,212,255,0.1); border: 1px solid rgba(0,212,255,0.2); border-radius: 20px; padding: 6px 14px; font-size: 11px; color: var(--accent-cyan); font-weight: 600; flex-shrink: 0; }
.cloud-badge .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); animation: pulse-dot 2s infinite; }
.cloud-badge:not(.connected) .dot { background: var(--text-muted); box-shadow: none; }
@keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:.4} }
.stats-row { display: flex; gap: 10px; margin-bottom: 18px; }
.stat-chip { flex: 1; background: var(--bg-card); backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur); border: 1px solid var(--border-card); border-radius: var(--radius-md); padding: 14px 12px; text-align: center; }
.stat-chip.category { border-color: rgba(0,212,255,0.25); }
.stat-chip.category .stat-num { color: var(--accent-cyan); }
.stat-chip.calorie { border-color: rgba(0,230,118,0.25); }
.stat-chip.calorie .stat-num { color: var(--accent-green); }
.stat-num { font-size: 26px; font-weight: 800; color: var(--text-primary); letter-spacing: -1px; }
.stat-label { font-size: 11px; color: var(--text-secondary); margin-top: 2px; display: block; }
.cat-scroll { display: flex; gap: 10px; padding-bottom: 14px; white-space: nowrap; }
.cat-chip { display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0; padding: 8px 18px; border-radius: 20px; font-size: 13px; font-weight: 600; color: var(--text-secondary); background: var(--bg-card); border: 1px solid var(--border-card); transition: var(--transition); white-space: nowrap; }
.cat-chip.active { color: #fff; background: rgba(0,212,255,0.15); border-color: var(--accent-cyan); box-shadow: 0 0 16px rgba(0,212,255,0.1); }
.food-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding-bottom: 20px; }
.food-card { background: var(--bg-card); backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur); border: 1px solid var(--border-card); border-radius: var(--radius-lg); overflow: hidden; transition: var(--transition); }
.food-card:active { transform: scale(0.97); }
.card-img { width: 100%; height: 120px; object-fit: cover; display: block; }
.card-body { padding: 12px 14px 14px; }
.card-name { font-size: 15px; font-weight: 700; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
.card-cal { display: flex; align-items: center; gap: 3px; margin-top: 4px; }
.cal-icon { font-size: 11px; }
.cal-val { font-size: 12px; font-weight: 700; color: var(--accent-orange); }
.cal-unit { font-size: 10px; color: var(--text-muted); font-weight: 500; }
.card-meta { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.card-unit { font-size: 12px; color: var(--text-secondary); margin-left: 2px; }
.qty-editor { display: flex; align-items: center; gap: 6px; }
.qty-btn { width: 24px; height: 24px; border-radius: 50%; border: 1px solid var(--border-card); background: rgba(255,255,255,0.04); color: var(--text-primary); font-size: 16px; display: flex; align-items: center; justify-content: center; line-height: 1; transition: var(--transition); }
.qty-btn:active { background: rgba(0,212,255,0.2); border-color: var(--accent-cyan); }
.qty-input { width: 42px; text-align: center; background: transparent; color: var(--text-primary); font-size: 16px; font-weight: 700; height: auto; min-height: auto; }
.empty-state { text-align: center; padding: 40px 20px; }
.empty-icon { font-size: 64px !important; color: var(--text-muted); margin-bottom: 12px; display: block; }
.empty-text { font-size: 14px; color: var(--text-secondary); display: block; }
.empty-hint { font-size: 12px; color: var(--text-muted); margin-top: 4px; display: block; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); z-index: 200; display: flex; align-items: flex-end; opacity: 0; pointer-events: none; transition: opacity 0.3s ease; }
.modal-overlay.show { opacity: 1; pointer-events: auto; }
.modal-sheet { width: 100%; max-height: 80%; background: var(--bg-panel); border-radius: var(--radius-xl) var(--radius-xl) 0 0; padding: 12px 20px 30px; overflow-y: auto; transform: translateY(100%); transition: transform 0.35s cubic-bezier(0.4,0,0.2,1); }
.modal-overlay.show .modal-sheet { transform: translateY(0); }
.modal-handle { width: 40px; height: 4px; border-radius: 2px; background: var(--text-muted); margin: 0 auto 16px; }
.modal-title { font-size: 20px; font-weight: 800; color: var(--text-primary); display: block; margin-bottom: 18px; }
.form-group { margin-bottom: 18px; }
.form-label { display: block; font-size: 12px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.form-input { width: 100%; height: 48px; background: var(--bg-card); border: 1px solid var(--border-card); border-radius: var(--radius-sm); padding: 0 16px; color: var(--text-primary); font-size: 15px; }
.form-input:focus { border-color: var(--accent-cyan); }
.picker-input { display: flex; align-items: center; }
.form-row { display: flex; gap: 12px; }
.flex-1 { flex: 1; }
.btn-row { display: flex; gap: 10px; margin-top: 18px; }
.btn-save { flex: 1; height: 52px; background: linear-gradient(135deg, #00d4ff 0%, #0098ff 100%); border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; color: #000; letter-spacing: 0.5px; }
.btn-save:active { transform: scale(0.98); opacity: 0.9; }
.btn-delete { flex: 1; height: 52px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; color: var(--accent-red); }
.toast { position: fixed; top: 80px; left: 50%; transform: translateX(-50%) translateY(-20px); background: rgba(0,230,118,0.15); border: 1px solid rgba(0,230,118,0.3); color: var(--accent-green); padding: 10px 24px; border-radius: 20px; font-size: 13px; font-weight: 600; z-index: 300; opacity: 0; pointer-events: none; transition: all 0.3s ease; }
.toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
</style>
