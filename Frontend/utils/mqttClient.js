/**
 * OneNET MQTT 实时推送客户端 (MQTT 3.1.1 over WebSocket)
 *
 * 通过 WebSocket 连接 OneNET MQTT Broker，订阅设备数据上报主题。
 * 设备数据变化时 OneNET 立即推送，前端毫秒级响应。
 *
 * 无外部依赖，仅使用 uni-app 内置 WebSocket API。
 *
 * 使用方式：
 *   import { mqttClient } from '@/utils/mqttClient.js'
 *   mqttClient.connect()   // App.vue onLaunch
 *   mqttClient.disconnect() // App.vue onHide
 */

import { store } from './store.js'
import { ONENET_CONFIG } from '@/config/onenet.js'

// ======================== MQTT 协议编码 ========================

function encodeRemainingLength(len) {
	const buf = []
	do {
		let b = len & 0x7F
		len >>>= 7
		if (len > 0) b |= 0x80
		buf.push(b)
	} while (len > 0)
	return new Uint8Array(buf)
}

function decodeRemainingLength(bytes, offset) {
	let len = 0, multiplier = 1, pos = offset
	while (pos < bytes.length) {
		const b = bytes[pos++]
		len += (b & 0x7F) * multiplier
		if ((b & 0x80) === 0) break
		multiplier *= 128
	}
	return { length: len, bytesUsed: pos - offset }
}

function encodeUTF8(str) {
	const encoder = new TextEncoder()
	const encoded = encoder.encode(str)
	const len = encoded.length
	const buf = new Uint8Array(2 + len)
	buf[0] = (len >> 8) & 0xFF
	buf[1] = len & 0xFF
	buf.set(encoded, 2)
	return buf
}

function concat(...arrays) {
	const total = arrays.reduce((s, a) => s + a.length, 0)
	const result = new Uint8Array(total)
	let offset = 0
	for (const a of arrays) {
		result.set(a, offset)
		offset += a.length
	}
	return result
}

function buildConnectPacket(clientId, username, password) {
	const protoName = encodeUTF8('MQTT')
	const protoLevel = new Uint8Array([0x04])      // MQTT 3.1.1
	const flags = new Uint8Array([0xC2])            // clean session, username, password
	const keepAlive = new Uint8Array([0x00, 0x3C])  // 60s

	const varHeader = concat(protoName, protoLevel, flags, keepAlive)

	const cid = encodeUTF8(clientId)
	const user = encodeUTF8(username)
	const pass = encodeUTF8(password)
	const payload = concat(cid, user, pass)

	const remaining = encodeRemainingLength(varHeader.length + payload.length)
	const fixedHeader = new Uint8Array([0x10, ...remaining])

	return concat(fixedHeader, varHeader, payload)
}

function buildSubscribePacket(packetId, topics) {
	const pid = new Uint8Array([(packetId >> 8) & 0xFF, packetId & 0xFF])
	let payload = new Uint8Array(0)
	for (const topic of topics) {
		const t = encodeUTF8(topic)
		const qos = new Uint8Array([0x00])
		payload = concat(payload, t, qos)
	}
	const remaining = encodeRemainingLength(pid.length + payload.length)
	const fixedHeader = new Uint8Array([0x82, ...remaining])
	return concat(fixedHeader, pid, payload)
}

function buildPublishPacket(topic, payloadStr, qos) {
	const t = encodeUTF8(topic)
	let pktIdBytes = new Uint8Array(0)
	if (qos > 0) {
		pktIdBytes = new Uint8Array([0x00, 0x01])
	}
	const payloadBytes = new TextEncoder().encode(payloadStr)
	const varHeader = concat(t, pktIdBytes)
	const remaining = encodeRemainingLength(varHeader.length + payloadBytes.length)
	const headerByte = 0x30 | ((qos & 0x03) << 1)
	const fixedHeader = new Uint8Array([headerByte, ...remaining])
	return concat(fixedHeader, varHeader, payloadBytes)
}

function buildPingReqPacket() {
	return new Uint8Array([0xC0, 0x00])
}

// ======================== MQTT 协议解码 ========================

function decodePublishPacket(bytes) {
	let pos = 0
	const header = bytes[pos++]
	const qos = (header >> 1) & 0x03

	const rl = decodeRemainingLength(bytes, pos)
	pos += rl.bytesUsed

	const topicLen = (bytes[pos] << 8) | bytes[pos + 1]
	pos += 2
	const topic = new TextDecoder().decode(bytes.slice(pos, pos + topicLen))
	pos += topicLen

	let packetId = 0
	if (qos > 0) {
		packetId = (bytes[pos] << 8) | bytes[pos + 1]
		pos += 2
	}

	const payload = bytes.slice(pos)
	return { topic, payload, qos, packetId }
}

