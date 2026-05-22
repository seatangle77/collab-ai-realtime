<script setup lang="ts">
import { computed } from 'vue'
import { User, ChatLineRound, Microphone } from '@element-plus/icons-vue'

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
    <div class="app-home-stack">
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
            {{ currentGroup?.name || '未加入群组，请先新建或加入群组' }}
          </span>
        </p>
        <p class="app-home-desc">
          这里将是普通用户使用协作与会话功能的入口。你可以在「我的群组」中创建、加入或管理协作群组，
          在「我的会话」中查看与 Collab AI 的历史会话，在「我的声纹」中管理声纹样本并生成声纹。
        </p>
      </div>

      <div class="app-home-quick-grid">
        <RouterLink class="app-home-quick" to="/app/groups">
          <div class="app-home-quick-icon app-home-quick-icon--groups">
            <User class="app-home-quick-svg" aria-hidden="true" />
          </div>
          <div class="app-home-quick-text">
            <p class="app-home-quick-name">我的群组</p>
            <p class="app-home-quick-hint">管理协作群组</p>
          </div>
        </RouterLink>

        <RouterLink class="app-home-quick" to="/app/sessions">
          <div class="app-home-quick-icon app-home-quick-icon--sessions">
            <ChatLineRound class="app-home-quick-svg" aria-hidden="true" />
          </div>
          <div class="app-home-quick-text">
            <p class="app-home-quick-name">我的会话</p>
            <p class="app-home-quick-hint">查看历史会话</p>
          </div>
        </RouterLink>

        <RouterLink class="app-home-quick" to="/app/voice-profile">
          <div class="app-home-quick-icon app-home-quick-icon--voice">
            <Microphone class="app-home-quick-svg" aria-hidden="true" />
          </div>
          <div class="app-home-quick-text">
            <p class="app-home-quick-name">我的声纹</p>
            <p class="app-home-quick-hint">管理声纹样本</p>
          </div>
        </RouterLink>
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
  gap: 16px;
}

.app-home-card {
  width: 100%;
  padding: 18px 20px;
  border-radius: var(--app-radius-card);
  background: var(--app-bg-elevated);
  box-shadow: var(--app-shadow-soft);
  border: 1px solid var(--app-border);
}

.app-home-title {
  margin: 0 0 8px;
  font-size: var(--app-font-size-title);
  font-weight: 700;
  color: var(--app-text-primary);
  letter-spacing: -0.02em;
}

.app-home-subtitle {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--app-text-secondary);
}

.app-home-group {
  margin: 0 0 12px;
  font-size: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px;
}

.app-home-group-label {
  color: var(--app-text-secondary);
}

.app-home-group-value {
  font-weight: 500;
  color: var(--app-text-primary);
}

.app-home-desc {
  margin: 0;
  font-size: 14px;
  line-height: 1.65;
  color: var(--app-text-secondary);
}

/* 快捷入口：2 列，第三块自动换行 */
.app-home-quick-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.app-home-quick {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 20px;
  border-radius: var(--app-radius-card);
  background: var(--app-bg-elevated);
  border: 1px solid var(--app-border);
  box-shadow: var(--app-shadow-card);
  text-decoration: none;
  color: inherit;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.app-home-quick:hover {
  border-color: var(--app-primary);
  box-shadow: var(--app-shadow-soft);
  transform: translateY(-2px);
}

.app-home-quick-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.app-home-quick-icon--groups {
  background: #dbeafe;
  color: #2563eb;
}

.app-home-quick-icon--sessions {
  background: #d1fae5;
  color: #059669;
}

.app-home-quick-icon--voice {
  background: #ede9fe;
  color: #7c3aed;
}

.app-home-quick-svg {
  width: 20px;
  height: 20px;
}

.app-home-quick-text {
  min-width: 0;
  text-align: left;
}

.app-home-quick-name {
  margin: 0 0 2px;
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.app-home-quick-hint {
  margin: 0;
  font-size: 12px;
  color: var(--app-text-secondary);
}
</style>
