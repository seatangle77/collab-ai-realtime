<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const router = useRouter()
const route = useRoute()

const menuItems = computed(() => [
  { path: '/admin/users', label: '用户管理' },
  { path: '/admin/groups', label: '群组管理' },
  { path: '/admin/memberships', label: '成员关系' },
  { path: '/admin/chat-sessions', label: '会话管理' },
  { path: '/admin/voice-profiles', label: '声纹管理' },
])

const activePath = computed(() => route.path)

function go(path: string) {
  if (path !== route.path) {
    router.push(path)
  }
}
</script>

<template>
  <el-container class="admin-layout">
    <el-aside width="220px" class="admin-sidebar">
      <div class="admin-logo">Collab AI Admin</div>
      <el-menu
        :default-active="activePath"
        background-color="#111827"
        text-color="#e5e7eb"
        active-text-color="#f97316"
        class="admin-menu"
      >
        <el-menu-item
          v-for="item in menuItems"
          :key="item.path"
          :index="item.path"
          @click="go(item.path)"
        >
          {{ item.label }}
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="admin-header">
        <h1 class="admin-header-title">管理后台</h1>
      </el-header>
      <el-main class="admin-content">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-layout {
  min-height: 100vh;
}

.admin-sidebar {
  display: flex;
  flex-direction: column;
  padding: 12px 8px;
  background: #111827;
  color: #e5e7eb;
}

.admin-logo {
  font-size: 18px;
  font-weight: 600;
  padding: 10px 12px 16px;
}

.admin-menu {
  border-right: none;
}

.admin-header {
  display: flex;
  align-items: center;
  padding: 0 20px;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
}

.admin-header-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.admin-content {
  padding: 16px 20px 24px;
  background: #f5f5f7;
}
</style>

