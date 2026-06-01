<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed, ref, watch } from 'vue'
import type { Component } from 'vue'
import { HomeFilled, ChatLineRound, Microphone, EditPen } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const isAccountMenuOpen = ref(false)

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

interface TabItem {
  path: string
  label: string
  icon: Component
}

const tabs: TabItem[] = [
  { path: '/app', label: '首页', icon: HomeFilled },
  { path: '/app/sessions', label: '会话', icon: ChatLineRound },
  { path: '/app/voice-profile', label: '声纹', icon: Microphone },
  { path: '/app/survey', label: '量表', icon: EditPen },
]

function isTabActive(tabPath: string): boolean {
  const p = route.path
  if (tabPath === '/app') {
    return p === '/app' || p === '/app/'
  }
  if (tabPath === '/app/groups') {
    return p.startsWith('/app/groups')
  }
  if (tabPath === '/app/sessions') {
    return p.startsWith('/app/sessions')
  }
  if (tabPath === '/app/voice-profile') {
    return p.startsWith('/app/voice-profile')
  }
if (tabPath === '/app/survey') {
    return p.startsWith('/app/survey')
  }
  return false
}

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

const accountInitial = computed(() => {
  const displayName = currentUser.value?.name || currentUser.value?.email || ''
  return displayName.trim().charAt(0).toUpperCase() || '我'
})

watch(
  () => route.fullPath,
  () => {
    isAccountMenuOpen.value = false
  },
)

function goAuth() {
  isAccountMenuOpen.value = false
  router.push('/app/login')
}

function logout() {
  isAccountMenuOpen.value = false
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('app_access_token')
    window.localStorage.removeItem('app_user')
    // 保留当前小组，让再次登录后的选组页默认显示上次选择的小组。
    // window.localStorage.removeItem('app_current_group')
  }
  router.push('/app/login')
}
</script>

<template>
  <div class="app-layout">
    <header class="app-header">
      <div class="app-logo">Collab AI</div>
      <div class="app-header-right">
        <span v-if="isLoggedIn && currentUser" class="app-user-name app-header-desktop-item">
          {{ currentUser.name || currentUser.email }}
        </span>
        <span v-if="isLoggedIn && currentGroup" class="app-current-group app-header-desktop-item">
          {{ currentGroup.name }}
        </span>
        <button
          v-if="!isLoggedIn"
          class="app-auth-btn app-auth-btn--login"
          type="button"
          @click="goAuth"
        >
          登录
        </button>
        <button
          v-else
          class="app-auth-btn app-auth-btn--logout app-header-desktop-item"
          type="button"
          @click="logout"
        >
          退出
        </button>
        <div v-if="isLoggedIn" class="app-account-menu">
          <button
            class="app-account-trigger"
            type="button"
            :aria-expanded="isAccountMenuOpen"
            aria-label="账户菜单"
            @click="isAccountMenuOpen = !isAccountMenuOpen"
          >
            {{ accountInitial }}
          </button>
          <div v-if="isAccountMenuOpen" class="app-account-popover">
            <div class="app-account-name">
              {{ currentUser?.name || currentUser?.email }}
            </div>
            <div v-if="currentGroup" class="app-account-group">
              {{ currentGroup.name }}
            </div>
            <button class="app-account-logout" type="button" @click="logout">
              退出登录
            </button>
          </div>
        </div>
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
        :class="{ 'app-tab-item--active': isTabActive(tab.path) }"
        :aria-label="tab.label"
      >
        <component :is="tab.icon" class="app-tab-icon-svg" aria-hidden="true" />
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
  background: var(--app-bg-page);
}

/* ── Header（约 56px，与 demo h-14 对齐）── */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: calc(56px + env(safe-area-inset-top));
  padding: env(safe-area-inset-top) 16px 0;
  background: rgba(255, 255, 255, 0.8);
  border-bottom: 1px solid var(--app-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--app-shadow-card);
  position: sticky;
  top: 0;
  z-index: 100;
}

.app-logo {
  font-size: 18px;
  font-weight: 700;
  color: var(--app-text-primary);
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.app-header-right {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.app-user-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--app-text-secondary);
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-current-group {
  font-size: 14px;
  font-weight: 500;
  color: var(--app-text-secondary);
  background: var(--app-bg-page);
  border: 1px solid var(--app-border);
  padding: 2px 10px;
  border-radius: 999px;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-auth-btn {
  flex-shrink: 0;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 15px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    color 0.18s ease,
    border-color 0.18s ease;
}

.app-auth-btn--login {
  border: 1px solid var(--app-primary);
  background: var(--app-primary);
  color: #fff;
}

.app-auth-btn--login:hover {
  background: var(--app-primary-hover);
  border-color: var(--app-primary-hover);
}

.app-auth-btn--logout {
  border: 1px solid transparent;
  background: transparent;
  color: var(--app-text-secondary);
}

.app-auth-btn--logout:hover {
  background: var(--app-bg-page);
  color: var(--app-text-primary);
}

.app-account-menu {
  display: none;
  position: relative;
}

.app-account-trigger {
  width: 34px;
  height: 34px;
  border: 1px solid var(--app-border);
  border-radius: 50%;
  background: var(--app-primary);
  color: #fff;
  font: inherit;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
}

.app-account-popover {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  width: min(260px, calc(100vw - 24px));
  padding: 12px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
  z-index: 240;
}

.app-account-name,
.app-account-group {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-account-name {
  color: var(--app-text-primary);
  font-size: 15px;
  font-weight: 700;
}

.app-account-group {
  margin-top: 4px;
  color: var(--app-text-secondary);
  font-size: 13px;
}

.app-account-logout {
  width: 100%;
  min-height: 40px;
  margin-top: 12px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: var(--app-bg-page);
  color: var(--app-text-primary);
  font: inherit;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
}

@media (max-width: 600px) {
  .app-header {
    padding-right: 12px;
    padding-left: 12px;
  }

  .app-logo {
    font-size: 17px;
  }

  .app-header-desktop-item {
    display: none;
  }

  .app-account-menu {
    display: block;
  }
}

/* ── 主内容区 ── */
.app-main {
  flex: 1;
  padding: 12px 12px calc(80px + env(safe-area-inset-bottom));
  overflow-y: auto;
}

/* ── 底部 Tab Bar（约 64px + safe-area）── */
.app-tabbar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  min-height: 68px;
  display: flex;
  align-items: stretch;
  background: rgba(255, 255, 255, 0.96);
  border-top: 1px solid var(--app-border);
  box-shadow: 0 -2px 12px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  z-index: 200;
  padding-bottom: env(safe-area-inset-bottom);
}

.app-tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 7px 2px 6px;
  text-decoration: none;
  color: var(--app-text-muted);
  transition: color 0.18s ease;
}

.app-tab-item--active {
  color: var(--app-primary);
}

.app-tab-icon-svg {
  width: 23px;
  height: 23px;
  flex-shrink: 0;
}

.app-tab-label {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  line-height: 1.15;
  font-weight: 500;
}
</style>
