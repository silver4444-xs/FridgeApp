import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig({
	plugins: [uni()],
	server: {
		proxy: {
			'/api/onenet': {
				target: 'https://iot-api.heclouds.com',
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/api\/onenet/, ''),
				secure: false,
			},
		},
	},
})
