<script setup lang="ts">
import { ref } from 'vue'

export interface InfoGapButton {
  id: string
  keyword: string
  skw_score: number
  analysis_run_id?: string
  window_start?: string
  created_at?: string
}

const props = defineProps<{
  sessionId: string
  buttons: InfoGapButton[]
}>()

const emit = defineEmits<{
  (e: 'clicked', buttonId: string, content: string, keyword: string): void
}>()

const clickedIds = ref<Set<string>>(new Set())
const loadingId = ref<string | null>(null)
const results = ref<Map<string, string>>(new Map())

async function handleClick(btn: InfoGapButton) {
  if (clickedIds.value.has(btn.id) || loadingId.value) return

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

    clickedIds.value.add(btn.id)
    if (content) {
      results.value.set(btn.id, content)
    }
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
    <div v-for="btn in buttons" :key="btn.id" class="info-gap-item">
      <button
        class="info-gap-btn"
        :class="{
          'info-gap-btn--clicked': clickedIds.has(btn.id),
          'info-gap-btn--loading': loadingId === btn.id,
        }"
        :disabled="clickedIds.has(btn.id) || loadingId !== null"
        @click="handleClick(btn)"
      >
        <span v-if="loadingId === btn.id" class="info-gap-btn__spinner" aria-hidden="true" />
        <span v-else-if="clickedIds.has(btn.id)" class="info-gap-btn__check" aria-hidden="true">✓</span>
        {{ btn.keyword }}
      </button>
      <div v-if="results.has(btn.id)" class="info-gap-result">
        <span class="info-gap-result__keyword">{{ btn.keyword }}</span>
        <p class="info-gap-result__content">{{ results.get(btn.id) }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.info-gap-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
}

.info-gap-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-gap-btn {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 14px;
  border: 1px solid rgba(217, 119, 6, 0.4);
  background: rgba(217, 119, 6, 0.07);
  color: #d97706;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s ease, opacity 0.2s ease;
  white-space: nowrap;
}

.info-gap-btn:hover:not(:disabled) {
  background: rgba(217, 119, 6, 0.15);
}

.info-gap-btn--clicked {
  border-color: rgba(150, 150, 150, 0.3);
  background: rgba(150, 150, 150, 0.06);
  color: #999;
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

.info-gap-btn__check {
  font-size: 11px;
  flex-shrink: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.info-gap-result {
  padding: 8px 12px;
  background: rgba(217, 119, 6, 0.05);
  border-left: 2px solid rgba(217, 119, 6, 0.4);
  border-radius: 0 6px 6px 0;
  animation: fadeIn 0.25s ease;
}

.info-gap-result__keyword {
  font-size: 11px;
  font-weight: 600;
  color: #d97706;
  display: block;
  margin-bottom: 3px;
}

.info-gap-result__content {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--app-text-primary, #111827);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
