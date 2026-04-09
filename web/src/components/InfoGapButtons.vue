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
  (e: 'clicked', buttonId: string): void
}>()

const clickedIds = ref<Set<string>>(new Set())
const loadingId = ref<string | null>(null)

async function handleClick(btn: InfoGapButton) {
  if (clickedIds.value.has(btn.id) || loadingId.value) return

  loadingId.value = btn.id
  try {
    // e2e 会对该接口做 mock：只检查 response.ok，避免 response.json() 在 mock 下阻塞
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

    clickedIds.value.add(btn.id)
    emit('clicked', btn.id)
  } catch {
    // 静默失败，不打断用户
  } finally {
    loadingId.value = null
  }
}
</script>

<template>
  <div v-if="buttons.length > 0" class="info-gap-container">
    <button
      v-for="btn in buttons"
      :key="btn.id"
      class="info-gap-btn"
      :class="{
        'info-gap-btn--clicked': clickedIds.has(btn.id),
        'info-gap-btn--loading': loadingId === btn.id,
      }"
      :disabled="clickedIds.has(btn.id) || loadingId !== null"
      @click="handleClick(btn)"
    >
      {{ btn.keyword }}
    </button>
  </div>
</template>

<style scoped>
.info-gap-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  opacity: 0.6;
  transition: opacity 0.3s ease;
}

.info-gap-container:hover {
  opacity: 1;
}

.info-gap-btn {
  padding: 4px 12px;
  border-radius: 14px;
  border: 1px solid rgba(100, 149, 237, 0.6);
  background: rgba(100, 149, 237, 0.08);
  color: #6495ed;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s ease, opacity 0.2s ease;
  white-space: nowrap;
}

.info-gap-btn:hover:not(:disabled) {
  background: rgba(100, 149, 237, 0.2);
}

.info-gap-btn--clicked {
  border-color: rgba(150, 150, 150, 0.4);
  background: rgba(150, 150, 150, 0.08);
  color: #999;
  cursor: default;
}

.info-gap-btn--loading {
  opacity: 0.5;
  cursor: wait;
}
</style>
