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
  condition?: string
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

const CONDITION_LABELS: Record<string, string> = {
  no_assistance: '无辅助',
  glasses: '智能眼镜',
  app_notification: 'APP 通知',
}

const displayName = computed(() => currentUser.value?.name || 'Collab AI 用户')
const groupName = computed(() => currentGroup.value?.name || '请先加入小组')
const conditionLabel = computed(() => {
  const c = currentGroup.value?.condition
  return c ? (CONDITION_LABELS[c] ?? c) : null
})
</script>

<template>
  <div class="app-home">
    <div class="app-home-stack">

      <!-- 欢迎横幅 -->
      <div class="app-home-banner">
        <p class="app-home-banner-greeting">你好，{{ displayName }} 👋</p>
        <div class="app-home-banner-group">
          <span class="app-home-banner-group-label">当前小组</span>
          <strong class="app-home-banner-group-value">{{ groupName }}</strong>
        </div>
        <div class="app-home-banner-badges">
          <div class="app-home-banner-badge">AI 辅助小组讨论 · 约 60 分钟</div>
          <div v-if="conditionLabel" class="app-home-banner-badge app-home-banner-badge-condition">
            实验条件：{{ conditionLabel }}
          </div>
        </div>
      </div>

      <!-- 实验流程 -->
      <div class="app-home-card">
        <p class="app-home-section-title">实验流程</p>
        <div class="app-home-steps">

          <div class="app-home-step">
            <div class="step-left">
              <span class="step-dot">🧊</span>
              <span class="step-line" />
            </div>
            <div class="app-home-step-body">
              <span class="app-home-step-name">破冰环节</span>
              <span class="app-home-step-desc">自我介绍 + 故事接龙</span>
            </div>
          </div>

          <div class="app-home-step">
            <div class="step-left">
              <span class="step-dot">✏️</span>
              <span class="step-line" />
            </div>
            <div class="app-home-step-body">
              <span class="app-home-step-name">个人任务 <em>5 分钟</em></span>
              <span class="app-home-step-desc">在白纸上独立完成排序，不与他人交流</span>
            </div>
          </div>

          <div class="app-home-step">
            <div class="step-left">
              <span class="step-dot">💬</span>
              <span class="step-line" />
            </div>
            <div class="app-home-step-body">
              <span class="app-home-step-name">小组讨论 <em>30 分钟</em></span>
              <span class="app-home-step-desc">点底部「会话」进入，结束前写下共同答案</span>
            </div>
          </div>

          <div class="app-home-step app-home-step-last">
            <div class="step-left">
              <span class="step-dot">📝</span>
            </div>
            <div class="app-home-step-body">
              <span class="app-home-step-name">量表填写</span>
              <span class="app-home-step-desc">讨论结束后点底部「量表」完成 SRCC 和 PCS</span>
            </div>
          </div>

        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.app-home {
  display: flex;
  justify-content: center;
  padding-bottom: 16px;
}

.app-home-stack {
  width: 100%;
  max-width: var(--app-content-width-narrow);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ── 欢迎横幅 ── */
.app-home-banner {
  width: 100%;
  padding: 20px 20px 18px;
  border-radius: var(--app-radius-card);
  background: linear-gradient(135deg, #1d4ed8 0%, #4f46e5 100%);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.3);
}

.app-home-banner-greeting {
  margin: 0 0 14px;
  font-size: 16px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.8);
}

.app-home-banner-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 16px;
}

.app-home-banner-group-label {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
}

.app-home-banner-group-value {
  font-size: 32px;
  font-weight: 800;
  color: #fff;
  line-height: 1.15;
}

.app-home-banner-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.app-home-banner-badge {
  display: inline-block;
  background: rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.9);
  border-radius: 100px;
  padding: 5px 14px;
  font-size: 13px;
}

.app-home-banner-badge-condition {
  background: rgba(255, 255, 255, 0.25);
  font-weight: 600;
}

/* ── 流程卡片 ── */
.app-home-card {
  width: 100%;
  padding: 18px 16px;
  border-radius: var(--app-radius-card);
  background: var(--app-bg-elevated);
  box-shadow: var(--app-shadow-soft);
  border: 1px solid var(--app-border);
}

.app-home-section-title {
  margin: 0 0 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

/* ── 时间轴步骤 ── */
.app-home-steps {
  display: flex;
  flex-direction: column;
}

.app-home-step {
  display: flex;
  gap: 14px;
}

.step-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}

.step-dot {
  font-size: 20px;
  line-height: 1;
}

.step-line {
  width: 2px;
  flex: 1;
  min-height: 16px;
  background: var(--app-border);
  margin: 4px 0;
}

.app-home-step-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-bottom: 18px;
}

.app-home-step-last .app-home-step-body {
  padding-bottom: 0;
}

.app-home-step-name {
  font-size: var(--app-font-size-body);
  font-weight: 600;
  color: var(--app-text-primary);
  line-height: 1.3;
}

.app-home-step-name em {
  font-style: normal;
  font-weight: 400;
  font-size: 14px;
  color: var(--app-text-secondary);
  margin-left: 4px;
}

.app-home-step-desc {
  font-size: 14px;
  color: var(--app-text-secondary);
  line-height: 1.5;
}
</style>
