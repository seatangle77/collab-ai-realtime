<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Refresh, Select } from '@element-plus/icons-vue'
import type { AdminGroup, AdminMembership } from '../../types/admin'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminMemberships } from '../../api/admin/memberships'
import {
  getTaskScoreEntry,
  saveTaskScoreEntry,
  type TaskScoreAnswers,
  type TaskScoreResult,
} from '../../api/admin/task-score-entries'

type TaskId = 'moon_survival' | 'lost_at_sea' | 'winter_survival'
type AnswerColumnKey = string

interface TaskItem {
  key: string
  label: string
  expertRank: number
}

interface TaskConfig {
  id: TaskId
  label: string
  itemCount: number
  items: TaskItem[]
}

interface ScoreSummary {
  label: string
  score: number
}

interface RankRow {
  rank: number
}

interface DragState {
  columnKey: AnswerColumnKey
  rank: number
}

const CONDITION_LABELS: Record<string, string> = {
  no_assistance: '无辅助',
  glasses: '智能眼镜',
  app_notification: 'APP 通知',
}

const TASK_CONFIGS: Record<TaskId, TaskConfig> = {
  moon_survival: {
    id: 'moon_survival',
    label: 'NASA Moon Survival（月球求生）',
    itemCount: 15,
    items: [
      { key: 'oxygen_tanks', label: '两罐 100 磅氧气', expertRank: 1 },
      { key: 'water_5_gallons', label: '5 加仑饮用水', expertRank: 2 },
      { key: 'stellar_map', label: '星象图（月面星座）', expertRank: 3 },
      { key: 'food_concentrate', label: '食物浓缩包', expertRank: 4 },
      { key: 'solar_fm_transceiver', label: '太阳能调频收发器', expertRank: 5 },
      { key: 'nylon_rope_50ft', label: '50 英尺尼龙绳', expertRank: 6 },
      { key: 'first_aid_kit', label: '急救箱（含注射针）', expertRank: 7 },
      { key: 'parachute_silk', label: '降落伞丝绸', expertRank: 8 },
      { key: 'life_raft', label: '救生筏', expertRank: 9 },
      { key: 'signal_flares', label: '信号弹', expertRank: 10 },
      { key: 'pistols_45_caliber', label: '两把 .45 口径手枪', expertRank: 11 },
      { key: 'dehydrated_milk', label: '一箱脱水奶粉', expertRank: 12 },
      { key: 'portable_heater', label: '便携式加热装置', expertRank: 13 },
      { key: 'magnetic_compass', label: '磁罗盘', expertRank: 14 },
      { key: 'matches', label: '一盒火柴', expertRank: 15 },
    ],
  },
  lost_at_sea: {
    id: 'lost_at_sea',
    label: 'Lost at Sea（海上求生）',
    itemCount: 15,
    items: [
      { key: 'shaving_mirror', label: '剃须镜', expertRank: 1 },
      { key: 'oil_gas_mixture_2_gallons', label: '2 加仑油气混合物', expertRank: 2 },
      { key: 'water_5_gallons', label: '5 加仑饮用水', expertRank: 3 },
      { key: 'army_c_rations', label: '一箱美军 C 口粮', expertRank: 4 },
      { key: 'opaque_plastic_sheet', label: '20 平方英尺不透明塑料布', expertRank: 5 },
      { key: 'chocolate_bars', label: '两箱巧克力棒', expertRank: 6 },
      { key: 'fishing_kit', label: '钓鱼套装', expertRank: 7 },
      { key: 'nylon_rope_15ft', label: '15 英尺尼龙绳', expertRank: 8 },
      { key: 'floating_seat_cushion', label: '浮力座垫', expertRank: 9 },
      { key: 'shark_repellent', label: '鲨鱼驱避剂', expertRank: 10 },
      { key: 'rum_160_proof', label: '160 度朗姆酒（1 夸脱）', expertRank: 11 },
      { key: 'transistor_radio', label: '小型晶体管收音机', expertRank: 12 },
      { key: 'pacific_ocean_chart', label: '太平洋海图', expertRank: 13 },
      { key: 'mosquito_netting', label: '防蚊网', expertRank: 14 },
      { key: 'sextant', label: '六分仪', expertRank: 15 },
    ],
  },
  winter_survival: {
    id: 'winter_survival',
    label: 'Winter Survival（冬季求生）',
    itemCount: 12,
    items: [
      { key: 'windproof_matches', label: '火柴（防风火柴盒）', expertRank: 1 },
      { key: 'candle', label: '蜡烛', expertRank: 2 },
      { key: 'large_caliber_pistol', label: '大口径手枪（含子弹）', expertRank: 3 },
      { key: 'household_knife', label: '家用短刀', expertRank: 4 },
      { key: 'newspapers', label: '报纸（每人一份）', expertRank: 5 },
      { key: 'hand_axe', label: '手斧', expertRank: 6 },
      { key: 'wool_scarf', label: '厚羊毛围巾（每人）', expertRank: 7 },
      { key: 'vegetable_oil', label: '植物油（1 升）', expertRank: 8 },
      { key: 'flashlight', label: '手电筒（备用电池）', expertRank: 9 },
      { key: 'whiskey', label: '威士忌酒（1 瓶）', expertRank: 10 },
      { key: 'local_aerial_map', label: '航空地图（本地区）', expertRank: 11 },
      { key: 'compass', label: '指南针', expertRank: 12 },
    ],
  },
}

