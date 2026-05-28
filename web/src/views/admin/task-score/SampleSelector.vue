<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Check, Close } from '@element-plus/icons-vue'
import type { AdminGroup } from '../../../types/admin'
import { conditionLabel, selectedGroupNames } from './reportHelpers'

const props = defineProps<{
  conditionColumns: string[]
  groupOptionsByCondition: Record<string, AdminGroup[]>
  loadingGroups: boolean
}>()

const selectedGroupIdsByCondition = defineModel<Record<string, string[]>>({ required: true })

const sampleDialogVisible = ref(false)
const activeSampleCondition = ref('')
const groupSearchText = ref('')
const sampleTreeRef = ref()

const activeConditionGroups = computed(() =>
  activeSampleCondition.value
    ? props.groupOptionsByCondition[activeSampleCondition.value] ?? []
    : [],
)
const selectedActiveGroupIds = computed({
  get: () => selectedGroupIdsByCondition.value[activeSampleCondition.value] ?? [],
  set: (value: string[]) => {
    if (activeSampleCondition.value) {
      selectedGroupIdsByCondition.value[activeSampleCondition.value] = value
    }
  },
})
const sampleTreeData = computed(() => [
  {
    id: `condition:${activeSampleCondition.value}`,
    label: `${conditionLabel(activeSampleCondition.value)}（共 ${activeConditionGroups.value.length} 组）`,
    children: activeConditionGroups.value.map((group) => ({
      id: group.id,
      label: group.name,
      meta: group.id,
    })),
  },
])
const sampleTreeProps = { label: 'label', children: 'children' }

function openSampleDialog(condition: string) {
  activeSampleCondition.value = condition
  groupSearchText.value = ''
  sampleDialogVisible.value = true
  nextTick(() => {
    sampleTreeRef.value?.setCheckedKeys(selectedGroupIdsByCondition.value[condition] ?? [])
  })
}

function selectAllActiveGroups() {
  if (!activeSampleCondition.value) return
  const ids = activeConditionGroups.value.map((group) => group.id)
  selectedGroupIdsByCondition.value[activeSampleCondition.value] = ids
  sampleTreeRef.value?.setCheckedKeys(ids)
}

function clearActiveGroups() {
  if (!activeSampleCondition.value) return
  selectedGroupIdsByCondition.value[activeSampleCondition.value] = []
  sampleTreeRef.value?.setCheckedKeys([])
}

function filterSampleTree(value: string, data: { label?: string; meta?: string }) {
  if (!value) return true
  const keyword = value.toLowerCase()
  return `${data.label ?? ''} ${data.meta ?? ''}`.toLowerCase().includes(keyword)
}

function onSampleTreeCheck(_node: unknown, state: { checkedKeys: Array<string | number> }) {
  if (!activeSampleCondition.value) return
  const validGroupIds = new Set(activeConditionGroups.value.map((group) => group.id))
  selectedGroupIdsByCondition.value[activeSampleCondition.value] = state.checkedKeys
    .map(String)
    .filter((key) => validGroupIds.has(key))
}

function selectedNames(condition: string) {
  return selectedGroupNames(condition, selectedGroupIdsByCondition.value, props.groupOptionsByCondition)
}

watch(groupSearchText, (value) => {
  sampleTreeRef.value?.filter(value)
})
</script>

