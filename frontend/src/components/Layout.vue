<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import { roleLabel } from '@/utils/status'
import type { Notification } from '@/types'

const authStore = useAuthStore()
const notificationStore = useNotificationStore()
const route = useRoute()
const router = useRouter()

// 当前激活的菜单
const activeMenu = computed(() => route.path)

// 菜单项：根据角色计算
interface MenuItem {
  index: string
  title: string
  icon: string
  visible: boolean
}

const menuItems = computed<MenuItem[]>(() => [
  { index: '/home', title: '首页', icon: 'HomeFilled', visible: true },
  { index: '/projects', title: '项目管理', icon: 'Folder', visible: true },
  { index: '/users', title: '用户管理', icon: 'User', visible: authStore.isAdmin },
  { index: '/organizations', title: '组织管理', icon: 'OfficeBuilding', visible: authStore.isAdmin },
  { index: '/llm-config', title: 'LLM 配置', icon: 'Cpu', visible: authStore.isSuperAdmin },
  { index: '/audit', title: '审计日志', icon: 'Document', visible: authStore.isAdmin },
  { index: '/profile', title: '个人信息', icon: 'UserFilled', visible: true },
])

const visibleMenus = computed(() => menuItems.value.filter((m) => m.visible))

// 通知
const notifications = computed<Notification[]>(() => notificationStore.notifications)
const unreadCount = computed(() => notificationStore.unreadCount)

async function loadNotifications() {
  try {
    await notificationStore.fetchNotifications({ page: 1, page_size: 10 })
  } catch {
    // ignore
  }
}

async function handleNotificationVisible(visible: boolean) {
  if (visible) {
    await loadNotifications()
  }
}

async function handleNotificationClick(n: Notification) {
  if (!n.is_read) {
    await notificationStore.markNotificationRead(n.id)
  }
  if (n.link_url) {
    router.push(n.link_url)
  }
}

function handleMenuSelect(index: string) {
  router.push(index)
}

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    authStore.logout()
    ElMessage.success('已退出登录')
    router.push('/login')
  } catch {
    // 取消
  }
}

onMounted(async () => {
  if (!authStore.user) {
    await authStore.fetchCurrentUser()
  }
  await notificationStore.fetchUnreadCount()
})
</script>

<template>
  <el-container class="layout-container">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="layout-aside">
      <div class="logo">
        <el-icon class="logo-icon"><Cpu /></el-icon>
        <span class="logo-text">BMS SOX</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        class="layout-menu"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
        @select="handleMenuSelect"
      >
        <el-menu-item v-for="item in visibleMenus" :key="item.index" :index="item.index">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="main-container">
      <!-- 顶栏 -->
      <el-header class="layout-header">
        <div class="header-left">
          <span class="header-title">BMS SOX 算法软件交付管理系统</span>
        </div>
        <div class="header-right">
          <!-- 通知 -->
          <el-dropdown trigger="click" @visible-change="handleNotificationVisible">
            <el-badge :value="unreadCount" :hidden="unreadCount === 0" :max="99">
              <el-icon class="header-icon"><Bell /></el-icon>
            </el-badge>
            <template #dropdown>
              <el-dropdown-menu class="notification-dropdown">
                <el-dropdown-item v-if="notifications.length === 0" disabled>
                  暂无通知
                </el-dropdown-item>
                <el-dropdown-item
                  v-for="n in notifications"
                  :key="n.id"
                  @click="handleNotificationClick(n)"
                >
                  <div class="notification-item">
                    <div class="notification-title">
                      <el-badge is-dot :hidden="n.is_read" type="danger">
                        {{ n.title }}
                      </el-badge>
                    </div>
                    <div class="notification-content">{{ n.content }}</div>
                  </div>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <!-- 用户信息 -->
          <el-dropdown trigger="click">
            <div class="user-info">
              <el-icon><UserFilled /></el-icon>
              <span class="user-name">{{ authStore.user?.full_name || authStore.user?.username || '用户' }}</span>
              <el-tag size="small" type="info" effect="plain">
                {{ roleLabel(authStore.user?.system_role || 'guest') }}
              </el-tag>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="router.push('/profile')">个人信息</el-dropdown-item>
                <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-button type="danger" plain size="small" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>

      <!-- 内容区域 -->
      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout-container {
  height: 100vh;
}

.layout-aside {
  background-color: #304156;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 1px;
  background-color: #2b3a4d;
}

.logo-icon {
  margin-right: 8px;
  font-size: 24px;
}

.layout-menu {
  border-right: none;
}

.layout-menu .el-menu-item {
  border-left: 3px solid transparent;
}

.layout-menu .el-menu-item.is-active {
  border-left-color: #409eff;
  background-color: #263445 !important;
}

.main-container {
  height: 100vh;
}

.layout-header {
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-icon {
  font-size: 20px;
  cursor: pointer;
  color: #606266;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #303133;
}

.user-name {
  font-size: 14px;
}

.layout-main {
  background-color: #f0f2f5;
  padding: 0;
  overflow-y: auto;
}

.notification-dropdown {
  width: 320px;
  max-height: 400px;
  overflow-y: auto;
}

.notification-item {
  padding: 4px 0;
  width: 280px;
}

.notification-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.notification-content {
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
