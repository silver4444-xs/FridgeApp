<template>
	<view class="chat-shell">
		<!-- Header -->
		<view class="chat-header">
			<view class="chat-avatar ai">
				<text class="material-icons">psychology</text>
			</view>
			<view class="chat-header-info">
				<text class="chat-header-name">AI 助手</text>
				<view class="chat-header-status">
					<view class="status-dot" :class="{ on: connected, off: !connected }"></view>
					<text class="status-text">{{ connected ? '在线' : '离线' }}</text>
				</view>
			</view>
		</view>

		<!-- Messages -->
		<scroll-view
			class="chat-body"
			scroll-y
			:scroll-top="scrollTop"
			:scroll-with-animation="true"
		>
			<!-- Quick Actions -->
			<view v-if="messages.length === 0 && !streaming" class="chat-welcome">
				<view class="welcome-avatar">
					<text class="material-icons">restaurant</text>
				</view>
				<text class="welcome-title">今天想吃什么？</text>
				<text class="welcome-sub">告诉 AI 你的口味偏好，为你智能推荐</text>
				<view class="quick-chips">
					<view class="quick-chip" @click="sendQuick('能做什么菜?')">
						<text class="material-icons chip-icon">stars</text>
						<text>能做什么菜?</text>
					</view>
					<view class="quick-chip" @click="sendQuick('推荐3道简单快手的菜')">
						<text class="material-icons chip-icon">bolt</text>
						<text>推荐3道快手菜</text>
					</view>
					<view class="quick-chip" @click="sendQuick('冰箱里有什么?')">
						<text class="material-icons chip-icon">kitchen</text>
						<text>冰箱里有什么?</text>
					</view>
				</view>
			</view>

			<!-- Message Bubbles -->
			<view
				v-for="(msg, idx) in messages"
				:key="idx"
				class="msg-row"
				:class="msg.role === 'user' ? 'msg-user' : 'msg-ai'"
			>
				<view v-if="msg.role === 'ai'" class="msg-avatar ai">
					<text class="material-icons">psychology</text>
				</view>
				<view class="msg-bubble" :class="msg.role === 'user' ? 'bubble-user' : 'bubble-ai'">
					<!-- User plain text -->
					<text v-if="msg.role === 'user'" class="msg-text">{{ msg.text }}</text>

					<!-- AI rich blocks -->
					<view v-if="msg.role === 'ai' && msg.blocks" class="msg-rich">
						<!-- Collapsed: first 3 blocks + expand -->
						<template v-if="msg.collapsed">
								<view v-for="(block, bi) in msg.blocks.slice(0, 3)" :key="bi" :class="'mb-' + block.type">
									<view v-if="block.type === 'table'" class="mb-table-wrap">
										<view class="mb-table-row mb-table-head"><text v-for="(h, hi) in block.header" :key="hi" class="mb-table-cell head">{{ h }}</text></view>
										<view v-for="(row, ri) in block.rows" :key="ri" class="mb-table-row" :class="{ alt: ri % 2 === 1 }"><text v-for="(cell, ci) in row" :key="ci" class="mb-table-cell">{{ cell }}</text></view>
									</view>
									<view v-else-if="block.type === 'divider'" class="mb-divider"></view>
									<view v-else-if="block.type === 'blockquote'" class="mb-blockquote"><text v-for="(seg, si) in block.inlines" :key="si" :class="'mi-' + seg.type">{{ seg.text }}</text></view>
									<view v-else class="mb-block-inner">
										<image v-if="block.image" :src="block.image" mode="aspectFill" class="mb-recipe-img" />
										<view class="mb-block-text"><text v-for="(seg, si) in block.inlines" :key="si" :class="'mi-' + seg.type">{{ seg.text }}</text></view>
									</view>
								</view>
							<view class="expand-row" @click="expandMsg(idx)">
								<text class="material-icons expand-icon">expand_more</text>
								<text class="expand-label">展开全文</text>
							</view>
						</template>
						<!-- Full -->
						<template v-else>
								<view v-for="(block, bi) in msg.blocks" :key="bi" :class="'mb-' + block.type">
									<view v-if="block.type === 'table'" class="mb-table-wrap">
										<view class="mb-table-row mb-table-head"><text v-for="(h, hi) in block.header" :key="hi" class="mb-table-cell head">{{ h }}</text></view>
										<view v-for="(row, ri) in block.rows" :key="ri" class="mb-table-row" :class="{ alt: ri % 2 === 1 }"><text v-for="(cell, ci) in row" :key="ci" class="mb-table-cell">{{ cell }}</text></view>
									</view>
									<view v-else-if="block.type === 'divider'" class="mb-divider"></view>
									<view v-else-if="block.type === 'blockquote'" class="mb-blockquote"><text v-for="(seg, si) in block.inlines" :key="si" :class="'mi-' + seg.type">{{ seg.text }}</text></view>
									<view v-else class="mb-block-inner">
										<image v-if="block.image" :src="block.image" mode="aspectFill" class="mb-recipe-img" />
										<view class="mb-block-text"><text v-for="(seg, si) in block.inlines" :key="si" :class="'mi-' + seg.type">{{ seg.text }}</text></view>
									</view>
								</view>
						</template>
					</view>

					<!-- Copy button -->
					<view v-if="msg.role === 'ai'" class="copy-row" @click="copyMsg(msg)">
						<text class="material-icons copy-icon">content_copy</text>
						<text class="copy-label">复制</text>
					</view>
				</view>
				<view v-if="msg.role === 'user'" class="msg-avatar user">
					<text class="material-icons">person</text>
				</view>
			</view>

			<!-- Tool Status -->
			<view v-if="toolStatus && streaming" class="tool-indicator">
				<view class="tool-dot"></view>
				<text class="tool-text">{{ toolStatus }}</text>
			</view>

			<!-- Streaming Bubble -->
			<view v-if="streaming && streamText" class="msg-row msg-ai">
				<view class="msg-avatar ai">
					<text class="material-icons">psychology</text>
				</view>
				<view class="msg-bubble bubble-ai streaming-bubble">
					<view class="msg-rich">
							<view v-for="(block, bi) in streamBlocks" :key="bi" :class="'mb-' + block.type">
									<view v-if="block.type === 'table'" class="mb-table-wrap">
										<view class="mb-table-row mb-table-head"><text v-for="(h, hi) in block.header" :key="hi" class="mb-table-cell head">{{ h }}</text></view>
										<view v-for="(row, ri) in block.rows" :key="ri" class="mb-table-row" :class="{ alt: ri % 2 === 1 }"><text v-for="(cell, ci) in row" :key="ci" class="mb-table-cell">{{ cell }}</text></view>
									</view>
									<view v-else-if="block.type === 'divider'" class="mb-divider"></view>
									<view v-else-if="block.type === 'blockquote'" class="mb-blockquote"><text v-for="(seg, si) in block.inlines" :key="si" :class="'mi-' + seg.type">{{ seg.text }}</text></view>
									<view v-else class="mb-block-inner">
										<image v-if="block.image" :src="block.image" mode="aspectFill" class="mb-recipe-img" />
										<view class="mb-block-text"><text v-for="(seg, si) in block.inlines" :key="si" :class="'mi-' + seg.type">{{ seg.text }}</text></view>
									</view>
								</view>
					</view>
					<text class="typing-cursor">|</text>
				</view>
			</view>

			<!-- HITL Approval -->
			<view v-if="interruptVisible" class="hitl-card">
				<view class="hitl-icon-wrap">
					<text class="material-icons hitl-icon">verified_user</text>
				</view>
				<text class="hitl-title">保存偏好到长期记忆？</text>
				<text class="hitl-desc">AI 会根据你的偏好提供更精准的推荐</text>
				<view class="hitl-actions">
					<view class="hitl-btn approve" @click="sendApprove">
						<text class="material-icons" style="font-size:16px;">check</text>
						<text>批准</text>
					</view>
					<view class="hitl-btn reject" @click="sendReject">
						<text class="material-icons" style="font-size:16px;">close</text>
						<text>拒绝</text>
					</view>
				</view>
			</view>

			<view style="height:8px;"></view>
		</scroll-view>

		<!-- Input Bar -->
		<view class="chat-input-bar">
			<view class="input-row">
				<input
					class="chat-input"
					v-model="input"
					placeholder="告诉冰箱你想吃什么..."
					:disabled="streaming"
					confirm-type="send"
					@confirm="send"
				/>
				<view
					class="send-btn"
					:class="{ disabled: streaming || !input.trim() }"
					@click="send"
				>
					<text class="material-icons send-icon">send</text>
				</view>
			</view>
		</view>
	</view>
