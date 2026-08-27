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
// API Key 一律不内置默认值 —— 前端产物会被打包分发，写死等同公开泄露。
// 取值来源：用户在设置页填入，存于 uni.getStorageSync('api_key')。
// 留空时 getWsUrl() 不拼接 api_key 参数，后端开发模式仍可连通；
// 生产环境（后端已设 API_KEY）必须由用户在设置页配置。
const DEFAULT_API_KEY = ''

export function getBackendUrl() {
	try {
		const stored = uni.getStorageSync('backend_url')
		if (stored) return stored.replace(/\/+$/, '')
	} catch (_) { /* ignore */ }
	return DEFAULT_BACKEND_URL
}

export function getApiKey() {
	try {
		const stored = uni.getStorageSync('api_key')
		if (stored) return stored
	} catch (_) { /* ignore */ }
	return DEFAULT_API_KEY
}

export function getApiHeaders() {
	return { 'X-API-Key': getApiKey() }
}

export function getWsUrl(path) {
	const base = getBackendUrl().replace(/^http/, 'ws') + path
	const key = getApiKey()
	return key ? `${base}?api_key=${encodeURIComponent(key)}` : base
}

export function getApiUrl(path) {
	return getBackendUrl() + '/api' + (path || '')
}

export function getStaticUrl(path) {
	return getBackendUrl() + '/static/' + (path || '')
}
