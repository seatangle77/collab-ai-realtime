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
  { path: '/app', label: '首页' },
  { path: '/app/groups', label: '我的群组' },
  { path: '/app/sessions', label: '我的会话' },
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

function go(path: string) {
  if (path !== route.path) {
    router.push(path)
  }
}

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
    <header class="app-header">
      <div class="app-logo">Collab AI</div>
      <nav class="app-nav">
        <button
          v-for="tab in tabs"
          :key="tab.path"
          class="app-nav-item"
          :data-active="active === tab.path"
          type="button"
          @click="go(tab.path)"
        >
          {{ tab.label }}
        </button>
      </nav>
      <div class="app-header-right">
        <div v-if="isLoggedIn && currentUser" class="app-user-info">
          <span class="app-user-name">{{ currentUser.name || currentUser.email }}</span>
          <span class="app-user-email">
            {{ currentUser.email }}
          </span>
          <span class="app-user-separator">·</span>
          <span class="app-user-group-inline">
            <span class="app-user-group-label">当前群组：</span>
            <span class="app-user-group-value">
              {{ currentGroup?.name || '未选择' }}
            </span>
          </span>
        </div>
        <div class="app-auth">
          <button
            v-if="!isLoggedIn"
            class="app-auth-btn"
            type="button"
            @click="goAuth"
          >
            登录 / 注册
          </button>
          <button
            v-else
            class="app-auth-btn"
            type="button"
            @click="logout"
          >
            退出登录
          </button>
        </div>
      </div>
    </header>
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f9fafb;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 10px 32px;
  background: rgba(255, 255, 255, 0.96);
  border-bottom: 1px solid rgba(229, 231, 235, 0.7);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
}

.app-logo {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #111827;
}

.app-nav {
  display: flex;
  gap: 16px;
}

.app-nav-item {
  border-radius: 999px;
  border: 1px solid transparent;
  padding: 8px 16px;
  font-size: 15px;
  background: transparent;
  cursor: pointer;
  color: #4b5563;
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.app-nav-item[data-active='true'] {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.18);
}

.app-nav-item:not([data-active='true']):hover {
  background: #f3f4f6;
  color: #111827;
}

.app-header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.app-user-info {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  font-size: 13px;
  color: #374151;
}

.app-user-name {
  font-weight: 600;
  font-size: 15px;
  color: #111827;
}

.app-user-email {
  font-size: 12px;
  color: #6b7280;
}

.app-user-group-label {
  font-size: 12px;
  color: #6b7280;
}

.app-user-group-value {
  font-weight: 500;
  font-size: 13px;
}

.app-user-separator {
  font-size: 13px;
  color: #d1d5db;
}

.app-user-group-inline {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.app-auth {
  display: flex;
  align-items: center;
}

.app-auth-btn {
  border-radius: 999px;
  border: 1px solid #2563eb;
  padding: 8px 16px;
  font-size: 14px;
  background: #2563eb;
  color: #ffffff;
  cursor: pointer;
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.25);
  transition:
    background-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.1s ease,
    opacity 0.18s ease;
}

.app-auth-btn:hover {
  background: #1d4ed8;
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.3);
  transform: translateY(-1px);
}

.app-auth-btn:active {
  transform: translateY(0);
  box-shadow: 0 8px 16px rgba(37, 99, 235, 0.24);
}

.app-main {
  flex: 1;
  padding: 20px 32px 28px;
}
</style>