// ======================== MQTT 客户端 ========================

const RECONNECT_DELAYS = [500, 1000, 2000, 4000, 8000, 16000, 30000, 60000]
const KEEPALIVE = 55_000

class MqttClient {
	constructor() {
		this._socketTask = null
		this._connected = false
		this._reconnectIdx = 0
		this._reconnectTimer = null
		this._pingTimer = null
		this._packetId = 1
	}

	get connected() { return this._connected }

	connect() {
		if (this._connected) return
			if (this._socketTask) { try { this._socketTask.close({}) } catch (_) {} this._socketTask = null }
		this._doConnect()
	}

	disconnect() {
		this._reconnectIdx = Infinity
		this._clearTimers()
		if (this._socketTask) {
			try { this._socketTask.close({}) } catch (_) {}
			this._socketTask = null
		}
		this._connected = false
		store.mqttConnected = false
			console.log('[MQTT] 已断开')
	}

	_doConnect() {
		const { token, clientId, username } = this._generateAuth()
		const wsUrl = `wss://${ONENET_CONFIG.mqttBroker}:${ONENET_CONFIG.wsPort}/mqtt`

		console.log('[MQTT] 正在连接...', wsUrl.substring(0, 40) + '...')

		this._socketTask = uni.connectSocket({
			url: wsUrl,
			complete: () => {},
		})

		this._socketTask.onOpen(() => {
			console.log('[MQTT] WebSocket 已连接，发送 MQTT CONNECT')
			const pkt = buildConnectPacket(clientId, username, token)
			this._socketTask.send({
				data: pkt.buffer,
				success: () => console.log('[MQTT] CONNECT 已发送'),
				fail: (e) => console.error('[MQTT] CONNECT 发送失败:', e),
			})
		})

		this._socketTask.onMessage((res) => {
			const bytes = new Uint8Array(res.data)
			this._handleMessage(bytes)
		})

		this._socketTask.onClose((e) => {
			console.warn('[MQTT] 连接关闭:', e.code, e.reason)
			this._connected = false
			this._clearTimers()
			this._socketTask = null
			this._scheduleReconnect()
		})

		this._socketTask.onError((e) => {
			console.error('[MQTT] 连接错误:', e.errMsg)
			this._connected = false
			try { this._socketTask.close({}) } catch (_) {}
			this._socketTask = null
			this._clearTimers()
			this._scheduleReconnect()
		})
	}

	_handleMessage(bytes) {
		if (bytes.length === 0) return
		const type = (bytes[0] >> 4) & 0x0F

		switch (type) {
			case 2: { // CONNACK
				const code = bytes[3]
				if (code === 0) {
					console.log('[MQTT] 认证成功')
					this._connected = true
					store.mqttConnected = true
					this._reconnectIdx = 0
					this._subscribe()
					this._startPing()
				} else {
					console.error('[MQTT] 认证失败，错误码:', code)
				}
				break
			}
			case 3: { // PUBLISH
				try {
					const pub = decodePublishPacket(bytes)
					this._onDataPush(pub.topic, pub.payload)
				} catch (e) {
					console.error('[MQTT] 解析 PUBLISH 失败:', e)
				}
				break
			}
			case 9: // SUBACK
				console.log('[MQTT] 订阅成功')
				break
			case 13: // PINGRESP
				break
		}
	}

	/** 发布消息到指定主题 */
	publish(topic, payload) {
		if (!this._connected || !this._socketTask) {
			console.warn('[MQTT] 未连接，无法发布')
			return false
		}
		const pkt = buildPublishPacket(topic, typeof payload === 'string' ? payload : JSON.stringify(payload), 1)
		this._socketTask.send({
			data: pkt.buffer,
			success: () => console.log('[MQTT] PUBLISH 成功:', topic),
			fail: (e) => console.error('[MQTT] PUBLISH 失败:', e),
		})
		return true
	}

	_subscribe() {
		const topics = [
			`$sys/${ONENET_CONFIG.productId}/${ONENET_CONFIG.deviceName}/dp/post/json/+`,
			`$sys/${ONENET_CONFIG.productId}/${ONENET_CONFIG.deviceName}/thing/property/post/reply`,
		]
		const pkt = buildSubscribePacket(this._packetId++, topics)
		this._socketTask.send({
			data: pkt.buffer,
			success: () => console.log('[MQTT] SUBSCRIBE 已发送'),
			fail: (e) => console.error('[MQTT] SUBSCRIBE 失败:', e),
		})
	}

