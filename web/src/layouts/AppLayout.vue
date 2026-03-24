<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'

const router = useRouter()
const route = useRoute()

interface AppUser {
  id: string
  name: string
  email: string
  password_needs_reset?: boolean
}

interface AppGroupSummary {
  id: string
  name: string
}

const tabs = computed(() => [
  { path: '/app', label: '首页', icon: '🏠' },
  { path: '/app/groups', label: '群组', icon: '👥' },
  { path: '/app/sessions', label: '会话', icon: '💬' },
  { path: '/app/voice-profile', label: '声纹', icon: '🎙️' },
])

const active = computed(() => (route.path.startsWith('/app') ? route.path : '/app'))

const isLoggedIn = computed(() => {
  if (typeof window === 'undefined') return false
  return !!window.localStorage.getItem('app_access_token')
})

const currentUser = computed<AppUser | null>(() => {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem('app_user')
  if (!raw) return null
  try {
    return JSON.parse(raw) as AppUser
  } catch {
    return null
  }
})

const currentGroup = computed<AppGroupSummary | null>(() => {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem('app_current_group')
  if (!raw) return null
  try {
    return JSON.parse(raw) as AppGroupSummary
  } catch {
    return null
  }
})

function goAuth() {
  router.push('/app/login')
}

function logout() {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('app_access_token')
    window.localStorage.removeItem('app_user')
    window.localStorage.removeItem('app_current_group')
  }
  router.push('/app/login')
}
</script>

<template>
  <div class="app-layout">
    <!-- 顶部 Header：只保留 Logo + 用户信息 + 退出 -->
    <header class="app-header">
      <div class="app-logo">Collab AI</div>
      <div class="app-header-right">
        <span v-if="isLoggedIn && currentUser" class="app-user-name">
          {{ currentUser.name || currentUser.email }}
        </span>
        <span v-if="isLoggedIn && currentGroup" class="app-current-group">
          {{ currentGroup.name }}
        </span>
        <button
          v-if="!isLoggedIn"
          class="app-auth-btn"
          type="button"
          @click="goAuth"
        >
          登录
        </button>
        <button
          v-else
          class="app-auth-btn app-auth-btn--logout"
          type="button"
          @click="logout"
        >
          退出
        </button>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="app-main">
      <RouterView />
    </main>

    <!-- 底部 Tab Bar -->
    <nav class="app-tabbar">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.path"
        :to="tab.path"
        class="app-tab-item"
        :class="{ 'app-tab-item--active': active === tab.path }"
      >
        <span class="app-tab-icon">{{ tab.icon }}</span>
        <span class="app-tab-label">{{ tab.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f9fafb;
}

/* ── Header ── */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.96);
  border-bottom: 1px solid rgba(229, 231, 235, 0.7);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  position: sticky;
  top: 0;
  z-index: 100;
}

.app-logo {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
  letter-spacing: 0.02em;
}

.app-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-user-name {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-current-group {
  font-size: 12px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 2px 8px;
  border-radius: 999px;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-auth-btn {
  border-radius: 999px;
  border: 1px solid #2563eb;
  padding: 6px 14px;
  font-size: 13px;
  background: #2563eb;
  color: #ffffff;
  cursor: pointer;
  transition: background-color 0.18s ease;
}

.app-auth-btn--logout {
  background: transparent;
  color: #6b7280;
  border-color: #d1d5db;
}

.app-auth-btn--logout:hover {
  background: #f3f4f6;
}

/* ── 主内容区 ── */
.app-main {
  flex: 1;
  padding: 16px 16px 80px; /* 底部留出 tab bar 高度 */
  overflow-y: auto;
}

/* ── 底部 Tab Bar ── */
.app-tabbar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px;
  display: flex;
  align-items: stretch;
  background: rgba(255, 255, 255, 0.97);
  border-top: 1px solid rgba(229, 231, 235, 0.8);
  box-shadow: 0 -2px 12px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  z-index: 200;
  /* 兼容 iPhone 底部安全区 */
  padding-bottom: env(safe-area-inset-bottom);
}

.app-tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  text-decoration: none;
  color: #9ca3af;
  transition: color 0.18s ease;
}

.app-tab-item--active {
  color: #2563eb;
}

.app-tab-icon {
  font-size: 20px;
  line-height: 1;
}

.app-tab-label {
  font-size: 11px;
  font-weight: 500;
}
</style>
