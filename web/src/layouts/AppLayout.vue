<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'

const router = useRouter()
const route = useRoute()

const tabs = computed(() => [
  { path: '/app', label: '首页' },
  { path: '/app/groups', label: '我的群组' },
  { path: '/app/sessions', label: '我的会话' },
])

const active = computed(() => route.path.startsWith('/app') ? route.path : '/app')

function go(path: string) {
  if (path !== route.path) {
    router.push(path)
  }
}
</script>

<template>
  <div class="app-layout">
    <header class="app-header">
      <div class="app-logo">Collab AI</div>
      <nav class="app-nav">
        <button
          v-for="tab in tabs"
          :key="tab.path"
          class="app-nav-item"
          :data-active="active === tab.path"
          type="button"
          @click="go(tab.path)"
        >
          {{ tab.label }}
        </button>
      </nav>
    </header>
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f9fafb;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
}

.app-logo {
  font-size: 18px;
  font-weight: 600;
}

.app-nav {
  display: flex;
  gap: 8px;
}

.app-nav-item {
  border-radius: 999px;
  border: 1px solid transparent;
  padding: 6px 12px;
  font-size: 14px;
  background: transparent;
  cursor: pointer;
}

.app-nav-item[data-active='true'] {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}

.app-main {
  flex: 1;
  padding: 16px 20px 24px;
}
</style>

