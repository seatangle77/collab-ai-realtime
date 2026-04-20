<script setup lang="ts">
import { ref } from 'vue'

export interface InfoGapButton {
  id: string
  keyword: string
  skw_score: number
  analysis_run_id?: string
  window_start?: string
  created_at?: string
  explanation?: string
  viewed?: boolean
}

const props = defineProps<{
  sessionId: string
  buttons: InfoGapButton[]
}>()

const emit = defineEmits<{
  (e: 'clicked', buttonId: string, content: string, keyword: string): void
}>()

const loadingId = ref<string | null>(null)

async function handleClick(btn: InfoGapButton) {
  if (btn.viewed || loadingId.value) return

  loadingId.value = btn.id
  try {
    const baseURL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''
    const token = window.localStorage.getItem('app_access_token')
    const res = await fetch(baseURL + `/api/sessions/${props.sessionId}/info-gap/click`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ button_id: btn.id }),
    })

    if (!res.ok) {
      throw new Error(`click failed: status=${res.status}`)
    }

    const data = await res.json() as { success: boolean; content?: string; keyword?: string }
    const content = data.content ?? ''
    emit('clicked', btn.id, content, btn.keyword)
  } catch {
    // 静默失败，不打断用户
  } finally {
    loadingId.value = null
  }
}
</script>

<template>
  <div v-if="buttons.length > 0" class="info-gap-container">
    <div
      v-for="btn in buttons"
      :key="btn.id"
      class="info-gap-item"
      :class="{ 'info-gap-item--viewed': btn.viewed }"
    >
      <button
        class="info-gap-btn"
        :class="{
          'info-gap-btn--viewed': btn.viewed,
          'info-gap-btn--loading': loadingId === btn.id,
        }"
        :disabled="btn.viewed || loadingId !== null"
        @click="handleClick(btn)"
      >
        <span v-if="loadingId === btn.id" class="info-gap-btn__spinner" aria-hidden="true" />
        <span class="info-gap-btn__label">{{ btn.keyword }}</span>
        <span class="info-gap-btn__chevron" aria-hidden="true">{{ btn.viewed ? '•' : '›' }}</span>
      </button>
      <div v-if="btn.explanation" class="info-gap-result">
        <p class="info-gap-result__content">{{ btn.keyword }}：{{ btn.explanation }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.info-gap-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0;
}

.info-gap-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-gap-item--viewed {
  gap: 10px;
}

.info-gap-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(217, 119, 6, 0.2);
  background: #fff7ed;
  color: #d97706;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease, opacity 0.2s ease;
}

.info-gap-btn:hover:not(:disabled) {
  background: #ffedd5;
  border-color: rgba(217, 119, 6, 0.35);
}

.info-gap-btn--viewed {
  border-color: rgba(59, 130, 246, 0.22);
  background: #f0f7ff;
  color: #1d4ed8;
  cursor: default;
}

.info-gap-btn--loading {
  opacity: 0.6;
  cursor: wait;
}

.info-gap-btn__spinner {
  width: 10px;
  height: 10px;
  border: 1.5px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  flex-shrink: 0;
}

.info-gap-btn__label {
  min-width: 0;
  line-height: 1.4;
}

.info-gap-btn__chevron {
  font-size: 15px;
  line-height: 1;
  flex-shrink: 0;
  opacity: 0.7;
}

.info-gap-btn:disabled {
  pointer-events: none;
}

.info-gap-btn:disabled .info-gap-btn__spinner {
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.info-gap-result {
  padding: 0 2px 0;
  animation: fadeIn 0.25s ease;
}

.info-gap-result__content {
  margin: 0;
  padding: 12px 14px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid rgba(148, 163, 184, 0.2);
  font-size: 14px;
  line-height: 1.7;
  color: var(--app-text-primary, #111827);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
