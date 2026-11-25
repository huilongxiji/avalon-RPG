import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import './styles/main.css'

import App from './App.vue'
import router from './router'

window.addEventListener('avalon:unauthorized', () => {
  // 整页跳转同时清空各页缓存和未完成操作。
  if (window.location.pathname !== '/login') {
    window.location.replace(`/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`)
  }
})

createApp(App)
  .use(createPinia())
  .use(router)
  .use(ElementPlus, { locale: zhCn }) // 界面组件全部用中文
  .mount('#app')
