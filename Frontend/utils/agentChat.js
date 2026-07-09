/**
 * Agent 流式对话客户端 — 连接 /ws/chat 端点
 * Phase 5 后端已就绪，Phase 8 前端接入
 *
 * 原代码: 无 Agent 对话功能，仅 OneNET 数据推送 /ws/fridge
 * 改进后: WebSocket 流式对话，打字机效果 + 工具状态提示
 */
import { store } from './store.js'

let wsTask = null
let reconnectTimer = null
const listeners = { token: [], toolStart: [], toolEnd: [], toolError: [], done: [], error: [] }

function getChatWsUrl() {
	try {
		const url = uni.getStorageSync('backend_url') || 'http://localhost:8000'
		return url.replace(/^http/, 'ws') + '/ws/chat'
	} catch (_) {
		return 'ws://localhost:8000/ws/chat'
	}
}

export function onAgentChat(event, callback) {
	if (listeners[event]) listeners[event].push(callback)
}

export function offAgentChat(event, callback) {
	if (listeners[event]) listeners[event] = listeners[event].filter(cb => cb !== callback)
}

function _emit(event, data) {
	if (listeners[event]) listeners[event].forEach(cb => { try { cb(data) } catch (_) {} })
}

export function connectAgentChat() {
	if (wsTask) { try { wsTask.close({}) } catch (_) {}; wsTask = null }
	const url = getChatWsUrl()
	console.log('[AgentChat] Connecting:', url)

	try {
		wsTask = uni.connectSocket({ url, complete: () => {} })

		wsTask.onOpen(() => {
			console.log('[AgentChat] Connected')
			store.agentChatConnected = true
		})

		wsTask.onMessage((res) => {
			try {
				const data = JSON.parse(res.data)
				switch (data.type) {
					case 'stream_token': _emit('token', data.token); break
					case 'stream_tool_start': _emit('toolStart', data); break
					case 'stream_tool_end': _emit('toolEnd', data); break
					case 'stream_tool_error': _emit('toolError', { tool: data.tool, error: data.error }); break
					case 'stream_done': _emit('done'); break
					case 'stream_error': _emit('error', data.error); break
				}
			} catch (e) { console.warn('[AgentChat] Parse error:', e) }
		})

		wsTask.onError((err) => {
			console.error('[AgentChat] Error:', err)
			_emit('error', 'WebSocket 连接失败')
		})

		wsTask.onClose(() => {
			console.warn('[AgentChat] Closed, reconnecting in 3s...')
			store.agentChatConnected = false
			wsTask = null
			clearTimeout(reconnectTimer)
			reconnectTimer = setTimeout(connectAgentChat, 3000)
		})
	} catch (e) {
		console.error('[AgentChat] Connect failed:', e)
	}
}

export function sendAgentMessage(message, threadId) {
	if (!threadId) {
		threadId = uni.getStorageSync('agent_thread_id') || ('user_' + Date.now())
		uni.setStorageSync('agent_thread_id', threadId)
	}
	if (!wsTask) {
		_emit('error', 'WebSocket 未连接，正在重连...')
		connectAgentChat()
		setTimeout(() => {
			if (wsTask) wsTask.send({ data: JSON.stringify({ type: 'chat', message, thread_id: threadId }) })
		}, 1000)
		return
	}
	wsTask.send({ data: JSON.stringify({ type: 'chat', message, thread_id: threadId }) })
	console.log('[AgentChat] Sent:', message.slice(0, 50))
}

export function resumeAgentChat(threadId, decision) {
	if (!threadId) {
		threadId = uni.getStorageSync('agent_thread_id') || ('user_' + Date.now())
	}
	if (!wsTask) {
		_emit('error', 'WebSocket not connected')
		return
	}
	wsTask.send({ data: JSON.stringify({ type: 'resume', thread_id: threadId, decision }) })
	console.log('[AgentChat] Resume sent:', decision)
}

export function disconnectAgentChat() {
	clearTimeout(reconnectTimer)
	if (wsTask) { try { wsTask.close({}) } catch (_) {}; wsTask = null }
	store.agentChatConnected = false
}
