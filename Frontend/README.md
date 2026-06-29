● 全部完成。以下是最终项目结构和各模块说明。

  ---
  项目结构

  FridgeApp/
  ├── utils/
  │   ├── onenet.js          ← OneNET 云端服务（HTTP API + MQTT token）
  │   └── store.js           ← 集中式数据 Store（响应式，跨页面共享）
  ├── pages/
  │   ├── home/home.vue      ← 🏠 冰箱首页（食材网格 + 分类导航 + 编辑弹窗）
  │   ├── categories/categories.vue ← 📂 分类浏览（按品类横向滚动）
  │   ├── add/add.vue        ← ➕ 添加食材（表单 + 相册上传）
  │   ├── reminders/reminders.vue   ← 🔔 过期提醒（三级紧急度 + 操作建议）
  │   ├── settings/settings.vue     ← ⚙️ 设置（OneNET 连接 + API 配置 + 重置）
  │   └── index/index.vue    ← （旧文件，不再使用）
  ├── static/tab/            ← 9 个 Tab 图标 PNG
  ├── pages.json             ← 页面路由 + TabBar（含 midButton）
  ├── App.vue                ← 全局暗色主题
  ├── uni.scss               ← 暗色主题 CSS 变量
  └── main.js / manifest.json

  数据流架构

  OneNET Cloud (HTTP API)
         │
         ▼
    utils/onenet.js          ← fetchAllFromCloud()
         │                    • getDatastreams() → getDatapoints()
         │                    • 解析 JSON/CSV 格式食材数据
         │                    • 提取传感器数据 (温度/湿度/门状态)
         ▼
    utils/store.js           ← 响应式 Store (Vue reactive)
         │                    • foods[] 食材库存 CRUD
         │                    • deviceStatus 传感器数据
         │                    • 过期天数自动计算
         │                    • 本地存储持久化
         ▼
    5 个页面组件             ← 直接从 store 读取，修改自动刷新 UI

  从 OneNET 获取数据的流程

  1. 配置 API Key：进入「设置」→ 点击「配置 API」→ 填入 apiKey（access_key）和 deviceId
  2. 点击同步：设置页的「立即同步」按钮调用 fetchAllFromCloud()
  3. 数据解析：自动识别三种食材数据格式：
    - JSON：{"name":"苹果","cat":"fruit","qty":3,"unit":"颗"}
    - 前缀匹配：数据流 ID 含 food_ 的自动映射
    - 传感器：含 temp / humidity / door 的归入设备状态
  4. 合并到本地库存：云端数据与本地数据按名称+分类去重合并

  与原型对照

  ┌───────────────────────────────┬───────────────────────────────────┐
  │           原型功能            │             实现文件              │
  ├───────────────────────────────┼───────────────────────────────────┤
  │ 冰箱首页 + 食材网格 + +/-数量 │ pages/home/home.vue               │
  ├───────────────────────────────┼───────────────────────────────────┤
  │ 分类横向滚动 + 统计卡片       │ pages/home/home.vue               │
  ├───────────────────────────────┼───────────────────────────────────┤
  │ 点击食材 → 底部编辑弹窗       │ pages/home/home.vue (modal-sheet) │
  ├───────────────────────────────┼───────────────────────────────────┤
  │ 分类浏览页                    │ pages/categories/categories.vue   │
  ├───────────────────────────────┼───────────────────────────────────┤
  │ 添加食材表单 + 照片上传       │ pages/add/add.vue                 │
  ├───────────────────────────────┼───────────────────────────────────┤
  │ 过期提醒列表 + 三级状态       │ pages/reminders/reminders.vue     │
  ├───────────────────────────────┼───────────────────────────────────┤
  │ OneNET 连接卡片 + API 配置    │ pages/settings/settings.vue       │
  ├───────────────────────────────┼───────────────────────────────────┤
  │ 暗色玻璃态科技风              │ uni.scss + 各页 scoped style      │
  ├───────────────────────────────┼───────────────────────────────────┤
  │ 底部凸起添加按钮              │ pages.json midButton              │
  └───────────────────────────────┴───────────────────────────────────┘

  在 HBuilderX 中直接运行即可看到效果。未配置 apiKey 时自动使用 12 种演示食材（Unsplash 真实照片）。