</template>

<script>
import { connectAgentChat, sendAgentMessage, onAgentChat, disconnectAgentChat, resumeAgentChat } from '@/utils/agentChat.js'
import { store } from '@/utils/store.js'
import { getRecipeImage, FALLBACK_RECIPE } from '@/utils/imageResolver.js'

const TOOL_NAMES = {
	recipe_expert: '正在搜索菜谱...',
	substitution_expert: '正在查找替换方案...',
	cooking_expert: '正在检索烹饪知识...',
	recommend_by_fridge: '正在分析冰箱食材...',
	search_recipes_by_ingredients: '正在搜索菜谱...',
	get_recipe_detail: '正在获取菜谱详情...',
	find_substitutions: '正在查找替换食材...',
	search_cooking_knowledge: '正在检索知识库...',
	get_fridge_inventory: '正在读取冰箱库存...',
	save_user_preferences: '正在保存偏好...',
	get_user_preferences: '正在读取偏好...',
}

const COLLAPSE_THRESHOLD = 500

function parseInlines(text) {
	const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g)
	return parts.filter(Boolean).map(part => {
		if (/^\*\*.*\*\*$/.test(part)) return { type: 'bold', text: part.slice(2, -2) }
		if (/^\*.*\*$/.test(part)) return { type: 'italic', text: part.slice(1, -1) }
		if (/^`.*`$/.test(part)) return { type: 'code', text: part.slice(1, -1) }
		return { type: 'text', text: part }
	})
}

