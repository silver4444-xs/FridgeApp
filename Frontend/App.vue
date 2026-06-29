<script>
import { connectBackendWs, stopCloudSync } from '@/utils/cloudSync.js'

export default {
	onLaunch() {
		console.log('[FridgeAI] App Launch')
		connectBackendWs()
	},
	onShow() {
		console.log('[FridgeAI] App Show')
		connectBackendWs()
	},
	onHide() {
		console.log('[FridgeAI] App Hide')
		stopCloudSync()
	},
}
</script>

<style>
:root {
  --bg-deep: #06090f;
  --bg-panel: #0d1117;
  --bg-card: rgba(22, 27, 40, 0.72);
  --bg-card-hover: rgba(30, 37, 55, 0.82);
  --border-card: rgba(255, 255, 255, 0.06);
  --border-glow: rgba(0, 212, 255, 0.18);
  --text-primary: #e6edf3;
  --text-secondary: #8b949e;
  --text-muted: #484f58;
  --accent-cyan: #00d4ff;
  --accent-purple: #7c3aed;
  --accent-green: #00e676;
  --accent-orange: #f59e0b;
  --accent-red: #ef4444;
  --accent-pink: #ec4899;
  --glass-blur: blur(20px);
  --radius-sm: 10px;
  --radius-md: 16px;
  --radius-lg: 24px;
  --radius-xl: 32px;
  --shadow-card: 0 4px 24px rgba(0,0,0,0.4), 0 0 1px rgba(255,255,255,0.06);
  --shadow-glow: 0 0 30px rgba(0, 212, 255, 0.08);
  --transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html, body, uni-app, uni-page, uni-page-body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
}

page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-deep);
  color: var(--text-primary);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  -webkit-font-smoothing: antialiased;
  user-select: none;
}

input, button, textarea { outline: none; border: none; }

uni-page-head { background-color: var(--bg-deep) !important; }

@font-face {
  font-family: 'Material Icons';
  font-style: normal;
  font-weight: 400;
  src: url('/static/fonts/material-icons.ttf') format('truetype');
}

.material-icons {
  font-family: 'Material Icons';
  font-weight: normal;
  font-style: normal;
  font-size: 24px;
  display: inline-block;
  line-height: 1;
  text-transform: none;
  letter-spacing: normal;
  word-wrap: normal;
  white-space: nowrap;
  direction: ltr;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  -moz-osx-font-smoothing: grayscale;
  font-feature-settings: 'liga';
}

@media (min-width: 701px) {
  page {
    max-width: 430px;
    margin: 0 auto;
    box-shadow: 0 0 0 3px #1a1a2e, 0 0 0 6px #0d0d16, 0 0 0 8px #1a1a2e, 0 20px 60px rgba(0,0,0,0.7);
    border-radius: 44px;
    overflow: hidden;
  }
}
</style>
