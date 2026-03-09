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
  <div class="app-groups">
    <div class="app-groups-header">
      <h2 class="app-groups-title">我的群组</h2>
      <div class="app-groups-meta">
        <span class="app-groups-user" v-if="currentUser">
          {{ currentUser.name || currentUser.email }}（{{ currentUser.email }}）
        </span>
        <span class="app-groups-group">
          <span class="app-groups-group-label">当前群组：</span>
          <span class="app-groups-group-value">
            {{ currentGroup?.name || '未选择' }}
          </span>
        </span>
      </div>
    </div>
    <p class="app-groups-desc">
      后续会在这里对接 /api/groups 相关接口，展示和管理你参与的协作群组。
      选择的群组会影响在「我的会话」等页面中看到的上下文。
    </p>
  </div>
</template>

<style scoped>
.app-groups {
  max-width: 880px;
}

.app-groups-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.app-groups-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.app-groups-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  font-size: 12px;
}

.app-groups-user {
  color: #4b5563;
}

.app-groups-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #374151;
}

.app-groups-group-label {
  color: #6b7280;
}

.app-groups-group-value {
  font-weight: 500;
}

.app-groups-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
}
</style>

