/**
 * 应用入口
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import './style.css'

const app = createApp(App)

// 注册所有 Element Plus 图标为全局组件
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

// 全局错误处理器：捕获 Vue 运行时异常，避免未处理的 Promise 拒绝
// 注意：此处不调用可能抛错的 ElNotification，避免递归
app.config.errorHandler = (err, instance, info) => {
  console.error('Vue全局异常:', err, info)
}

app.mount('#app')
