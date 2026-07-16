/**
 * 云端同步服务 — 通过后端 WebSocket (自动重连)
 */
import { store } from './store.js'
import { getWsUrl } from '@/config/app.js'

let backendWsTask = null
let reconnectTimer = null

export function connectBackendWs() {
	if (backendWsTask) { try { backendWsTask.close({}) } catch (_) {}; backendWsTask = null }
	try {
		const wsUrl = getWsUrl('/ws/fridge')
		console.log('[CloudSync] Connecting WS:', wsUrl)
		backendWsTask = uni.connectSocket({ url: wsUrl, complete: () => {} })

		backendWsTask.onOpen(() => {
			store.backendWsConnected = true
			store.cloudConnected = true
			console.log('[CloudSync] WS connected')
		})

		backendWsTask.onMessage((res) => {
			try {
				const msg = JSON.parse(res.data)
				if (msg.type === 'food_update' && msg.foodItems) {
					console.log('[CloudSync] WS received', msg.foodItems.length, 'items')
					store.mergeCloudFoods(msg.foodItems)
					store.cloudLastSync = msg.timestamp || new Date().toISOString()
				}
			} catch (e) { console.warn('[CloudSync] Parse error:', e) }
		})

		backendWsTask.onClose(() => {
			console.warn('[CloudSync] WS closed, reconnecting in 2s...')
			store.backendWsConnected = false
			backendWsTask = null
			clearTimeout(reconnectTimer)
			reconnectTimer = setTimeout(connectBackendWs, 2000)
		})

		backendWsTask.onError((e) => {
			console.warn('[CloudSync] WS error:', e.errMsg)
			store.backendWsConnected = false
		})
	} catch (e) {
		console.warn('[CloudSync] WS connect failed, retrying in 3s:', e)
		store.backendWsConnected = false
		reconnectTimer = setTimeout(connectBackendWs, 3000)
	}
}

export function uploadViaWs(foods) {
	if (!backendWsTask || !store.backendWsConnected) {
		console.warn('[CloudSync] WS not connected, upload skipped')
		return
	}
	// Fix #7: 使用 _foods (原始数组) 而非 foods (computed 去重数组) 上传
	// 原有逻辑: uploadViaWs(store.foods) — store.foods 是 computed 属性，按 name|cat 去重
	//   用户有意添加两条同名同类食材时，去重会丢失一条
	// 修复后: 优先使用 store._foods 原始数据，保留全部记录
	const source = foods || store._foods
	const payload = JSON.stringify({ type: 'food_upload', foods: source.map(f => ({
		name: f.enName || f.name, category: f.cat, quantity: f.qty, calories: f.calories ?? null
	})) })
	console.log('[CloudSync] Uploading', source.length, 'foods via WS')
	backendWsTask.send({ data: payload })
}

export function requestSync() {
	if (backendWsTask && store.backendWsConnected) {
		backendWsTask.send({ data: '{"type":"request_sync"}' })
	}
}

export function stopCloudSync() {
	clearTimeout(reconnectTimer)
	reconnectTimer = null
	if (backendWsTask) { try { backendWsTask.close({}) } catch (_) {}; backendWsTask = null }
	store.backendWsConnected = false
}
