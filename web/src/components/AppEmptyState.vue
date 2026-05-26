<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import {
  ChatLineRound,
  Document,
  FolderOpened,
  Microphone,
  User,
} from '@element-plus/icons-vue'

const iconMap: Record<string, Component> = {
  chat: ChatLineRound,
  document: Document,
  empty: FolderOpened,
  group: User,
  microphone: Microphone,
}

const legacyIconMap: Record<string, keyof typeof iconMap> = {
  '👥': 'group',
  '🧑‍🤝‍🧑': 'group',
  '📭': 'empty',
  '🗂️': 'empty',
  '📝': 'document',
  '🎙️': 'microphone',
}

const props = withDefaults(
  defineProps<{
    icon?: string
    title: string
    description?: string
    actionLabel?: string
    compact?: boolean
  }>(),
  {
    icon: 'empty',
    description: '',
    actionLabel: '',
    compact: false,
  },
)

const emptyIcon = computed(() => {
  const key = iconMap[props.icon] ? props.icon : legacyIconMap[props.icon] || 'empty'
  return iconMap[key]
})

defineEmits<{
  (e: 'action'): void
}>()
</script>

<template>
  <div class="app-empty-state" :class="{ 'app-empty-state--compact': compact }">
    <div class="app-empty-state-icon" aria-hidden="true">
      <component :is="emptyIcon" class="app-empty-state-icon-svg" />
    </div>
    <p class="app-empty-state-title">{{ title }}</p>
    <p v-if="description" class="app-empty-state-description">{{ description }}</p>
    <button
      v-if="actionLabel"
      type="button"
      class="app-empty-state-action"
      @click="$emit('action')"
    >
      {{ actionLabel }}
    </button>
  </div>
</template>

<style scoped>
.app-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 10px;
  padding: 40px 20px;
  border-radius: var(--app-radius-card);
  background: #fbfdff;
  border: 1px solid var(--app-border);
}

.app-empty-state--compact {
  padding: 20px;
}

.app-empty-state-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--app-radius-pill);
  background: var(--app-primary-soft);
  color: var(--app-primary);
}

.app-empty-state-icon-svg {
  width: 24px;
  height: 24px;
}

.app-empty-state-title {
  margin: 0;
  font-size: var(--app-font-size-heading);
  font-weight: 600;
  color: var(--app-text-primary);
}

.app-empty-state-description {
  margin: 0;
  max-width: 32rem;
  font-size: var(--app-font-size-body);
  line-height: 1.6;
  color: var(--app-text-secondary);
}

.app-empty-state-action {
  margin-top: 2px;
  padding: 8px 16px;
  border: 1px solid var(--app-primary);
  border-radius: var(--app-radius-pill);
  background: var(--app-primary);
  color: var(--app-bg-elevated);
  font-size: var(--app-font-size-body);
  font-family: inherit;
  cursor: pointer;
}

.app-empty-state-action:hover {
  background: var(--app-primary-hover);
  border-color: var(--app-primary-hover);
}
</style>
