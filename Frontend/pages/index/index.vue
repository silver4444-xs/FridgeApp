<template>
	<view class="page-shell">
		<view class="page">
			<!-- Header -->
			<view class="header">
				<text class="header-title">智能冰箱监控</text>
				<view class="status-bar">
					<view class="status-dot" :class="statusClass"></view>
					<text class="status-text">{{ statusText }}</text>
				</view>
			</view>

			<!-- Device Info Card -->
			<view class="info-card">
				<view class="info-row">
					<text class="info-label">产品 ID</text>
					<text class="info-value">{{ productId }}</text>
				</view>
				<view class="info-row">
					<text class="info-label">设备名称</text>
					<text class="info-value">{{ deviceName }}</text>
				</view>
			</view>

			<!-- Loading -->
			<view v-if="loading" class="loading-wrap">
				<view class="loading-spinner"></view>
				<text class="loading-text">正在获取数据...</text>
			</view>

			<!-- Error -->
			<view v-if="errorMsg" class="error-card">
				<text class="error-text">{{ errorMsg }}</text>
			</view>

			<!-- Data Grid -->
			<view v-if="!loading && dataList.length > 0" class="data-grid">
				<view
					v-for="item in dataList"
					:key="item.id"
					class="data-card"
					:class="'card-' + getCardType(item.id)"
				>
					<text class="card-icon">{{ getIcon(item.id) }}</text>
					<view class="card-info">
						<text class="card-name">{{ item.name }}</text>
						<view class="card-value-row">
							<text class="card-value">{{ formatValue(item) }}</text>
							<text v-if="item.unit" class="card-unit">{{ item.unit }}</text>
						</view>
						<text v-if="item.time" class="card-time">{{ formatTime(item.time) }}</text>
					</view>
				</view>
			</view>

			<!-- Empty -->
			<view v-if="!loading && dataList.length === 0 && !errorMsg" class="empty-wrap">
				<text class="material-icons empty-icon">sensors_off</text>
				<text class="empty-text">暂无数据</text>
			</view>

			<!-- Refresh Button -->
			<view class="btn-wrap">
				<view class="refresh-btn" :class="{ disabled: loading }" @click="fetchData">
					<text class="material-icons" style="font-size:18px;vertical-align:middle;margin-right:6px;">refresh</text>
					<text>{{ loading ? '获取中...' : '刷新数据' }}</text>
				</view>
			</view>
		</view>
	</view>
</template>

<script>
import { getConfig } from '@/config/onenet.js'

const ICON_MAP = {
	temperature: '🌡',
	freezer_temp: '❄️',
	humidity: '💧',
	door_status: '🚪',
	power: '⚡',
}