<template>
  <el-card class="sample-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>样本选择</strong>
        <span>每个条件只列出该条件下的小组</span>
      </div>
    </template>
    <div class="sample-grid">
      <div v-for="condition in conditionColumns" :key="condition" class="sample-field">
        <div class="sample-field-head">
          <label>{{ conditionLabel(condition) }}</label>
          <el-tag size="small" effect="plain">
            {{ selectedGroupIdsByCondition[condition]?.length ?? 0 }} / {{ groupOptionsByCondition[condition]?.length ?? 0 }}
          </el-tag>
        </div>
        <div class="sample-trigger-row">
          <button
            class="sample-select-trigger"
            type="button"
            :disabled="loadingGroups"
            @click="openSampleDialog(condition)"
          >
            <span>{{ selectedGroupIdsByCondition[condition]?.length ? selectedNames(condition) : '点击选择小组' }}</span>
            <span class="sample-select-arrow">⌄</span>
          </button>
          <el-button
            :icon="Close"
            circle
            size="small"
            :disabled="(selectedGroupIdsByCondition[condition]?.length ?? 0) === 0"
            @click="selectedGroupIdsByCondition[condition] = []"
          />
        </div>
      </div>
    </div>
  </el-card>

  <el-dialog
    v-model="sampleDialogVisible"
    :title="`${conditionLabel(activeSampleCondition)}样本选择`"
    width="720px"
  >
    <div class="sample-dialog-toolbar">
      <el-input v-model="groupSearchText" clearable placeholder="搜索小组名称或 ID" />
      <div class="sample-dialog-actions">
        <el-button :icon="Check" @click="selectAllActiveGroups">全选</el-button>
        <el-button @click="clearActiveGroups">清空</el-button>
      </div>
    </div>

    <div class="sample-tree-shell">
      <el-tree
        ref="sampleTreeRef"
        :data="sampleTreeData"
        :props="sampleTreeProps"
        node-key="id"
        show-checkbox
        default-expand-all
        :expand-on-click-node="false"
        :filter-node-method="filterSampleTree"
        @check="onSampleTreeCheck"
      >
        <template #default="{ data }">
          <div class="sample-tree-node" :class="{ 'is-group': !data.children }">
            <span class="sample-tree-label">{{ data.label }}</span>
            <span v-if="data.meta" class="sample-tree-meta">{{ data.meta }}</span>
          </div>
        </template>
      </el-tree>
      <el-empty v-if="activeConditionGroups.length === 0" description="当前条件下没有小组" />
    </div>

    <template #footer>
      <div class="dialog-footer">
        <span>已选 {{ selectedActiveGroupIds.length }} 组</span>
        <el-button type="primary" @click="sampleDialogVisible = false">完成</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.sample-card {
  border: 1px solid #e3e9f2;
  border-radius: 8px;
}

.card-title,
.sample-field-head,
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-title strong {
  font-size: 14px;
  font-weight: 600;
  color: #1e2d40;
}

.card-title span,
.dialog-footer {
  color: #64748b;
  font-size: 12px;
}

.sample-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
  gap: 12px 20px;
}

.sample-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.sample-field label {
  color: #324055;
  font-size: 13px;
  font-weight: 600;
}

.sample-trigger-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sample-select-trigger {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 32px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 10px;
  border: 1px solid #d8e1ee;
  border-radius: 6px;
  background: #ffffff;
  color: #172033;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  text-align: left;
}

.sample-select-trigger:hover {
  border-color: #a8c3ff;
}

.sample-select-trigger span:first-child {
  overflow: hidden;
  min-width: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sample-select-arrow {
  flex: 0 0 auto;
  color: #8a97aa;
  font-size: 16px;
}

.sample-dialog-toolbar {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) auto;
  gap: 12px;
  margin-bottom: 14px;
}

.sample-dialog-actions {
  display: flex;
  gap: 8px;
}

.sample-tree-shell {
  max-height: 430px;
  overflow: auto;
  padding: 10px;
  border: 1px solid #e3e9f2;
  border-radius: 8px;
  background: #f8fafc;
}

.sample-tree-shell :deep(.el-tree) {
  background: transparent;
}

.sample-tree-shell :deep(.el-tree-node__content) {
  min-height: 38px;
  border-radius: 6px;
}

.sample-tree-node {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 8px;
}

.sample-tree-node.is-group {
  padding: 5px 0;
}

.sample-tree-label {
  overflow: hidden;
  color: #172033;
  font-size: 14px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sample-tree-meta {
  color: #748197;
  font-size: 12px;
}

@media (max-width: 1100px) {
  .sample-grid,
  .sample-dialog-toolbar {
    grid-template-columns: 1fr;
  }
}
</style>
