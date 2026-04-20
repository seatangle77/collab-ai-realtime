<script setup lang="ts">
import { ref, computed } from 'vue'
import InfoGapButtons, { type InfoGapButton } from './InfoGapButtons.vue'

const props = defineProps<{
  sessionId: string
  summary: string
  summaryVersion: number
  hasSummary: boolean
  buttons: InfoGapButton[]
  sessionOngoing: boolean
}>()

const emit = defineEmits<{
  (e: 'buttonClicked', buttonId: string, content: string, keyword: string): void
}>()

const isExpanded = ref(false)

const previewKeywords = computed(() => props.buttons.slice(0, 3))
const hasContent = computed(() => props.hasSummary || props.buttons.length > 0)
const previewText = computed(() => {
  if (props.hasSummary && props.buttons.length > 0) return '讨论摘要 · 相关概念'
  if (props.hasSummary) return '讨论摘要'
  return '相关概念'
})

function toggleExpanded() {
  isExpanded.value = !isExpanded.value
}
</script>

<template>
  <div v-if="hasContent" class="ai-sheet">
    <div class="ai-sheet__handle-bar" @click="toggleExpanded" role="button" aria-label="展开或收起 AI 洞察">
      <div class="ai-sheet__handle-knob" />
    </div>

    <div class="ai-sheet__preview" @click="toggleExpanded">
      <span class="ai-sheet__preview-title">{{ previewText }}</span>
      <span v-if="buttons.length > 0" class="ai-sheet__preview-keywords">
        <span
          v-for="btn in previewKeywords"
          :key="btn.id"
          class="ai-sheet__preview-pill"
        >{{ btn.keyword }}</span>
        <span v-if="buttons.length > 3" class="ai-sheet__preview-more">+{{ buttons.length - 3 }}</span>
      </span>
      <span class="ai-sheet__preview-chevron" aria-hidden="true">{{ isExpanded ? '▾' : '▴' }}</span>
    </div>

    <div v-if="isExpanded" class="ai-sheet__body">
      <div v-if="hasSummary" class="ai-sheet__summary-section">
        <div class="ai-sheet__section-head">
          <span class="ai-sheet__section-label">讨论摘要</span>
          <span class="ai-sheet__section-version">v{{ summaryVersion }}</span>
        </div>
        <p class="ai-sheet__summary-content">{{ summary }}</p>
      </div>

      <template v-if="hasSummary && sessionOngoing && buttons.length > 0">
        <div class="ai-sheet__divider" aria-hidden="true" />
      </template>

      <div v-if="sessionOngoing && buttons.length > 0" class="ai-sheet__gap-section">
        <div class="ai-sheet__section-head">
          <span class="ai-sheet__section-label">相关概念</span>
        </div>
        <InfoGapButtons
          :session-id="sessionId"
          :buttons="buttons"
          @clicked="(id, content, kw) => emit('buttonClicked', id, content, kw)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.ai-sheet {
  position: fixed;
  bottom: calc(64px + env(safe-area-inset-bottom));
  left: 0;
  right: 0;
  z-index: 150;
  background: var(--app-bg-elevated, #fff);
  border-top: 1px solid var(--app-border, #e5e7eb);
  border-radius: 12px 12px 0 0;
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.08);
  max-width: var(--app-content-width-default, 480px);
  margin: 0 auto;
}

.ai-sheet__handle-bar {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 8px 0 4px;
  cursor: pointer;
}

.ai-sheet__handle-knob {
  width: 36px;
  height: 4px;
  border-radius: 2px;
  background: var(--app-border, #d1d5db);
}

.ai-sheet__preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 14px 10px;
  cursor: pointer;
  min-height: 36px;
}

.ai-sheet__preview-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-primary, #111827);
  flex-shrink: 0;
}

.ai-sheet__preview-keywords {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  overflow: hidden;
}

.ai-sheet__preview-pill {
  font-size: 12px;
  color: #b45309;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.18);
  border-radius: 999px;
  padding: 3px 8px;
  white-space: nowrap;
}

.ai-sheet__preview-more {
  font-size: 12px;
  color: var(--app-text-muted, #9ca3af);
  white-space: nowrap;
}

.ai-sheet__preview-chevron {
  font-size: 12px;
  color: var(--app-text-muted, #9ca3af);
  flex-shrink: 0;
}

.ai-sheet__body {
  max-height: 55vh;
  overflow-y: auto;
  padding: 4px 0 16px;
  display: flex;
  flex-direction: column;
  gap: 0;
  border-top: 1px solid var(--app-border, #e5e7eb);
}

.ai-sheet__summary-section {
  padding: 14px;
  background: var(--app-bg-subtle, #f9fafb);
}

.ai-sheet__gap-section {
  padding: 14px;
}

.ai-sheet__divider {
  height: 1px;
  background: var(--app-border, #e5e7eb);
  margin: 0;
}

.ai-sheet__section-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}

.ai-sheet__section-label {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text-primary, #111827);
}

.ai-sheet__section-version {
  font-size: 12px;
  color: var(--app-text-muted, #9ca3af);
}

.ai-sheet__summary-content {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: var(--app-text-primary, #111827);
  white-space: pre-wrap;
}

.ai-sheet__gap-section :deep(.info-gap-container) {
  padding: 0;
  gap: 10px;
  opacity: 1;
}
</style>