	_onDataPush(topic, payloadBytes) {
		try {
			const json = new TextDecoder().decode(payloadBytes)
			const msg = JSON.parse(json)
			console.log('========== [MQTT] 实时推送 ==========')
			console.log('  Topic :', topic)
			console.log('  时间  :', new Date().toLocaleTimeString('zh-CN', { hour12: false }))
			console.log('  原始数据:', JSON.stringify(msg, null, 2))

			const params = msg.params || msg.data || msg
			const sensorData = {}
			const foodItems = []

			for (const [identifier, val] of Object.entries(params)) {
				const value = (val && typeof val === 'object') ? val.value : val
				const id = identifier.toLowerCase()

				if (id.includes('temp') || id.includes('humidity') || id.includes('door') || id.includes('power')) {
					sensorData[id] = { value: isNaN(value) ? value : parseFloat(value), time: new Date().toISOString() }
				}
				if (id.includes('food') || id.includes('item') || id.includes('inventory')) {
					const parsed = this._parseFoodProperty(id, value)
					if (parsed) foodItems.push(...parsed)
				}
			}

			if (Object.keys(sensorData).length > 0) {
				console.log('  [MQTT] 传感器:', JSON.stringify(sensorData, null, 2))
				store.updateDeviceStatus({
					temperature: sensorData['temperature']?.value ?? sensorData['temp']?.value,
					freezerTemp: sensorData['freezer_temp']?.value ?? sensorData['freezertemp']?.value,
					humidity: sensorData['humidity']?.value,
					doorStatus: sensorData['door_status']?.value ?? sensorData['doorstatus']?.value,
					power: sensorData['power']?.value,
				})
			}
			if (foodItems.length > 0) {
				console.log('  [MQTT] 食材:', JSON.stringify(foodItems, null, 2))
				store.mergeCloudFoods(foodItems)
			}

			store.cloudLastSync = new Date().toISOString()
				console.log('====================================')
			} catch (e) {
			console.error('[MQTT] 数据处理失败:', e)
		}
	}

	_parseFoodProperty(identifier, value) {
		if (value === null || value === undefined) return null
		if (typeof value === 'string') {
			if (value.startsWith('{') || value.startsWith('[')) {
				try {
					const obj = JSON.parse(value)
					if (Array.isArray(obj)) {
						return obj.map(item => this._normalizeFoodItem(item, identifier)).filter(Boolean)
					}
					return [this._normalizeFoodItem(obj, identifier)].filter(Boolean)
				} catch (_) {}
			}
		}
		const name = identifier.replace(/^(food_|item_|inventory_)/, '').replace(/_/g, ' ')
		return [{ name: name || identifier, cat: 'packaged', qty: parseFloat(value) || 1, unit: '个', fromCloud: true }]
	}

	_normalizeFoodItem(obj, identifier) {
		if (!obj || typeof obj !== 'object') return null
		return {
			name: obj.name || obj.n || obj.title || identifier || '',
			cat: obj.cat || obj.category || obj.c || 'packaged',
			qty: parseFloat(obj.qty || obj.q || obj.quantity || 1) || 1,
			unit: obj.unit || obj.u || '个',
			expiry: obj.expiry_date || obj.expiry || obj.exp || obj.e || null,
			calories: obj.calories || obj.cal || null,
			photo: obj.photo || obj.img || obj.p || null,
			fromCloud: true,
		}
	}

	// ---- 认证 ----

	_generateAuth() {
		const version = '2018-10-31'
		const res = `products/${ONENET_CONFIG.productId}/devices/${ONENET_CONFIG.deviceName}`
		const et = Math.floor(Date.now() / 1000) + 86400 * 365
		const method = 'md5'

		const stringToSign = `${et}\n${method}\n${res}\n${version}`
		const keyBytes = this._base64Decode(ONENET_CONFIG.deviceSecret)
		const signBase64 = this._hmacMd5(keyBytes, stringToSign)
		const encRes = encodeURIComponent(res)
		const encSign = encodeURIComponent(signBase64)
		const token = `version=${version}&res=${encRes}&et=${et}&method=${method}&sign=${encSign}`

		return { token, clientId: ONENET_CONFIG.deviceName, username: ONENET_CONFIG.productId }
	}

	_base64Decode(str) {
		try {
			const binary = atob(str)
			const bytes = new Uint8Array(binary.length)
			for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
			return bytes
		} catch (_) { return new Uint8Array(0) }
	}

	_hmacMd5(keyBytes, str) {
		const blockSize = 64
		const encoder = new TextEncoder()
		const strBytes = encoder.encode(str)

		let k = new Uint8Array(blockSize)
		if (keyBytes.length > blockSize) {
			const h = this._md5(keyBytes)
			k.set(h, 0)
		} else {
			k.set(keyBytes, 0)
		}

		const iPad = new Uint8Array(blockSize)
		const oPad = new Uint8Array(blockSize)
		for (let i = 0; i < blockSize; i++) {
			iPad[i] = k[i] ^ 0x36
			oPad[i] = k[i] ^ 0x5C
		}

		const inner = new Uint8Array(blockSize + strBytes.length)
		inner.set(iPad, 0)
		inner.set(strBytes, blockSize)
		const innerHash = this._md5(inner)

		const outer = new Uint8Array(blockSize + 16)
		outer.set(oPad, 0)
		outer.set(innerHash, blockSize)
		return this._base64Encode(this._md5(outer))
	}

