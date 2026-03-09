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
</script>

<template>
  <div class="app-sessions">
    <div class="app-sessions-header">
      <h2 class="app-sessions-title">我的会话</h2>
      <div class="app-sessions-meta">
        <span class="app-sessions-user" v-if="currentUser">
          {{ currentUser.name || currentUser.email }}（{{ currentUser.email }}）
        </span>
        <span class="app-sessions-group">
          <span class="app-sessions-group-label">当前群组：</span>
          <span class="app-sessions-group-value">
            {{ currentGroup?.name || '未选择' }}
          </span>
        </span>
      </div>
    </div>
    <p class="app-sessions-desc">
      后续会在这里对接 /api 下的会话与转写接口，展示你的历史会话记录。
      这里展示的内容会结合当前选择的群组进行过滤或聚合。
    </p>
  </div>
</template>

<style scoped>
.app-sessions {
  max-width: 880px;
}

.app-sessions-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.app-sessions-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.app-sessions-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  font-size: 12px;
}

.app-sessions-user {
  color: #4b5563;
}

.app-sessions-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #374151;
}

.app-sessions-group-label {
  color: #6b7280;
}

.app-sessions-group-value {
  font-weight: 500;
}

.app-sessions-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
}
</style>