const loadingGroups = ref(false)
const loadingMembers = ref(false)
const savingEntry = ref(false)
const groups = ref<AdminGroup[]>([])
const members = ref<AdminMembership[]>([])
const selectedGroupId = ref('')
const selectedTaskId = ref<TaskId>('moon_survival')
const orderedInputs = reactive<Record<number, Record<AnswerColumnKey, string | undefined>>>({})
const scoreSummaries = ref<ScoreSummary[]>([])
const dragState = ref<DragState | null>(null)
const dragOverState = ref<DragState | null>(null)

const selectedGroup = computed(() => groups.value.find((group) => group.id === selectedGroupId.value))
const selectedTask = computed(() => TASK_CONFIGS[selectedTaskId.value])
const rankRows = computed<RankRow[]>(() =>
  Array.from({ length: selectedTask.value.itemCount }, (_, index) => ({ rank: index + 1 })),
)
const itemByKey = computed(() => new Map(selectedTask.value.items.map((item) => [item.key, item])))
const activeMembers = computed(() => members.value.filter((member) => member.status === 'active').slice(0, 3))
const answerColumns = computed(() => [
  ...activeMembers.value.map((member, index) => ({
    key: member.user_id,
    label: member.user_name || `成员 ${index + 1}`,
    subLabel: member.role === 'leader' ? 'leader' : 'member',
    participantId: member.user_id,
  })),
  { key: 'group_final', label: '小组最终', subLabel: 'group', participantId: null },
])

function conditionLabel(condition?: string) {
  return condition ? (CONDITION_LABELS[condition] ?? condition) : '—'
}

function conditionTagType(condition?: string): 'success' | 'warning' | 'info' | '' {
  if (condition === 'no_assistance') return 'info'
  if (condition === 'glasses') return 'success'
  if (condition === 'app_notification') return 'warning'
  return ''
}

function resetRanks() {
  for (const key of Object.keys(orderedInputs)) {
    delete orderedInputs[Number(key)]
  }
  scoreSummaries.value = []
  for (let rank = 1; rank <= selectedTask.value.itemCount; rank += 1) {
    orderedInputs[rank] = {}
  }
}

function applyResultPreview(result: TaskScoreResult | null | undefined) {
  if (!result) {
    scoreSummaries.value = []
    return
  }
  scoreSummaries.value = [
    ...result.individual_scores.map((item, index) => ({
      label: `IS${index + 1} ${item.participant_name || item.participant_id}`,
      score: item.score,
    })),
    { label: 'AIS 平均个人分', score: result.ais },
    { label: 'Best IS 最佳个人分', score: result.best_is },
    { label: 'GS 小组最终分', score: result.gs },
    { label: '弱协同值 AIS - GS', score: result.weak_synergy },
    { label: '强协同值 Best IS - GS', score: result.strong_synergy },
  ]
}