	_md5(bytes) {
		function R(n, c) { return (n << c) | (n >>> (32 - c)) }
		function A(x, y) {
			const l = (x & 0xFFFF) + (y & 0xFFFF)
			return (((x >>> 16) + (y >>> 16) + (l >>> 16)) << 16) | (l & 0xFFFF)
		}

		const msg = new Uint8Array(bytes.length + 72)
		msg.set(bytes, 0)
		msg[bytes.length] = 0x80
		const bitLen = bytes.length * 8
		const padLen = ((bytes.length + 8) >>> 6 << 6) + 56 - bytes.length - 1
		const dv = new DataView(msg.buffer)
		dv.setUint32(bytes.length + padLen + 1, bitLen & 0xFFFFFFFF, true)
		dv.setUint32(bytes.length + padLen + 5, Math.floor(bitLen / 0x100000000), true)

		let a = 0x67452301, b = 0xEFCDAB89, c = 0x98BADCFE, d = 0x10325476
		const S = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21]
		const T = Array.from({ length: 64 }, (_, i) => Math.floor(0x100000000 * Math.abs(Math.sin(i + 1))))

		for (let o = 0; o < msg.length; o += 64) {
			const X = new Uint32Array(16)
			for (let i = 0; i < 16; i++) {
				X[i] = msg[o + i * 4] | (msg[o + i * 4 + 1] << 8) | (msg[o + i * 4 + 2] << 16) | (msg[o + i * 4 + 3] << 24)
			}
			let aa = a, bb = b, cc = c, dd = d
			for (let i = 0; i < 64; i++) {
				let f, g
				if (i < 16) { f = (b & c) | (~b & d); g = i }
				else if (i < 32) { f = (d & b) | (~d & c); g = (5 * i + 1) % 16 }
				else if (i < 48) { f = b ^ c ^ d; g = (3 * i + 5) % 16 }
				else { f = c ^ (b | ~d); g = (7 * i) % 16 }
				const tmp = d
				d = c; c = b
				b = A(b, R(A(a, A(f, A(X[g], T[i]))), S[(i >>> 4) * 4 + (i % 4)]))
				a = tmp
			}
			a = A(a, aa); b = A(b, bb); c = A(c, cc); d = A(d, dd)
		}

		const out = new Uint8Array(16)
		const wr = (v, o) => { out[o] = v & 0xFF; out[o + 1] = (v >>> 8) & 0xFF; out[o + 2] = (v >>> 16) & 0xFF; out[o + 3] = (v >>> 24) & 0xFF }
		wr(a, 0); wr(b, 4); wr(c, 8); wr(d, 12)
		return out
	}

	_base64Encode(bytes) {
		const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
		let result = ''
		for (let i = 0; i < bytes.length; i += 3) {
			const b1 = bytes[i]
			const b2 = i + 1 < bytes.length ? bytes[i + 1] : 0
			const b3 = i + 2 < bytes.length ? bytes[i + 2] : 0
			result += chars[b1 >>> 2]
			result += chars[((b1 & 3) << 4) | (b2 >>> 4)]
			result += i + 1 < bytes.length ? chars[((b2 & 15) << 2) | (b3 >>> 6)] : '='
			result += i + 2 < bytes.length ? chars[b3 & 63] : '='
		}
		return result
	}

	// ---- 重连与心跳 ----

	_scheduleReconnect() {
		if (this._reconnectIdx >= 99) return
		const idx = Math.min(this._reconnectIdx++, RECONNECT_DELAYS.length - 1)
		const delay = RECONNECT_DELAYS[idx]
		console.log('[MQTT] ' + delay / 1000 + 's 后重连... (第 ' + this._reconnectIdx + ' 次)')
		this._reconnectTimer = setTimeout(() => this._doConnect(), delay)
	}

	_startPing() {
		this._clearPing()
		this._pingTimer = setInterval(() => {
			if (this._socketTask && this._connected) {
				const pkt = buildPingReqPacket()
				this._socketTask.send({ data: pkt.buffer, fail: () => {} })
			}
		}, KEEPALIVE)
	}

	_clearTimers() {
		this._clearPing()
		if (this._reconnectTimer) {
			clearTimeout(this._reconnectTimer)
			this._reconnectTimer = null
		}
	}

	_clearPing() {
		if (this._pingTimer) {
			clearInterval(this._pingTimer)
			this._pingTimer = null
		}
	}
}

export const mqttClient = new MqttClient()
