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

watch(
  () => props.visible,
  (val) => {
    if (!val) return
    showing.value = true
    if (dismissTimer) clearTimeout(dismissTimer)
    dismissTimer = setTimeout(() => {
      showing.value = false
      emit('dismissed')
    }, 4000)
  },
)
</script>

<template>
  <Transition name="push-fade">
    <div v-if="showing" class="push-notification">
      <span class="push-content">{{ content }}</span>
    </div>
  </Transition>
</template>

<style scoped>
.push-notification {
  position: fixed;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  background: rgba(30, 30, 30, 0.88);
  color: #fff;
  padding: 10px 20px;
  border-radius: 20px;
  max-width: 80vw;
  font-size: 14px;
  line-height: 1.5;
  text-align: center;
  pointer-events: none;
  backdrop-filter: blur(6px);
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
