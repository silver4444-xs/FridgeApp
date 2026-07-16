/**
 * FridgeAI 前端统一配置
 *
 * 后端 URL 优先级:
 *   1. 用户在设置页手动填入的地址 (uni.getStorageSync('backend_url'))
 *   2. DEFAULT_BACKEND_URL 常量 (部署时修改此处即可)
 *
 * 用法:
 *   import { getBackendUrl, getWsUrl, getApiUrl, getStaticUrl } from '@/config/app.js'
 */

// === 部署时修改此值 ===
const DEFAULT_BACKEND_URL = 'http://localhost:8000'

export function getBackendUrl() {
	try {
		const stored = uni.getStorageSync('backend_url')
		if (stored) return stored.replace(/\/+$/, '')
	} catch (_) { /* ignore */ }
	return DEFAULT_BACKEND_URL
}

export function getWsUrl(path) {
	return getBackendUrl().replace(/^http/, 'ws') + path
}

export function getApiUrl(path) {
	return getBackendUrl() + '/api' + (path || '')
}

export function getStaticUrl(path) {
	return getBackendUrl() + '/static/' + (path || '')
}
