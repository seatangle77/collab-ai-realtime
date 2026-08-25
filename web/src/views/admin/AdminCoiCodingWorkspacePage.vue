<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminCoiAiCodingPage from './AdminCoiAiCodingPage.vue'
import AdminCoiIndependentCodingPage from './AdminCoiIndependentCodingPage.vue'

type CodingWorkspace = 'human' | 'coder_c'

const route = useRoute()
const router = useRouter()
const workspace = ref<CodingWorkspace>(route.query.coder === 'c' ? 'coder_c' : 'human')

watch(workspace, async (value) => {
  const query = { ...route.query }
  if (value === 'coder_c') query.coder = 'c'
  else delete query.coder
  await router.replace({ path: '/admin/coi-independent-coding', query })
})
</script>

<template>
  <div class="coding-workspace-tabs">
    <el-tabs v-model="workspace">
      <el-tab-pane label="研究员 A / B" name="human" />
      <el-tab-pane label="研究员 C（AI 辅助）" name="coder_c" />
    </el-tabs>
  </div>

  <AdminCoiIndependentCodingPage v-if="workspace === 'human'" />
  <AdminCoiAiCodingPage v-else />
</template>

<style scoped>
.coding-workspace-tabs {
  margin: 0 20px 4px;
  padding: 0 20px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
}
.coding-workspace-tabs :deep(.el-tabs__header) { margin: 0; }
</style>
