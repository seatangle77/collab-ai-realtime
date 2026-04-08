<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  content: string
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'dismissed'): void
}>()

const showing = ref(false)
let dismissTimer: ReturnType<typeof setTimeout> | null = null
const AUTO_DISMISS_MS = 10000

function clearDismissTimer() {
  if (dismissTimer) {
    clearTimeout(dismissTimer)
    dismissTimer = null
  }
}

function scheduleDismiss() {
  clearDismissTimer()
  dismissTimer = setTimeout(() => {
    showing.value = false
    emit('dismissed')
  }, AUTO_DISMISS_MS)
}

function handleManualClose() {
  clearDismissTimer()
  showing.value = false
  emit('dismissed')
}

function handleMouseEnter() {
  clearDismissTimer()
}

function handleMouseLeave() {
  if (!showing.value) return
  scheduleDismiss()
}

watch(
  () => props.visible,
  (val) => {
    if (!val) {
      clearDismissTimer()
      showing.value = false
      return
    }
    showing.value = true
    scheduleDismiss()
  },
)
</script>

<template>
  <Transition name="push-fade">
    <div
      v-if="showing"
      class="push-notification"
      @mouseenter="handleMouseEnter"
      @mouseleave="handleMouseLeave"
    >
      <span class="push-title">AI 建议</span>
      <span class="push-content">{{ content }}</span>
      <button type="button" class="push-close-btn" @click="handleManualClose">知道了</button>
    </div>
  </Transition>
</template>

<style scoped>
.push-notification {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  background: #111827;
  color: #f9fafb;
  padding: 12px 14px;
  border-radius: 12px;
  width: min(92vw, 560px);
  font-size: 14px;
  line-height: 1.5;
  text-align: left;
  pointer-events: auto;
  backdrop-filter: blur(6px);
  border: 1px solid #374151;
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.25);
  display: flex;
  align-items: center;
  gap: 10px;
}

.push-title {
  flex-shrink: 0;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #1d4ed8;
  color: #dbeafe;
}

.push-content {
  flex: 1;
}

.push-close-btn {
  flex-shrink: 0;
  border: 1px solid #4b5563;
  background: transparent;
  color: #e5e7eb;
  border-radius: 999px;
  font-size: 12px;
  padding: 2px 10px;
  cursor: pointer;
}

.push-close-btn:hover {
  background: #1f2937;
}

.push-fade-enter-active,
.push-fade-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}

.push-fade-enter-from,
.push-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-8px);
}
</style>
