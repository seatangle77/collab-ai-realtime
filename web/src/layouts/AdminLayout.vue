<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Fold, Expand } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

interface AdminMenuItem {
  path: string
  label: string
}

interface AdminMenuGroup {
  label: string
  items: AdminMenuItem[]
}

const menuGroups = computed<AdminMenuGroup[]>(() => [
  {
    label: '基础数据',
    items: [
      { path: '/admin/users', label: '用户管理' },
      { path: '/admin/groups', label: '群组管理' },
      { path: '/admin/memberships', label: '成员关系' },
      { path: '/admin/chat-sessions', label: '会话管理' },
      { path: '/admin/voice-profiles', label: '声纹管理' },
      { path: '/admin/speech-transcripts', label: '语音转写' },
    ],
  },
  {
    label: 'AI 分析',
    items: [
      { path: '/admin/discussion-states', label: '讨论状态' },
      { path: '/admin/window-metrics', label: '窗口指标' },
      // { path: '/admin/window-metrics-keywords', label: '窗口关键词' },
      { path: '/admin/window-metrics-batch-reasoning', label: '窗口论证批量日志' },
      { path: '/admin/discussion-summaries', label: '讨论摘要' },
      { path: '/admin/info-gap-buttons', label: '信息缺口按钮' },
      { path: '/admin/info-gap-skw', label: '关键词 SKW' },
      { path: '/admin/ai-push-analysis', label: 'AI 推送分析' },
      { path: '/admin/info-gap-recall-analysis', label: '关键词召回分析' },
    ],
  },
  {
    label: '推送管理',
    items: [
      { path: '/admin/push-queue', label: '推送队列' },
      { path: '/admin/push-logs', label: '推送日志' },
    ],
  },
])

const collapsed = ref(false)
const activePath = computed(() => route.path)

function go(path: string) {
  if (path !== route.path) {
    router.push(path)
  }
}
</script>

<template>
  <el-container class="admin-layout">
    <el-aside :width="collapsed ? '0px' : '220px'" class="admin-sidebar" style="overflow: hidden; transition: width 0.2s;">
      <div class="admin-logo">Collab AI Admin</div>
      <el-menu
        :default-active="activePath"
        background-color="#111827"
        text-color="#e5e7eb"
        active-text-color="#f97316"
        class="admin-menu"
      >
        <el-menu-item-group
          v-for="group in menuGroups"
          :key="group.label"
        >
          <template #title>{{ group.label }}</template>
          <el-menu-item
            v-for="item in group.items"
            :key="item.path"
            :index="item.path"
            @click="go(item.path)"
          >
            {{ item.label }}
          </el-menu-item>
        </el-menu-item-group>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="admin-header">
        <el-button :icon="collapsed ? Expand : Fold" circle size="small" @click="collapsed = !collapsed" />
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

:deep(.el-menu-item-group__title) {
  padding: 10px 12px 6px;
  color: #9ca3af;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

:deep(.el-menu-item-group__title + ul) {
  margin-bottom: 10px;
}

.admin-header {
  display: flex;
  align-items: center;
  gap: 12px;
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