function applyAnswers(answers: TaskScoreAnswers) {
  resetRanks()
  for (const answer of answers.individual) {
    answer.ordered_items.forEach((itemKey, index) => {
      const rank = index + 1
      if (!orderedInputs[rank]) orderedInputs[rank] = {}
      orderedInputs[rank][answer.participant_id] = itemKey
    })
  }
  answers.group_final.ordered_items.forEach((itemKey, index) => {
    const rank = index + 1
    if (!orderedInputs[rank]) orderedInputs[rank] = {}
    orderedInputs[rank].group_final = itemKey
  })
}

async function loadExistingEntry() {
  if (!selectedGroupId.value || !selectedTaskId.value) return
  try {
    const entry = await getTaskScoreEntry(selectedGroupId.value, selectedTaskId.value)
    if (!entry) {
      scoreSummaries.value = []
      return
    }
    applyAnswers(entry.answers_json)
    applyResultPreview(entry.result_json)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载已有任务分数录入失败')
  }
}

async function fetchGroups() {
  loadingGroups.value = true
  try {
    const res = await listAdminGroups({ page: 1, page_size: 200 })
    groups.value = res.items
    const firstGroup = groups.value[0]
    if (!selectedGroupId.value && firstGroup) {
      selectedGroupId.value = firstGroup.id
      await fetchMembers()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
}

async function fetchMembers() {
  if (!selectedGroupId.value) return
  loadingMembers.value = true
  scoreSummaries.value = []
  try {
    const res = await listAdminMemberships({
      page: 1,
      page_size: 20,
      group_id: selectedGroupId.value,
      status: 'active',
    })
    members.value = res.items
    resetRanks()
    await loadExistingEntry()
  } catch (e: any) {
    ElMessage.error(e?.message || '加载小组成员失败')
  } finally {
    loadingMembers.value = false
  }
}

function onTaskChange() {
  resetRanks()
  loadExistingEntry()
}

function itemFor(rank: number, columnKey: AnswerColumnKey): string | undefined {
  return orderedInputs[rank]?.[columnKey]
}

function setItem(rank: number, columnKey: AnswerColumnKey, value: string | undefined) {
  if (!orderedInputs[rank]) orderedInputs[rank] = {}
  orderedInputs[rank][columnKey] = value
  scoreSummaries.value = []
}

function startDrag(rank: number, columnKey: AnswerColumnKey, event: DragEvent) {
  if (!itemFor(rank, columnKey)) return
  dragState.value = { rank, columnKey }
  dragOverState.value = null
  event.dataTransfer?.setData('text/plain', `${columnKey}:${rank}`)
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.dropEffect = 'move'
  }
}

function finishDrag() {
  dragState.value = null
  dragOverState.value = null
}

function dropOnRank(targetRank: number, columnKey: AnswerColumnKey, event: DragEvent) {
  const raw = event.dataTransfer?.getData('text/plain') ?? ''
  const [rawColumnKey, rawRank] = raw.split(':')
  const fallbackRank = Number(rawRank)
  const source = dragState.value ?? (
    rawColumnKey && Number.isFinite(fallbackRank)
      ? { columnKey: rawColumnKey, rank: fallbackRank }
      : null
  )
  if (!source || source.columnKey !== columnKey || source.rank === targetRank) return

  const values = rankRows.value.map((row) => orderedInputs[row.rank]?.[columnKey])
  const sourceIndex = source.rank - 1
  const targetIndex = targetRank - 1
  const [moved] = values.splice(sourceIndex, 1)
  values.splice(targetIndex, 0, moved)

  rankRows.value.forEach((row, index) => {
    const rowInputs = orderedInputs[row.rank] ?? {}
    orderedInputs[row.rank] = rowInputs
    rowInputs[columnKey] = values[index]
  })
  scoreSummaries.value = []
  finishDrag()
}

function markDragOver(rank: number, columnKey: AnswerColumnKey) {
  if (!dragState.value || dragState.value.columnKey !== columnKey || dragState.value.rank === rank) {
    return
  }
  if (dragOverState.value?.columnKey === columnKey && dragOverState.value?.rank === rank) {
    return
  }
  dragOverState.value = { rank, columnKey }
}

function validateColumn(columnKey: AnswerColumnKey, columnLabel: string): string | null {
  const values = rankRows.value.map((row) => orderedInputs[row.rank]?.[columnKey])
  if (values.some((value) => value === undefined || value === null)) {
    return `${columnLabel} 还有未选择的物品`
  }

  const selectedItems = values as string[]
  const uniqueValues = new Set(selectedItems)
  if (uniqueValues.size !== selectedTask.value.itemCount) {
    return `${columnLabel} 存在重复物品`
  }

  for (const itemKey of selectedItems) {
    if (!itemByKey.value.has(itemKey)) {
      return `${columnLabel} 包含不属于当前任务的物品`
    }
  }
  return null
}

function calculateTotalScore(columnKey: AnswerColumnKey): number {
  return rankRows.value.reduce((sum, row) => {
    const itemKey = orderedInputs[row.rank]?.[columnKey]
    const item = itemKey ? itemByKey.value.get(itemKey) : undefined
    if (!item) return sum
    return sum + Math.abs(row.rank - item.expertRank)
  }, 0)
}

function isItemSelectedElsewhere(itemKey: string, columnKey: AnswerColumnKey, currentRank: number): boolean {
  return rankRows.value.some((row) => row.rank !== currentRank && orderedInputs[row.rank]?.[columnKey] === itemKey)
}

function validateAndPreview() {
  if (!selectedGroup.value) {
    ElMessage.warning('请先选择小组')
    return
  }
  if (activeMembers.value.length !== 3) {
    ElMessage.warning('任务分数录入需要 3 位 active 小组成员')
    return
  }

  for (const column of answerColumns.value) {
    const error = validateColumn(column.key, column.label)
    if (error) {
      ElMessage.warning(error)
      return
    }
  }

  const individualScores = activeMembers.value.map((member, index) => ({
    label: member.user_name || `成员 ${index + 1}`,
    score: calculateTotalScore(member.user_id),
  }))
  const gs = calculateTotalScore('group_final')
  const ais = individualScores.reduce((sum, item) => sum + item.score, 0) / individualScores.length
  const bestIs = Math.min(...individualScores.map((item) => item.score))

  scoreSummaries.value = [
    ...individualScores.map((item, index) => ({ label: `IS${index + 1} ${item.label}`, score: item.score })),
    { label: 'AIS 平均个人分', score: Number(ais.toFixed(2)) },
    { label: 'Best IS 最佳个人分', score: bestIs },
    { label: 'GS 小组最终分', score: gs },
    { label: '弱协同值 AIS - GS', score: Number((ais - gs).toFixed(2)) },
    { label: '强协同值 Best IS - GS', score: Number((bestIs - gs).toFixed(2)) },
  ]
  ElMessage.success('录入校验通过，已生成计算预览')
}

function buildEntryPayload() {
  if (!selectedGroup.value) {
    throw new Error('请先选择小组')
  }
  return {
    group_id: selectedGroup.value.id,
    task_id: selectedTask.value.id,
    answers: {
      individual: activeMembers.value.map((member) => ({
        participant_id: member.user_id,
        participant_name: member.user_name ?? null,
        ordered_items: rankRows.value.map((row) => orderedInputs[row.rank]?.[member.user_id] ?? ''),
      })),
      group_final: {
        ordered_items: rankRows.value.map((row) => orderedInputs[row.rank]?.group_final ?? ''),
      },
    },
  }
}

async function saveEntryDraft() {
  validateAndPreview()
  if (scoreSummaries.value.length === 0) return
  if (!selectedGroup.value) return

  savingEntry.value = true
  try {
    const payload = buildEntryPayload()
    const entry = await saveTaskScoreEntry(payload)
    applyResultPreview(entry.result_json)
    ElMessage.success('任务分数录入已保存')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存任务分数录入失败')
  } finally {
    savingEntry.value = false
  }
}

onMounted(() => {
  resetRanks()
  fetchGroups()
})
</script>

<template>
  <div class="task-score-page">
    <div class="page-header">
      <div>
        <h1>任务分数</h1>
        <p>录入每组每个任务的个人排序和小组最终排序，系统按专家答案计算客观表现分。</p>
      </div>
      <el-button :icon="Refresh" @click="fetchGroups">刷新群组</el-button>
    </div>

    <el-card class="control-card" shadow="never">
      <el-form label-width="86px" class="control-form">
        <el-form-item label="小组">
          <el-select
            v-model="selectedGroupId"
            data-testid="task-score-group-select"
            filterable
            :loading="loadingGroups"
            placeholder="选择小组"
            @change="fetchMembers"
          >
            <el-option
              v-for="group in groups"
              :key="group.id"
              :label="`${group.name} (${group.id})`"
              :value="group.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="实验条件">
          <el-tag :type="conditionTagType(selectedGroup?.condition)" size="large">
            {{ conditionLabel(selectedGroup?.condition) }}
          </el-tag>
        </el-form-item>
        <el-form-item label="任务">
          <el-select v-model="selectedTaskId" data-testid="task-score-task-select" @change="onTaskChange">
            <el-option
              v-for="task in Object.values(TASK_CONFIGS)"
              :key="task.id"
              :label="task.label"
              :value="task.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="16" class="content-row">
      <el-col :xs="24" :lg="18">
        <el-card class="entry-card" shadow="never">
          <template #header>
            <div class="card-header">
              <div>
                <strong>排名录入矩阵</strong>
                <span>按纸面顺序从第 1 名往下录入，每列 {{ selectedTask.itemCount }} 个物品且不可重复</span>
              </div>
              <div class="header-actions">
                <el-button :icon="Check" type="primary" data-testid="task-score-preview-button" @click="validateAndPreview">校验并计算</el-button>
                <el-button type="success" data-testid="task-score-save-button" :loading="savingEntry" @click="saveEntryDraft">保存录入</el-button>
              </div>
            </div>
          </template>

          <el-alert
            v-if="activeMembers.length !== 3"
            type="warning"
            show-icon
            :closable="false"
            title="当前小组 active 成员不是 3 人，暂不适合录入任务分数。"
            class="member-alert"
          />

          <el-table
            v-loading="loadingMembers"
            :data="rankRows"
            border
            height="620"
            class="score-entry-table"
          >
            <el-table-column prop="rank" label="名次" width="64" align="center" fixed class-name="rank-cell" />
            <el-table-column
              v-for="column in answerColumns"
              :key="column.key"
              min-width="172"
              align="center"
            >
              <template #header>
                <div class="column-head">
                  <span>{{ column.label }}</span>
                  <small>{{ column.subLabel }}</small>
                </div>
              </template>
              <template #default="{ row }">
                <div
                  class="rank-drop-zone"
                  :class="{
                    'is-dragging-source': dragState?.columnKey === column.key && dragState?.rank === row.rank,
                    'is-drag-over': dragOverState?.columnKey === column.key && dragOverState?.rank === row.rank,
                  }"
                  @dragenter.prevent="markDragOver(row.rank, column.key)"
                  @dragover.prevent
                  @drop.prevent.stop="dropOnRank(row.rank, column.key, $event)"
                >
                  <button
                    class="drag-handle"
                    :class="{ 'is-empty': !itemFor(row.rank, column.key) }"
                    :draggable="!!itemFor(row.rank, column.key)"
                    type="button"
                    title="拖动调整顺序"
                    @dragstart="startDrag(row.rank, column.key, $event)"
                    @dragend="finishDrag"
                  >
                    ≡
                  </button>
                  <el-select
                    :model-value="itemFor(row.rank, column.key)"
                    :data-testid="`task-score-item-select-${column.key}-${row.rank}`"
                    filterable
                    clearable
                    placeholder="选择物品"
                    size="small"
                    @update:model-value="(value: string | undefined) => setItem(row.rank, column.key, value || undefined)"
                  >
                    <el-option
                      v-for="item in selectedTask.items"
                      :key="item.key"
                      :label="item.label"
                      :value="item.key"
                      :disabled="isItemSelectedElsewhere(item.key, column.key, row.rank)"
                    />
                  </el-select>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="6">
        <el-card class="side-card" shadow="never">
          <template #header>
            <div class="side-title">
              <el-icon><Select /></el-icon>
              <strong>小组成员</strong>
            </div>
          </template>
          <div v-if="activeMembers.length === 0" class="empty-text">选择小组后显示成员</div>
          <div v-for="(member, index) in activeMembers" :key="member.id" class="member-row">
            <div class="member-index">{{ index + 1 }}</div>
            <div>
              <div class="member-name">{{ member.user_name || member.user_id }}</div>
              <div class="member-meta">{{ member.user_id }} · {{ member.role }}</div>
            </div>
          </div>
        </el-card>

        <el-card class="side-card" shadow="never">
          <template #header>
            <strong>计算预览</strong>
          </template>
          <div v-if="scoreSummaries.length === 0" class="empty-text">
            填完排名后点击“校验并计算”。
          </div>
          <div v-else class="summary-list">
            <div v-for="item in scoreSummaries" :key="item.label" class="summary-row">
              <span>{{ item.label }}</span>
              <strong>{{ item.score }}</strong>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.task-score-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.page-header h1 {
  margin: 0;
  color: #172033;
  font-size: 24px;
  font-weight: 700;
}

