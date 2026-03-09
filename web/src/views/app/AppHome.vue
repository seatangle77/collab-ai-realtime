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
  <div class="app-home">
    <div class="app-home-card">
      <h2 class="app-home-title">
        欢迎回来，{{ currentUser?.name || currentUser?.email || 'Collab AI 用户' }}
      </h2>
      <p v-if="currentUser?.email" class="app-home-subtitle">
        邮箱：{{ currentUser.email }}
      </p>
      <p class="app-home-group">
        <span class="app-home-group-label">当前群组：</span>
        <span class="app-home-group-value">
          {{ currentGroup?.name || '未选择，请前往「我的群组」选择' }}
        </span>
      </p>
      <p class="app-home-desc">
        这里将是普通用户使用协作与会话功能的入口。你可以在「我的群组」中加入或管理协作群组，
        并在「我的会话」中查看与 Collab AI 的历史会话。
      </p>
    </div>
  </div>
</template>

<style scoped>
.app-home {
  display: flex;
  justify-content: center;
}

.app-home-card {
  width: 100%;
  max-width: 720px;
  padding: 20px 22px;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
  border: 1px solid #e5e7eb;
}

.app-home-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.app-home-subtitle {
  margin: 0 0 12px;
  font-size: 13px;
  color: #6b7280;
}

.app-home-group {
  margin: 0 0 12px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.app-home-group-label {
  color: #6b7280;
}

.app-home-group-value {
  font-weight: 500;
  color: #111827;
}

.app-home-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
}
</style>

