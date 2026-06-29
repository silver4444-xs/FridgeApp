<template>
	<view class="page-shell">
		<view class="page">
			<view class="settings-header">
				<text class="settings-title">设置</text>
			</view>

			<view class="conn-card">
				<view class="conn-header">
					<view class="conn-dot" :class="{ on: cloudConnected }"></view>
					<view>
						<text class="conn-title">{{ cloudConnected ? 'OneNET IoT 已连接' : 'OneNET IoT 未连接' }}</text>
						<text class="conn-sub">{{ cloudConnected ? '云端数据同步中' : (cloudError || '请检查网络与凭证') }}</text>
					</view>
				</view>
				<view class="conn-detail">
					<view class="conn-row"><text class="cr-label">产品 ID</text><text class="cr-value">{{ config.productId }}</text></view>
					<view class="conn-row"><text class="cr-label">设备名称</text><text class="cr-value">{{ config.deviceName }}</text></view>
					<view class="conn-row"><text class="cr-label">数据刷新</text><text class="cr-value">3s 自动</text></view>
				</view>
			</view>

			<view class="settings-section">
				<text class="section-title">后端服务</text>
				<view class="setting-item">
					<view class="si-left">
						<view class="si-icon cyan"><text class="material-icons" style="font-size:18px;">dns</text></view>
						<view style="flex:1;">
							<text class="si-label">图片服务器地址</text>
							<text class="si-desc">只填电脑局域网IP的4段数字</text>
						</view>
					</view>
				</view>
				<view class="url-input-row">
					<view class="ip-row">
						<text class="url-fixed">http://</text>
						<input class="ip-input" type="number" maxlength="3" v-model="ip1" placeholder="192" @input="onIpInput(1)" />
						<text class="ip-dot">.</text>
						<input class="ip-input" type="number" maxlength="3" v-model="ip2" placeholder="168" @input="onIpInput(2)" />
						<text class="ip-dot">.</text>
						<input class="ip-input" type="number" maxlength="3" v-model="ip3" placeholder="0" @input="onIpInput(3)" />
						<text class="ip-dot">.</text>
						<input class="ip-input" type="number" maxlength="3" v-model="ip4" placeholder="1" @input="onIpInput(4)" />
						<text class="url-fixed">:8000</text>
					</view>
					<view class="url-btn" @click="saveBackendUrl">保存</view>
				</view>
			</view>

			<view class="settings-section">
				<text class="section-title">数据管理</text>
								<view class="setting-item" @click="exportData">
					<view class="si-left">
						<view class="si-icon purple"><text class="material-icons" style="font-size:18px;">download</text></view>
						<view><text class="si-label">导出数据</text><text class="si-desc">导出食材库存数据为 JSON</text></view>
					</view>
					<text class="material-icons si-right">file_download</text>
				</view>
			</view>

			<view class="settings-section">
				<text class="section-title">关于</text>
				<view class="setting-item">
					<view class="si-left">
						<view class="si-icon green"><text class="material-icons" style="font-size:18px;">info</text></view>
						<text class="si-label">版本</text>
					</view>
					<text class="si-value">FridgeAI v1.0.0</text>
				</view>
			</view>

			<view class="toast" :class="{ show: toastVisible }">{{ toastMsg }}</view>
		</view>
	</view>
</template>

<script>
import { store } from '@/utils/store.js'
import { getConfig } from '@/config/onenet.js'

export default {
	data() {
		return {
			config: getConfig(),
			toastVisible: false, toastMsg: '', toastTimer: null,
			ip1: '', ip2: '', ip3: '', ip4: '',
		}
	},
	computed: {
		cloudConnected() { return store.cloudConnected },
		cloudError() { return store.cloudError },
	},
	mounted() {
		this.parseStoredUrl()
	},
	methods: {
		parseStoredUrl() {
			try {
				const stored = uni.getStorageSync('backend_url') || ''
				const m = stored.match(/\/\/(\d+)\.(\d+)\.(\d+)\.(\d+)/)
				if (m) {
					this.ip1 = m[1]; this.ip2 = m[2]; this.ip3 = m[3]; this.ip4 = m[4]
				}
			} catch (e) {}
		},
		onIpInput(idx) {
			const val = this['ip' + idx]
			const num = parseInt(val, 10)
			if (val !== '' && (isNaN(num) || num < 0)) { this['ip' + idx] = ''; return }
			if (num > 255) { this['ip' + idx] = '255' }
			if (val.length >= 3 && idx < 4 && num >= 0 && num <= 255) {
				this.$nextTick(() => {})
			}
		},
		saveBackendUrl() {
			const parts = [this.ip1, this.ip2, this.ip3, this.ip4]
			if (parts.some(v => !v || isNaN(parseInt(v)))) {
				this.showToast('请填写完整IP地址'); return
			}
			const url = 'http://' + parts.map(v => parseInt(v)).join('.') + ':8000'
			uni.setStorageSync('backend_url', url)
			this.showToast('已保存: ' + url)
		},
		exportData() {
			const data = JSON.stringify(store.foods, null, 2)
			uni.setClipboardData({ data, success: () => this.showToast('已复制到剪贴板') })
		},
		showToast(msg) {
			this.toastMsg = msg; this.toastVisible = true
			clearTimeout(this.toastTimer)
			this.toastTimer = setTimeout(() => { this.toastVisible = false }, 2000)
		},
	},
}
</script>

