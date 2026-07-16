/**
 * OneNET Studio 统一配置文件
 *
 * 安全警告: 所有凭证字段在源码中均为空白占位符。
 * 真实凭证必须在部署时从环境变量或后端 API 注入，禁止硬编码到源码中。
 */

const ONENET_CONFIG = {
	// ---- 设备凭证 ----
	/**
	 * 安全警告: 以下凭证为占位符，禁止提交真实值到版本控制。
	 * 部署时通过以下方式之一注入:
	 *   1. 构建时替换 — CI/CD 环境变量在构建阶段替换
	 *   2. 运行时注入 — 从后端 API 端点获取 (推荐)
	 *   3. HBuilderX manifest — 通过 manifest.json 配置注入
	 */
	productId: '', // 部署时注入
	deviceName: 'device_01',
	deviceSecret: '', // 部署时注入

	// ---- API 认证 (部署时注入) ----
	accessKey: '', // 部署时注入
	userId: '', // 部署时注入

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
