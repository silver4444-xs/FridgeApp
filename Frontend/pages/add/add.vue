<template>
	<view class="page-shell">
		<view class="page">
			<view class="add-header">
				<text class="add-title">添加食材</text>
				<text class="add-sub">记录新食材信息到云端库存</text>
			</view>

			<view class="form-group">
				<text class="form-label">食材名称</text>
				<input class="form-input" v-model="form.name" placeholder="例如：草莓、牛肉" placeholder-class="ph" @input="onNameInput" />
				<view v-if="classification" class="classify-info">
					<view class="cl-row"><text class="cl-label">英文名</text><text class="cl-val">{{ classification.enName }}</text></view>
					<view class="cl-row"><text class="cl-label">分类</text><text class="cl-val">{{ catName }}</text></view>
					<view class="cl-row" v-if="classification.calories"><text class="cl-label">卡路里</text><text class="cl-val">{{ classification.calories }} kcal</text></view>
				</view>
				<view v-else-if="form.name.trim()" class="classify-info unknown">
					<text class="cl-hint">未识别食材，将以原名上传</text>
				</view>
			</view>

			<view class="form-row">
				<view class="form-group flex-1">
					<text class="form-label">数量</text>
					<input class="form-input" v-model.number="form.qty" type="number" />
				</view>
				<view class="form-group flex-1">
					<text class="form-label">单位</text>
					<picker :value="unitIndex" :range="unitOptions" @change="onUnitChange">
						<view class="form-input picker-input">{{ form.unit }}</view>
					</picker>
				</view>
			</view>

			<view class="btn-primary" @click="submit" :class="{ disabled: !canSubmit }">
				<text class="material-icons" style="vertical-align:middle;margin-right:6px;font-size:20px;">cloud_upload</text>
				<text>添加到冰箱</text>
			</view>

			<view class="toast" :class="{ show: toastVisible }">{{ toastMsg }}</view>
		</view>
	</view>
</template>

<script>
import { store, CAT_META, UNIT_OPTIONS, classifyFood } from '@/utils/store.js'
import { uploadViaWs } from '@/utils/cloudSync.js'

export default {
	data() {
		return {
			form: { name: '', qty: 1, unit: '个' },
			classification: null,
			unitOptions: UNIT_OPTIONS,
			toastVisible: false, toastMsg: '', toastTimer: null,
		}
	},
	computed: {
		unitIndex() { return this.unitOptions.indexOf(this.form.unit) },
		catName() { if (!this.classification) return ''; return (CAT_META[this.classification.cat] || CAT_META.packaged).name },
		canSubmit() { return !!this.form.name.trim() },
	},
	methods: {
		onUnitChange(e) { this.form.unit = this.unitOptions[e.detail.value] },
		onNameInput() {
			const name = this.form.name.trim()
			this.classification = name ? classifyFood(name) : null
		},
		async submit() {
			const name = this.form.name.trim()
			if (!name) { this.showToast('请输入食材名称'); return }
			const info = this.classification || classifyFood(name)
			const qty = parseFloat(this.form.qty) || 1
			store.addFood({ name, _classified: info, qty, unit: this.form.unit })
			try { await uploadViaWs(store.foods) }
			catch (e) { console.warn('[Add] 云端上传失败:', e) }
			this.form.name = ''; this.form.qty = 1; this.classification = null
			this.showToast('已添加 ' + info.zhName + (info.calories ? ' (' + info.calories + 'kcal)' : ''))
			setTimeout(() => uni.switchTab({ url: '/pages/home/home' }), 400)
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
.add-header { padding: 8px 0 20px; }
.add-title { font-size: 28px; font-weight: 900; color: var(--text-primary); letter-spacing: -0.5px; display: block; }
.add-sub { font-size: 13px; color: var(--text-secondary); margin-top: 4px; display: block; }
.form-group { margin-bottom: 18px; }
.form-label { display: block; font-size: 12px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.form-input { width: 100%; height: 48px; background: var(--bg-card); border: 1px solid var(--border-card); border-radius: var(--radius-sm); padding: 0 16px; color: var(--text-primary); font-size: 15px; }
.form-input:focus { border-color: var(--accent-cyan); }
.ph { color: var(--text-muted); }
.picker-input { display: flex; align-items: center; }
.form-row { display: flex; gap: 12px; }
.flex-1 { flex: 1; }
.classify-info { margin-top: 10px; padding: 10px 14px; background: rgba(0,212,255,0.06); border: 1px solid rgba(0,212,255,0.15); border-radius: var(--radius-sm); }
.classify-info.unknown { background: rgba(255,152,0,0.06); border-color: rgba(255,152,0,0.15); }
.cl-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; }
.cl-label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.cl-val { font-size: 14px; font-weight: 600; color: var(--accent-cyan); }
.cl-hint { font-size: 12px; color: #ff9800; }
.btn-primary { width: 100%; height: 52px; background: linear-gradient(135deg, #00d4ff 0%, #0098ff 100%); border-radius: var(--radius-sm); color: #000; font-size: 16px; font-weight: 700; display: flex; align-items: center; justify-content: center; letter-spacing: 0.5px; margin-top: 4px; }
.btn-primary:active { transform: scale(0.98); opacity: 0.9; }
.btn-primary.disabled { opacity: 0.5; pointer-events: none; }
.toast { position: fixed; top: 80px; left: 50%; transform: translateX(-50%) translateY(-20px); background: rgba(0,230,118,0.15); border: 1px solid rgba(0,230,118,0.3); color: var(--accent-green); padding: 10px 24px; border-radius: 20px; font-size: 13px; font-weight: 600; z-index: 300; opacity: 0; pointer-events: none; transition: all 0.3s ease; }
.toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
</style>
