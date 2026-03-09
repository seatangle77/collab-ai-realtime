<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'

const router = useRouter()
const route = useRoute()

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
  gap: 12px;
  padding: 10px 20px;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
}

.app-logo {
  font-size: 18px;
  font-weight: 600;
}

.app-nav {
  display: flex;
  gap: 8px;
}

.app-nav-item {
  border-radius: 999px;
  border: 1px solid transparent;
  padding: 6px 12px;
  font-size: 14px;
  background: transparent;
  cursor: pointer;
}

.app-nav-item[data-active='true'] {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}

.app-auth {
  display: flex;
  align-items: center;
}

.app-auth-btn {
  border-radius: 999px;
  border: 1px solid #2563eb;
  padding: 6px 12px;
  font-size: 13px;
  background: #2563eb;
  color: #ffffff;
  cursor: pointer;
}

.app-main {
  flex: 1;
  padding: 16px 20px 24px;
}
</style>