.page-header p {
  margin: 6px 0 0;
  color: #627089;
  font-size: 14px;
}

.control-card,
.entry-card,
.side-card {
  border: 1px solid #e3e9f2;
  border-radius: 8px;
}

.control-form {
  display: grid;
  grid-template-columns: minmax(280px, 1.4fr) minmax(160px, 0.6fr) minmax(260px, 1fr);
  gap: 12px 18px;
}

.control-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.control-form :deep(.el-select) {
  width: 100%;
}

.content-row {
  align-items: flex-start;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-header span {
  display: block;
  margin-top: 4px;
  color: #748197;
  font-size: 13px;
  font-weight: 500;
}

.header-actions {
  display: flex;
  gap: 8px;
  white-space: nowrap;
}

.member-alert {
  margin-bottom: 12px;
}

.score-entry-table :deep(.el-input-number) {
  width: 116px;
}

.score-entry-table :deep(.el-select) {
  width: 100%;
}

.rank-drop-zone {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 2px;
  border-radius: 8px;
  transition: none;
}

.rank-drop-zone.is-dragging-source {
  opacity: 0.55;
}

.rank-drop-zone.is-drag-over {
  background: #eff6ff;
  box-shadow: inset 0 0 0 2px #60a5fa;
}

.rank-drop-zone.is-drag-over::before {
  position: absolute;
  top: -6px;
  right: 8px;
  left: 8px;
  height: 3px;
  border-radius: 999px;
  background: #2563eb;
  content: "";
}

.drag-handle {
  display: grid;
  flex: 0 0 auto;
  width: 24px;
  height: 30px;
  place-items: center;
  border: 0;
  border-radius: 6px;
  background: #edf3f8;
  color: #5c6b82;
  cursor: grab;
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-handle.is-empty {
  color: #c0cad8;
  cursor: default;
}

.score-entry-table :deep(.el-table__cell) {
  padding: 10px 8px;
}

.score-entry-table :deep(.rank-cell .cell) {
  white-space: nowrap;
  word-break: keep-all;
}

.column-head {
  display: flex;
  min-height: 40px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  line-height: 1.2;
}

.column-head small {
  color: #8793a7;
  font-size: 12px;
  font-weight: 500;
}

.side-card + .side-card {
  margin-top: 16px;
}

.side-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.empty-text {
  color: #8793a7;
  font-size: 14px;
}

.member-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px solid #edf1f6;
}

.member-row:last-child {
  border-bottom: 0;
}

.member-index {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 50%;
  background: #eef6f0;
  color: #166534;
  font-weight: 600;
}

.member-name {
  color: #1f2a3d;
  font-size: 14px;
  font-weight: 700;
}

.member-meta {
  margin-top: 2px;
  color: #8190a5;
  font-size: 12px;
}

.summary-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.summary-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #edf1f6;
  color: #405069;
  font-size: 14px;
}

.summary-row:last-child {
  border-bottom: 0;
}

.summary-row strong {
  color: #172033;
  font-size: 16px;
}

@media (max-width: 1100px) {
  .control-form {
    grid-template-columns: 1fr;
  }

  .card-header,
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
