<script setup lang="ts">
import { computed } from 'vue'

interface AppUser {
  id: string
  name: string
  email: string
}

interface AppGroupSummary {
  id: string
  name: string
}

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

const displayName = computed(() => currentUser.value?.name || 'Collab AI 用户')

const groupName = computed(() => currentGroup.value?.name || '请先加入小组')
</script>

<template>
  <div class="app-home">
    <div class="app-home-stack">
      <div class="app-home-card">
        <p class="app-home-kicker">欢迎回来，{{ displayName }}</p>
        <div class="app-home-group-panel">
          <span class="app-home-group-label">当前小组</span>
          <strong class="app-home-group-value">{{ groupName }}</strong>
        </div>
        <p class="app-home-desc">
          加入小组后，选择成员新建并发起会话，其他成员进入同一会话即可。
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-home {
  display: flex;
  justify-content: center;
}

.app-home-stack {
  width: 100%;
  max-width: var(--app-content-width-narrow);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.app-home-card {
  width: 100%;
  padding: 16px;
  border-radius: var(--app-radius-card);
  background: var(--app-bg-elevated);
  box-shadow: var(--app-shadow-soft);
  border: 1px solid var(--app-border);
}

.app-home-kicker {
  margin: 0 0 12px;
  font-size: var(--app-font-size-body);
  font-weight: 600;
  color: var(--app-text-secondary);
}

.app-home-group-panel {
  margin: 0 0 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.app-home-group-label {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.app-home-group-value {
  display: block;
  font-size: 28px;
  line-height: 1.15;
  font-weight: 800;
  color: var(--app-text-primary);
  overflow-wrap: anywhere;
}

.app-home-desc {
  margin: 0;
  font-size: var(--app-font-size-body);
  line-height: 1.6;
  color: var(--app-text-secondary);
}
</style>
