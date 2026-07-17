/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

interface ImportMetaEnv {
  /** 应用完整名称 (浏览器标签 / 页面标题), 由 deploy.sh 通过 VITE_APP_TITLE 注入 */
  readonly VITE_APP_TITLE?: string
  /** 应用简短名称 (侧边栏 logo / 邮件前缀), 由 deploy.sh 通过 VITE_APP_SHORT_NAME 注入 */
  readonly VITE_APP_SHORT_NAME?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