export default {
	data() {
		return {
			productId: '',
			deviceName: '',
			dataList: [],
			loading: false,
			errorMsg: '',
			pollTimer: null,
		}
	},
	computed: {
		statusClass() {
			if (this.loading) return 'status-loading'
			if (this.errorMsg) return 'status-error'
			if (this.dataList.length > 0) return 'status-online'
			return 'status-offline'
		},
		statusText() {
			if (this.loading) return '连接中...'
			if (this.errorMsg) return '连接失败'
			if (this.dataList.length > 0) return '已连接'
			return '未连接'
		},
	},
	onLoad() {
		const config = getConfig()
		this.productId = config.productId
		this.deviceName = config.deviceName
		this.fetchData()
	},
	onShow() {},
	onHide() { this.stopPolling() },
	beforeUnmount() { this.stopPolling() },
	methods: {
		async fetchData() {
			this.loading = true
			this.errorMsg = ''
			try {
				this.dataList = result.sensorData ? Object.keys(result.sensorData).map(id => ({
					id,
					name: result.sensorData[id].name || id,
					value: result.sensorData[id].value,
					unit: result.sensorData[id].unit,
					time: result.sensorData[id].time,
				})) : []
			} catch (e) {
				this.errorMsg = e.message || '获取数据失败，请检查网络和配置'
			} finally {
				this.loading = false
			}
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

.header {
	text-align: center;
	padding: 32px 0 20px;
}
.header-title {
	font-size: 28px;
	font-weight: 900;
	color: var(--text-primary);
	letter-spacing: -0.5px;
	display: block;
}
.status-bar {
	display: flex;
	align-items: center;
	justify-content: center;
	margin-top: 10px;
}
.status-dot {
	width: 8px; height: 8px;
	border-radius: 50%;
	margin-right: 8px;
}
.status-online { background: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); }
.status-offline { background: var(--text-muted); }
.status-loading { background: var(--accent-orange); animation: blink 0.8s infinite; }
.status-error { background: var(--accent-red); }
.status-text { font-size: 13px; color: var(--text-secondary); }

@keyframes blink { 50% { opacity: 0.3; } }

/* Device Info */
.info-card {
	background: var(--bg-card);
	backdrop-filter: var(--glass-blur);
	-webkit-backdrop-filter: var(--glass-blur);
	border: 1px solid var(--border-card);
	border-radius: var(--radius-md);
	padding: 16px 20px;
	margin-bottom: 20px;
}
.info-row {
	display: flex;
	justify-content: space-between;
	padding: 8px 0;
}
.info-label { font-size: 13px; color: var(--text-muted); }
.info-value { font-size: 13px; color: var(--text-primary); font-weight: 500; }

/* Loading */
.loading-wrap {
	display: flex;
	flex-direction: column;
	align-items: center;
	padding: 60px 0;
}
.loading-spinner {
	width: 32px; height: 32px;
	border: 3px solid rgba(255,255,255,0.06);
	border-top-color: var(--accent-cyan);
	border-radius: 50%;
	animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-text { margin-top: 12px; font-size: 13px; color: var(--text-secondary); }

/* Error */
.error-card {
	background: rgba(239,68,68,0.08);
	border: 1px solid rgba(239,68,68,0.2);
	border-radius: var(--radius-md);
	padding: 20px;
	margin-bottom: 20px;
}
.error-text { font-size: 13px; color: var(--accent-red); text-align: center; display: block; }

/* Data Grid */
.data-grid {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 12px;
}
.data-card {
	background: var(--bg-card);
	backdrop-filter: var(--glass-blur);
	-webkit-backdrop-filter: var(--glass-blur);
	border: 1px solid var(--border-card);
	border-radius: var(--radius-md);
	padding: 20px 16px;
	display: flex;
	flex-direction: column;
	align-items: center;
	text-align: center;
}
.card-icon { font-size: 32px; margin-bottom: 8px; }
.card-name { font-size: 12px; color: var(--text-secondary); display: block; margin-bottom: 6px; }
.card-value-row { display: flex; align-items: baseline; justify-content: center; }
.card-value { font-size: 28px; font-weight: 800; color: var(--text-primary); }
.card-unit { font-size: 12px; color: var(--text-muted); margin-left: 4px; }
.card-time { font-size: 11px; color: var(--text-muted); display: block; margin-top: 4px; }

.card-temp .card-value { color: var(--accent-cyan); }
.card-energy .card-value { color: var(--accent-orange); }
.card-status .card-value { color: var(--accent-green); }

/* Empty */
.empty-wrap { text-align: center; padding: 60px 20px; }
.empty-icon {
	font-size: 56px !important;
	color: var(--text-muted);
	margin-bottom: 12px;
	display: block;
}
.empty-text { font-size: 14px; color: var(--text-secondary); display: block; }

/* Refresh Button */
.btn-wrap { padding: 24px 0 40px; text-align: center; }
.refresh-btn {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	padding: 14px 36px;
	background: rgba(0, 212, 255, 0.1);
	border: 1px solid rgba(0, 212, 255, 0.2);
	border-radius: 24px;
	color: var(--accent-cyan);
	font-size: 14px;
	font-weight: 600;
}
.refresh-btn:active { transform: scale(0.97); }
.refresh-btn.disabled { opacity: 0.4; pointer-events: none; }
</style>