<style scoped>
.page-shell { flex: 1; display: flex; flex-direction: column; height: 100%; overflow: hidden; background: var(--bg-deep); }
.page { flex: 1; padding: 0 20px; overflow-y: auto; -webkit-overflow-scrolling: touch; }
.settings-header { padding: 8px 0 20px; }
.settings-title { font-size: 28px; font-weight: 900; color: var(--text-primary); letter-spacing: -0.5px; }

.conn-card { background: var(--bg-card); backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur); border: 1px solid var(--border-card); border-radius: var(--radius-md); padding: 20px; margin-bottom: 20px; }
.conn-header { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.conn-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--text-muted); flex-shrink: 0; }
.conn-dot.on { background: var(--accent-green); box-shadow: 0 0 12px var(--accent-green); animation: pulse-dot 2s infinite; }
@keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:.4} }
.conn-title { font-size: 16px; font-weight: 700; color: var(--text-primary); display: block; }
.conn-sub { font-size: 12px; color: var(--text-secondary); display: block; }
.conn-detail { display: flex; flex-direction: column; gap: 8px; }
.conn-row { display: flex; justify-content: space-between; }
.cr-label { font-size: 12px; color: var(--text-muted); }
.cr-value { font-size: 12px; color: var(--text-secondary); font-family: monospace; }

.settings-section { margin-bottom: 24px; }
.section-title { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; display: block; margin-bottom: 10px; }
.setting-item { display: flex; align-items: center; justify-content: space-between; padding: 16px; background: var(--bg-card); backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur); border: 1px solid var(--border-card); border-radius: var(--radius-sm); margin-bottom: 8px; transition: var(--transition); }
.setting-item:active { background: var(--bg-card-hover); }
.si-left { display: flex; align-items: center; gap: 12px; }
.si-icon { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; }
.si-icon.cyan { background: rgba(0,212,255,0.1); color: var(--accent-cyan); }
.si-icon.purple { background: rgba(124,58,237,0.1); color: var(--accent-purple); }
.si-icon.green { background: rgba(0,230,118,0.1); color: var(--accent-green); }
.si-label { font-size: 14px; font-weight: 600; color: var(--text-primary); display: block; }
.si-desc { font-size: 11px; color: var(--text-secondary); display: block; }
.si-right { font-size: 20px !important; color: var(--text-muted); }
.si-value { font-size: 14px; color: var(--text-secondary); }

.url-input-row { display: flex; flex-direction: column; gap: 10px; margin-bottom: 8px; padding: 12px 16px; background: var(--bg-card); border: 1px solid var(--border-card); border-top: none; border-radius: 0 0 var(--radius-sm) var(--radius-sm); position: relative; z-index: 1; }
.ip-row { display: flex; align-items: center; gap: 4px; }
.url-fixed { font-size: 13px; color: var(--text-secondary); font-family: monospace; white-space: nowrap; flex-shrink: 0; }
.ip-dot { font-size: 16px; color: var(--text-muted); font-weight: 700; flex-shrink: 0; }
.ip-input { flex: 1; min-width: 0; min-height: 40px; padding: 6px 2px; background: var(--bg-deep); border: 1px solid var(--border-card); border-radius: 6px; color: var(--accent-cyan); font-size: 15px; font-weight: 700; text-align: center; font-family: monospace; }
.ip-input::placeholder { color: var(--text-muted); font-weight: 400; font-size: 10px; }
.url-btn { width: 100%; padding: 12px 0; background: var(--accent-cyan); color: #000; font-size: 14px; font-weight: 700; border-radius: 8px; text-align: center; display: flex; align-items: center; justify-content: center; cursor: pointer; }
.url-btn:active { opacity: 0.8; }

.toast { position: fixed; top: 80px; left: 50%; transform: translateX(-50%) translateY(-20px); background: rgba(0,230,118,0.15); border: 1px solid rgba(0,230,118,0.3); color: var(--accent-green); padding: 10px 24px; border-radius: 20px; font-size: 13px; font-weight: 600; z-index: 300; opacity: 0; pointer-events: none; transition: all 0.3s ease; }
.toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
</style>
