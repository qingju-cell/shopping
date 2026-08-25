import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
// @ts-ignore
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import router from './router'
import { useUserStore } from './stores/user'
import '@/styles/global.css'

const app = createApp(App)

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 使用 Pinia
const pinia = createPinia()
app.use(pinia)

// 使用路由
app.use(router)

// 使用 Element Plus（中文）
app.use(ElementPlus, { locale: zhCn })

// 初始化用户信息（从 localStorage 恢复）
const userStore = useUserStore()
userStore.initUserInfo()

// 挂载应用
app.mount('#app')
