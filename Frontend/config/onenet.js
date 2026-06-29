/**
 * OneNET Studio 统一配置文件
 */

const ONENET_CONFIG = {
	// ---- 设备凭证 ----
	productId: 'OAgTJW6fph',
	deviceName: 'device_01',
	deviceSecret: 'bFY1YWlrdmJ4eDB4c3o2c2U1MnpuSUNKUG03dVZuZno=',

	// ---- API 认证 ----
	accessKey: 'oR2pXSsfacONMQGjZ3+TtWN79S+npUepxSklYeHBK5s=',
	userId: '514400',

	// ---- 连接地址 ----
	baseUrl: 'https://iot-api.heclouds.com',
	mqttBroker: 'mqtt.heclouds.com',
	mqttPort: 6002,
	wsPort: 8083,

	// ---- 协议版本 ----
	mqttVersion: '2018-10-31',
	apiVersion: '2020-05-29',
}

function loadConfig() {
	try {
		const saved = uni.getStorageSync('onenet_config')
		if (saved && saved.productId === ONENET_CONFIG.productId) {
			// 仅产品 ID 匹配时才合并（防止旧产品凭证覆盖新配置）
			for (const key of Object.keys(saved)) {
				if (saved[key] != null && saved[key] !== '') {
					ONENET_CONFIG[key] = saved[key]
				}
			}
		} else if (saved && saved.productId !== ONENET_CONFIG.productId) {
			// 产品已更换，清除过期配置
			uni.removeStorageSync('onenet_config')
			uni.removeStorageSync('fridgeai_foods')
			console.log('[Config] Cleared stale config/foods from old product:', saved.productId)
		}
	} catch (_) {}
}

function saveConfig() {
	try {
		uni.setStorageSync('onenet_config', ONENET_CONFIG)
	} catch (_) {}
}

loadConfig()

function getConfig() { return { ...ONENET_CONFIG } }

export { ONENET_CONFIG, loadConfig, saveConfig, getConfig }
