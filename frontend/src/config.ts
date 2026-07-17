/**
 * 应用全局配置
 *
 * 标题等可在部署时通过环境变量覆盖:
 *   - VITE_APP_TITLE       完整应用名称 (浏览器标签 / 登录页 / 顶栏)
 *   - VITE_APP_SHORT_NAME  简短名称 (侧边栏 logo)
 *
 * 部署脚本 (deploy.sh) 会在 `npm run build` 前导出这两个变量,
 * Vite 在构建期把值静态内联到产物中。未设置时使用默认值。
 */

/** 完整应用名称 (用于浏览器标题、登录页大标题、顶栏标题) */
export const APP_TITLE: string = import.meta.env.VITE_APP_TITLE || '项目开发测试管理系统'

/** 简短名称 (用于侧边栏 logo、邮件主题前缀) */
export const APP_SHORT_NAME: string = import.meta.env.VITE_APP_SHORT_NAME || '项目开发测试'
