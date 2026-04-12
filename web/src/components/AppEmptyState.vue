<script setup lang="ts">
withDefaults(
  defineProps<{
    icon?: string
    title: string
    description?: string
    actionLabel?: string
    compact?: boolean
  }>(),
  {
    icon: '📭',
    description: '',
    actionLabel: '',
    compact: false,
  },
)

defineEmits<{
  (e: 'action'): void
}>()
</script>

<template>
  <div class="app-empty-state" :class="{ 'app-empty-state--compact': compact }">
    <div class="app-empty-state-icon" aria-hidden="true">{{ icon }}</div>
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
  background: var(--app-bg-elevated);
  border: 1px dashed var(--app-border);
}

.app-empty-state--compact {
  padding: 20px;
}

.app-empty-state-icon {
  font-size: 36px;
  line-height: 1;
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
