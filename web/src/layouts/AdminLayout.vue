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
  {
    label: '数据分析',
    items: [
      { path: '/admin/task-score-analysis', label: '任务分数录入' },
      { path: '/admin/task-score-report', label: '任务分数分析' },
      { path: '/admin/questionnaire-entries', label: '量表填写记录' },
      { path: '/admin/questionnaire-report', label: '量表分析报告' },
      { path: '/admin/coi-utterances', label: 'CoI 发言编码' },
      { path: '/admin/coi-analysis', label: 'CoI 认知参与度分析' },
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
    <el-aside :width="collapsed ? '0px' : '252px'" class="admin-sidebar">
      <div class="admin-brand">
        <div class="admin-brand-mark">CA</div>
        <div>
          <div class="admin-logo">Collab AI</div>
          <div class="admin-logo-subtitle">Admin Console</div>
        </div>
      </div>
      <el-menu
        :default-active="activePath"
        background-color="transparent"
        text-color="#e5e7eb"
        active-text-color="#166534"
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
    <el-container class="admin-main-shell">
      <el-button class="admin-sidebar-toggle" :icon="collapsed ? Expand : Fold" circle @click="collapsed = !collapsed" />
      <el-main class="admin-content">
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-layout {
  height: 100vh;
  min-height: 100vh;
  background: #f4f6fb;
  color: #172033;
  font-size: 15px;
  overflow: hidden;
}

.admin-sidebar {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 18px 14px;
  background:
    linear-gradient(180deg, rgba(34, 197, 94, 0.10), rgba(34, 197, 94, 0) 32%),
    #152033;
  color: #f8fafc;
  transition: width 0.2s ease;
  box-shadow: 12px 0 30px rgba(15, 23, 42, 0.08);
}

.admin-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 8px 20px;
}

.admin-brand-mark {
  display: grid;
  flex: 0 0 auto;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 10px;
  background: #ffffff;
  color: #152033;
  font-size: 14px;
  font-weight: 800;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.18);
}

.admin-logo {
  font-size: 17px;
  font-weight: 750;
  line-height: 1.1;
}

.admin-logo-subtitle {
  margin-top: 3px;
  color: #9fb0c7;
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.admin-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  overflow-y: auto;
}

:deep(.el-menu) {
  background: transparent;
}

:deep(.el-menu-item-group__title) {
  padding: 16px 10px 8px;
  color: #8ea0bb;
  font-size: 12px;
  font-weight: 750;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

:deep(.el-menu-item-group__title + ul) {
  margin-bottom: 8px;
}

:deep(.el-menu-item) {
  height: 42px;
  margin: 2px 0;
  border-radius: 8px;
  color: #d8e0ea;
  font-size: 15px;
  font-weight: 600;
  line-height: 42px;
}

:deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.08);
  color: #ffffff;
}

:deep(.el-menu-item.is-active) {
  background: #ffffff;
  color: #166534;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.16);
}

.admin-main-shell {
  position: relative;
  min-width: 0;
}

.admin-sidebar-toggle {
  position: absolute;
  z-index: 20;
  top: 18px;
  left: 20px;
  --el-button-size: 38px;
  background: rgba(255, 255, 255, 0.94);
  border-color: #d8e1ee;
  color: #324055;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.admin-content {
  height: 100vh;
  padding: 24px 28px 32px 76px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.76), rgba(244, 246, 251, 0) 220px),
    #f4f6fb;
  overflow: auto;
}

@media (max-width: 900px) {
  .admin-content {
    padding: 18px 16px 28px 66px;
  }

  .admin-sidebar-toggle {
    top: 14px;
    left: 14px;
  }
}
</style>