function parseMessage(text) {
	if (!text) return [{ type: 'paragraph', inlines: [{ type: 'text', text: '' }] }]
	const rawBlocks = text.split(/\n\n+/)
	return rawBlocks.map(block => {
		const trimmed = block.trim()
		if (!trimmed) return null

		if (/^[-*_]{3,}$/.test(trimmed)) return { type: 'divider' }

		const lines = trimmed.split('\n')
		if (lines.length >= 2 && lines.every(l => l.includes('|'))) {
			const clean = l => l.split('|').map(c => c.trim()).filter(c => c !== '')
			const header = clean(lines[0])
			const dataRows = lines.slice(1).filter(l => !/^[\s|:\-]+$/.test(l))
			const rows = dataRows.map(clean)
			if (header.length > 0 && rows.length > 0) {
				return { type: 'table', header, rows }
			}
		}

		if (/^>\s/.test(trimmed)) {
			const textContent = trimmed.replace(/^>\s?/gm, '')
			return { type: 'blockquote', inlines: parseInlines(textContent) }
		}

		if (/^#{1,3}\s/.test(trimmed)) {
			return { type: 'heading', inlines: parseInlines(trimmed.replace(/^#{1,3}\s/, '')) }
		}
		if (/^\d+[.、)]\s/.test(trimmed)) {
			return { type: 'list-item', inlines: parseInlines(trimmed.replace(/^\d+[.、)]\s/, '')) }
		}
		if (/^[-•]\s/.test(trimmed)) {
			return { type: 'bullet', inlines: parseInlines(trimmed.replace(/^[-•]\s/, '')) }
		}
		return { type: 'paragraph', inlines: parseInlines(trimmed) }
	}).filter(Boolean)
}

function enrichBlocks(blocks) {
	for (const block of blocks) {
		if (!block.inlines) continue
		for (const seg of block.inlines) {
			if (seg.type !== 'bold') continue
			const img = getRecipeImage(seg.text)
			if (img && img !== FALLBACK_RECIPE) {
				block.image = img
				break
			}
		}
	}
	return blocks
}

export default {
	name: 'AgentChatBox',
	data() {
		return {
			input: '',
			streaming: false,
			streamText: '',
			toolStatus: '',
			messages: [],
			threadId: '',
			interruptVisible: false,
			scrollTop: 0,
		}
	},
	computed: {
		connected() { return store.agentChatConnected },
		streamBlocks() { return parseMessage(this.streamText) },
	},
	mounted() {
		this.threadId = uni.getStorageSync('agent_thread_id') || ''
		onAgentChat('token', (t) => {
			this.streamText += t
			this.$nextTick(() => { this.scrollToBottom() })
		})
		onAgentChat('toolStart', (d) => {
			this.toolStatus = TOOL_NAMES[d.tool] || ('正在调用 ' + d.tool)
		})
		onAgentChat('toolEnd', () => { this.toolStatus = '' })
		onAgentChat('done', () => {
			if (this.streamText) {
				const blocks = enrichBlocks(parseMessage(this.streamText))
				this.messages.push({
					role: 'ai',
					text: this.streamText,
					blocks,
					collapsed: this.streamText.length > COLLAPSE_THRESHOLD,
				})
			}
			this.streamText = ''
			this.streaming = false
			this.toolStatus = ''
			this.interruptVisible = false
			this.$nextTick(() => { this.scrollToBottom() })
		})
		onAgentChat('error', (err) => {
			this.toolStatus = '错误: ' + err
			this.streaming = false
		})
		onAgentChat('toolStart', (d) => {
			if (d.tool === 'save_user_preferences') { this.interruptVisible = true }
		})
		connectAgentChat()
	},
	watch: {
		'store.agentChatConnected'(val) {
			if (!val && this.streaming) {
				this.streaming = false
				this.toolStatus = '连接断开，正在重连...'
			}
		},
	},
	beforeDestroy() { disconnectAgentChat() },
	methods: {
		send() {
			const msg = this.input.trim()
			if (!msg || this.streaming) return
			this.messages.push({ role: 'user', text: msg })
			this.input = ''
			this.streamText = ''
			this.streaming = true
			this.toolStatus = '思考中...'
			this.$nextTick(() => { this.scrollToBottom() })
			sendAgentMessage(msg, this.threadId)
		},
		sendQuick(msg) { this.input = msg; this.send() },
		sendApprove() { this.interruptVisible = false; resumeAgentChat(this.threadId, 'approve') },
		sendReject() { this.interruptVisible = false; resumeAgentChat(this.threadId, 'reject') },
		copyMsg(msg) {
			uni.setClipboardData({ data: msg.text, showToast: false })
			uni.showToast({ title: '已复制', icon: 'success', duration: 1500 })
		},
		expandMsg(idx) {
			this.$set(this.messages[idx], 'collapsed', false)
			this.$nextTick(() => { this.scrollToBottom() })
		},
		scrollToBottom() {
			this.scrollTop = this.scrollTop + 1
		},
	},
}
</script>

<style scoped>
.chat-shell {
	display: flex;
	flex-direction: column;
	height: 520px;
	background: rgba(255, 255, 255, 0.02);
	border: 1px solid rgba(255, 255, 255, 0.06);
	border-radius: 16px;
	overflow: hidden;
}

.chat-header {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 12px 16px;
	border-bottom: 1px solid rgba(255, 255, 255, 0.05);
	flex-shrink: 0;
}

.chat-avatar {
	width: 38px; height: 38px;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	flex-shrink: 0;
}
.chat-avatar.ai { background: linear-gradient(135deg, rgba(0, 212, 255, 0.2), rgba(124, 58, 237, 0.2)); }
.chat-avatar .material-icons { font-size: 20px !important; color: #00d4ff; }

.msg-avatar {
	width: 32px; height: 32px;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	flex-shrink: 0;
}
.msg-avatar.ai { background: rgba(0, 212, 255, 0.12); }
.msg-avatar.ai .material-icons { font-size: 16px !important; color: #00d4ff; }
.msg-avatar.user { background: rgba(168, 85, 247, 0.15); }
.msg-avatar.user .material-icons { font-size: 16px !important; color: #a855f7; }

.chat-header-info { flex: 1; }
.chat-header-name { font-size: 15px; font-weight: 700; color: #e0e0e0; display: block; }
.chat-header-status { display: flex; align-items: center; gap: 4px; margin-top: 2px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; }
.status-dot.on { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.5); }
.status-dot.off { background: #484f58; }
.status-text { font-size: 11px; color: #8b949e; }

.chat-body { flex: 1; padding: 12px 12px 0; overflow-y: auto; }

.chat-welcome { display: flex; flex-direction: column; align-items: center; padding: 32px 12px 20px; }
.welcome-avatar {
	width: 60px; height: 60px; border-radius: 50%;
	background: linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(124, 58, 237, 0.15));
	border: 2px solid rgba(0, 212, 255, 0.15);
	display: flex; align-items: center; justify-content: center;
	margin-bottom: 14px;
}
.welcome-avatar .material-icons { font-size: 30px !important; color: #00d4ff; }
.welcome-title { font-size: 18px; font-weight: 800; color: #e0e0e0; }
.welcome-sub { font-size: 12px; color: #8b949e; margin-top: 6px; text-align: center; }

.quick-chips { display: flex; flex-direction: column; gap: 8px; margin-top: 20px; width: 100%; max-width: 260px; }
.quick-chip {
	display: flex; align-items: center; gap: 8px;
	padding: 12px 16px; border-radius: 14px;
	font-size: 13px; font-weight: 600; color: #e0e0e0;
	background: rgba(255, 255, 255, 0.04);
	border: 1px solid rgba(255, 255, 255, 0.08);
	transition: all 0.2s ease;
}
.quick-chip:active { background: rgba(0, 212, 255, 0.1); border-color: rgba(0, 212, 255, 0.2); transform: scale(0.98); }
.chip-icon { font-size: 18px !important; color: #00d4ff; }

.msg-row { display: flex; align-items: flex-end; gap: 8px; margin-bottom: 14px; }
.msg-user { justify-content: flex-end; }
.msg-ai { justify-content: flex-start; }

.msg-bubble { max-width: 85%; padding: 12px 14px; border-radius: 18px; }
.bubble-user { background: linear-gradient(135deg, #7c3aed, #6366f1); border-bottom-right-radius: 6px; }
.bubble-ai { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.06); border-bottom-left-radius: 6px; }

/* Rich blocks */
.msg-rich { display: flex; flex-direction: column; gap: 10px; }

/* Table */
.mb-table-wrap { border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; overflow: hidden; }
.mb-table-row { display: flex; }
.mb-table-head { background: rgba(0, 212, 255, 0.08); }
.mb-table-row.alt { background: rgba(255, 255, 255, 0.02); }
.mb-table-cell {
	flex: 1; padding: 7px 8px;
	font-size: 12px; color: #c0c0c0;
	line-height: 1.4; text-align: center;
	border-right: 1px solid rgba(255, 255, 255, 0.04);
	word-break: break-word;
}
.mb-table-cell:last-child { border-right: none; }
.mb-table-cell.head { font-weight: 700; color: #e0e0e0; font-size: 12px; padding: 8px; }

/* Divider */
.mb-divider {
	height: 1px; margin: 4px 0;
	background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
}

/* Blockquote */
.mb-blockquote {
	padding: 8px 12px;
	border-left: 3px solid rgba(0, 212, 255, 0.4);
	background: rgba(0, 212, 255, 0.04);
	border-radius: 0 8px 8px 0;
	font-style: italic;
}

/* Block inner (with optional image) */
.mb-block-inner { display: flex; gap: 10px; }
.mb-recipe-img { width: 52px; height: 52px; border-radius: 10px; object-fit: cover; flex-shrink: 0; }
.mb-block-text { flex: 1; min-width: 0; }

/* Block types */
.mb-heading { padding-bottom: 2px; }
.mb-list-item { padding: 6px 0 6px 4px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); line-height: 1.5; }
.mb-list-item:last-child { border-bottom: none; }
.mb-bullet { padding: 3px 0 3px 4px; line-height: 1.5; }
.mb-paragraph { line-height: 1.55; }

/* Inline types */
.mi-text { font-size: 14px; color: #d0d0d0; line-height: 1.55; }
.mi-bold { font-size: 14px; font-weight: 800; color: #f0f0f0; }
.mi-italic { font-size: 14px; font-style: italic; color: #b0b0b0; }
.mi-code {
	font-size: 13px; font-family: 'SF Mono', 'Menlo', monospace;
	background: rgba(255, 255, 255, 0.08);
	border-radius: 4px; padding: 1px 6px; color: #e0e0e0;
}

/* Plain text fallback */
.msg-text { font-size: 14px; line-height: 1.55; color: #e0e0e0; word-break: break-word; white-space: pre-wrap; }

/* Expand button */
.expand-row {
	display: flex; align-items: center; justify-content: center; gap: 2px;
	padding: 10px 0 4px; border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.expand-icon { font-size: 16px !important; color: #00d4ff; }
.expand-label { font-size: 12px; font-weight: 600; color: #00d4ff; }

/* Copy row */
.copy-row {
	display: flex; align-items: center; justify-content: flex-end; gap: 4px;
	margin-top: 10px; padding-top: 8px;
	border-top: 1px solid rgba(255, 255, 255, 0.06);
	opacity: 0; transition: opacity 0.2s ease;
}
.msg-bubble:active .copy-row, .msg-row:active .copy-row { opacity: 1; }
.copy-icon { font-size: 13px !important; color: #8b949e; }
.copy-label { font-size: 11px; color: #8b949e; font-weight: 500; }
.copy-row:active { opacity: 0.7; }

/* Typing cursor */
.typing-cursor { color: #00d4ff; font-weight: 700; animation: blink 0.8s step-end infinite; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

.streaming-bubble { min-height: 20px; display: flex; flex-direction: row; align-items: flex-start; gap: 2px; }

/* Tool status */
.tool-indicator { display: flex; align-items: center; gap: 8px; padding: 8px 16px; margin: 0 0 14px 40px; }
.tool-dot {
	width: 8px; height: 8px; border-radius: 50%; background: #f59e0b;
	animation: tool-pulse 1.2s ease-in-out infinite;
}
@keyframes tool-pulse { 0%, 100% { opacity: 0.4; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1); } }
.tool-text { font-size: 12px; color: #8b949e; }

/* HITL */
.hitl-card {
	margin: 8px 0 16px 40px; padding: 16px;
	background: rgba(0, 212, 255, 0.06); border: 1px solid rgba(0, 212, 255, 0.15); border-radius: 16px;
}
.hitl-icon-wrap { width: 36px; height: 36px; border-radius: 50%; background: rgba(0, 212, 255, 0.12); display: flex; align-items: center; justify-content: center; margin-bottom: 10px; }
.hitl-icon { font-size: 20px !important; color: #00d4ff; }
.hitl-title { font-size: 14px; font-weight: 700; color: #e0e0e0; display: block; }
.hitl-desc { font-size: 12px; color: #8b949e; margin-top: 4px; display: block; }
.hitl-actions { display: flex; gap: 10px; margin-top: 14px; }
.hitl-btn { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px 0; border-radius: 12px; font-size: 13px; font-weight: 700; transition: all 0.2s ease; }
.hitl-btn.approve { background: rgba(34, 197, 94, 0.12); border: 1px solid rgba(34, 197, 94, 0.2); color: #22c55e; }
.hitl-btn.approve:active { background: rgba(34, 197, 94, 0.2); }
.hitl-btn.reject { background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.12); color: #f87171; }
.hitl-btn.reject:active { background: rgba(239, 68, 68, 0.15); }

/* Input */
.chat-input-bar { padding: 10px 12px 12px; border-top: 1px solid rgba(255, 255, 255, 0.05); flex-shrink: 0; }
.input-row { display: flex; align-items: center; gap: 8px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 24px; padding: 4px 4px 4px 16px; }
.chat-input { flex: 1; height: 38px; font-size: 14px; color: #e0e0e0; border: none; background: transparent; outline: none; }
.chat-input::placeholder { color: #484f58; font-size: 13px; }
.chat-input:disabled { opacity: 0.5; }
.send-btn { width: 38px; height: 38px; border-radius: 50%; background: linear-gradient(135deg, #00d4ff, #7c3aed); display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: all 0.2s ease; }
.send-btn:active { transform: scale(0.92); opacity: 0.85; }
.send-btn.disabled { opacity: 0.25; pointer-events: none; }
.send-icon { font-size: 18px !important; color: #fff; }
</style>
