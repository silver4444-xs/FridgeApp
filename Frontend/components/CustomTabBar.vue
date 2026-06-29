<template>
	<view class="bottom-nav">
		<view
			v-for="tab in tabs"
			:key="tab.path"
			class="nav-item"
			:class="{ active: currentPath === tab.path }"
			@click="switchTab(tab.path)"
		>
			<text class="material-icons">{{ tab.icon }}</text>
			<text class="nav-label">{{ tab.text }}</text>
		</view>
	</view>
</template>

<script>
export default {
	name: 'CustomTabBar',
	props: {
		currentPath: { type: String, default: '' },
	},
	data() {
		return {
			tabs: [
				{ path: '/pages/home/home', icon: 'kitchen', text: '冰箱' },
				{ path: '/pages/recipes/recipes', icon: 'menu_book', text: '食谱' },
				{ path: '/pages/add/add', icon: 'add_circle', text: '添加' },
				{ path: '/pages/settings/settings', icon: 'settings', text: '设置' },
			],
		}
	},
	methods: {
		switchTab(path) {
			if (this.currentPath === path) return
			uni.switchTab({ url: path })
		},
	},
}
</script>

<style scoped>
.bottom-nav {
	height: 72px;
	padding: 6px 0 10px;
	display: flex;
	align-items: center;
	flex-shrink: 0;
	background: rgba(13, 17, 23, 0.92);
	backdrop-filter: blur(24px);
	-webkit-backdrop-filter: blur(24px);
	border-top: 1px solid var(--border-card);
	z-index: 90;
}

.nav-item {
	flex: 1;
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	gap: 3px;
	cursor: pointer;
	position: relative;
	transition: var(--transition);
}

.nav-item .material-icons {
	font-size: 22px;
	color: var(--text-muted);
	transition: var(--transition);
}

.nav-label {
	font-size: 10px;
	font-weight: 600;
	color: var(--text-muted);
	transition: var(--transition);
}

.nav-item.active .material-icons {
	color: var(--accent-cyan);
}

.nav-item.active .nav-label {
	color: var(--accent-cyan);
}

.nav-item.active::before {
	content: '';
	position: absolute;
	top: -6px;
	width: 20px;
	height: 2px;
	border-radius: 1px;
	background: var(--accent-cyan);
}

</style>
