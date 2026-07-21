/**
 * 路由配置
 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Layout from '@/components/Layout.vue'
import { useSiteInfoStore } from '@/stores/siteInfo'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: () => import('@/views/ForgotPassword.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/reset-password',
    name: 'ResetPassword',
    component: () => import('@/views/ResetPassword.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    component: Layout,
    redirect: '/home',
    children: [
      {
        path: 'home',
        name: 'Home',
        component: () => import('@/views/Home.vue'),
        meta: { title: '首页', requiresAuth: true },
      },
      {
        path: 'projects',
        name: 'ProjectList',
        component: () => import('@/views/ProjectList.vue'),
        meta: { title: '项目管理', requiresAuth: true },
      },
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import('@/views/ProjectDetail.vue'),
        meta: { title: '项目详情', requiresAuth: true },
      },
      {
        path: 'releases/:id',
        name: 'ReleaseDetail',
        component: () => import('@/views/ReleaseDetail.vue'),
        meta: { title: '释放详情', requiresAuth: true },
      },
      {
        path: 'users',
        name: 'UserManagement',
        component: () => import('@/views/UserManagement.vue'),
        meta: { title: '用户管理', requiresAuth: true, roles: ['admin', 'super_admin'] },
      },
      {
        path: 'organizations',
        name: 'OrgManagement',
        component: () => import('@/views/OrgManagement.vue'),
        meta: { title: '组织管理', requiresAuth: true, roles: ['admin', 'super_admin'] },
      },
      {
        path: 'llm-config',
        name: 'LlmConfig',
        component: () => import('@/views/LlmConfig.vue'),
        meta: { title: 'LLM 配置', requiresAuth: true, roles: ['super_admin'] },
      },
      {
        path: 'system-settings',
        name: 'SystemSettings',
        component: () => import('@/views/SystemSettings.vue'),
        meta: { title: '系统设置', requiresAuth: true, roles: ['super_admin'] },
      },
      {
        path: 'audit',
        name: 'AuditLog',
        component: () => import('@/views/AuditLog.vue'),
        meta: { title: '审计日志', requiresAuth: true, roles: ['admin', 'super_admin'] },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/Profile.vue'),
        meta: { title: '个人信息', requiresAuth: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    redirect: '/home',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局前置守卫
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  // 设置页面标题（使用动态站点名称）
  const siteInfoStore = useSiteInfoStore()
  const siteName = siteInfoStore.siteName
  if (to.meta.title) {
    document.title = `${to.meta.title} - ${siteName}`
  } else {
    document.title = siteName
  }

  const requiresAuth = to.meta.requiresAuth !== false

  if (!requiresAuth) {
    // 已登录用户访问登录页则跳转首页
    if (to.name === 'Login' && authStore.isLoggedIn) {
      next({ path: '/home' })
      return
    }
    next()
    return
  }

  // 需要登录
  if (!authStore.isLoggedIn) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  // P2-6: 已有 token 但 user 为空(典型场景:刷新页面后 Pinia 状态丢失),
  // 重新拉取当前用户信息;若拉取失败(token 失效)则登出并跳登录
  if (authStore.isLoggedIn && !authStore.user) {
    try {
      await authStore.fetchCurrentUser()
    } catch {
      // fetchCurrentUser 内部已 logout,这里仅需跳登录
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }
    if (!authStore.isLoggedIn) {
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }
  }

  // 角色权限校验
  const requiredRoles = to.meta.roles as string[] | undefined
  if (requiredRoles && requiredRoles.length > 0) {
    const role = authStore.user?.system_role
    if (!role || !requiredRoles.includes(role)) {
      next({ path: '/home' })
      return
    }
  }

  next()
})

export default router
