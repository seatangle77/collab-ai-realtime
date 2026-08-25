<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import {
  getCoiAgreement,
  saveFinalCoiCodes,
  type AgreementUnit,
  type CoiCategory,
} from '../../api/admin/coi-units'
import type { AdminChatSession, AdminGroup } from '../../types/admin'
import { coiCodesDraftKey } from '../../utils/coiDraftKeys'

interface AgreementItem {
  unitId: string
  orderIndex: number
  content: string
  startTime: number | null
  coderA: CoiCategory[]
  coderB: CoiCategory[]
  finalCategories: CoiCategory[]
}

interface LocalDraft {
  codes: { unitId: string; categories: CoiCategory[] }[]
  savedAt: string
}

const COI_LABELS: Record<CoiCategory, { label: string; color: string; bg: string }> = {
  TE: { label: '触发', color: '#b45309', bg: '#fef9ee' },
  EX: { label: '探索', color: '#1d4ed8', bg: '#f0f5ff' },
  IN: { label: '整合', color: '#15803d', bg: '#f0fdf4' },
  RE: { label: '解决', color: '#b91c1c', bg: '#fff5f5' },
  OTHER: { label: '其他（非认知）', color: '#4b5563', bg: '#f3f4f6' },
}
const COI_KEYS = Object.keys(COI_LABELS) as CoiCategory[]

const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const selectedGroupId = ref('')
const selectedSessionId = ref('')
const loadingGroups = ref(false)
const loadingSessions = ref(false)
const loadingItems = ref(false)
const saving = ref(false)
const items = ref<AgreementItem[]>([])
const hasDraft = ref(false)
const draftInfo = ref<{ savedAt: string; count: number } | null>(null)

const totalCount = computed(() => items.value.length)
const finalCount = computed(() => items.value.filter(item => item.finalCategories.length > 0).length)
const agreedCount = computed(() => items.value.filter(item => isAgreed(item)).length)
const disagreementCount = computed(() => items.value.filter(item => item.coderA.length && item.coderB.length && !isAgreed(item)).length)
const progressPct = computed(() =>
  totalCount.value > 0 ? Math.round((finalCount.value / totalCount.value) * 100) : 0,
)

onMounted(async () => {
  loadingGroups.value = true
  try {
    const res = await listAdminGroups({ page_size: 200 })
    groups.value = res.items
  } catch (e: any) {
    ElMessage.error(e?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
})

function resetItems() {
  items.value = []
  hasDraft.value = false
  draftInfo.value = null
}

async function onGroupChange() {
  selectedSessionId.value = ''
  sessions.value = []
  resetItems()
  if (!selectedGroupId.value) return
  loadingSessions.value = true
  try {
    const res = await listAdminChatSessions({ group_id: selectedGroupId.value, page_size: 200 })
    sessions.value = res.items
    if (res.items.length > 0) {
      selectedSessionId.value = res.items[0]!.id
      await loadAgreement()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载会话失败')
  } finally {
    loadingSessions.value = false
  }
}

async function onSessionChange() {
  resetItems()
  await loadAgreement()
}

function draftKey() {
  return selectedSessionId.value ? coiCodesDraftKey(selectedSessionId.value, 'final') : ''
}

function checkDraft() {
  const key = draftKey()
  if (!key) return
  const raw = localStorage.getItem(key)
  if (!raw) { hasDraft.value = false; draftInfo.value = null; return }
  try {
    const draft = JSON.parse(raw) as LocalDraft
    hasDraft.value = true
    draftInfo.value = { savedAt: draft.savedAt, count: draft.codes.length }
  } catch {
    hasDraft.value = false
    draftInfo.value = null
  }
}

function saveDraft() {
  const key = draftKey()
  if (!key || items.value.length === 0) return
  const codes = items.value
    .filter(item => item.finalCategories.length > 0)
    .map(item => ({ unitId: item.unitId, categories: [...item.finalCategories] }))
  const draft: LocalDraft = {
    codes,
    savedAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  }
  localStorage.setItem(key, JSON.stringify(draft))
  hasDraft.value = true
  draftInfo.value = { savedAt: draft.savedAt, count: draft.codes.length }
  ElMessage.success('最终协商草稿已保存到本地')
}

function restoreDraft() {
  const key = draftKey()
  if (!key) return
  const raw = localStorage.getItem(key)
  if (!raw) return
  try {
    const draft = JSON.parse(raw) as LocalDraft
    const categoriesByUnit = new Map(draft.codes.map(code => [code.unitId, code.categories]))
    items.value = items.value.map(item => ({
      ...item,
      finalCategories: categoriesByUnit.get(item.unitId) ?? [],
    }))
    ElMessage.success(`已恢复最终协商草稿：${draft.codes.length} 条`)
  } catch {
    ElMessage.error('草稿数据损坏，无法恢复')
  }
}

function clearDraft() {
  const key = draftKey()
  if (!key) return
  localStorage.removeItem(key)
  hasDraft.value = false
  draftInfo.value = null
}

function toAgreementItem(row: AgreementUnit): AgreementItem {
  return {
    unitId: row.unit.id,
    orderIndex: row.unit.order_index,
    content: row.unit.content,
    startTime: row.unit.start_time,
    coderA: [...(row.coder_a?.coi_categories ?? [])],
    coderB: [...(row.coder_b?.coi_categories ?? [])],
    finalCategories: [...(row.final?.coi_categories ?? [])],
  }
}

async function loadAgreement() {
  if (!selectedSessionId.value) return
  loadingItems.value = true
  try {
    const res = await getCoiAgreement(selectedSessionId.value)
    items.value = res.map(toAgreementItem)
    checkDraft()
    if (res.length === 0) {
      ElMessage.info('该会话暂无观点单元，请先完成「CoI 观点整理」')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载协商数据失败')
  } finally {
    loadingItems.value = false
  }
}

function fmt(s: number | null): string {
  if (s == null || Number.isNaN(s)) return '--'
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1).padStart(4, '0')
  return `${m}:${sec}`
}

function isAgreed(item: AgreementItem): boolean {
  return item.coderA.length > 0
    && item.coderB.length > 0
    && item.coderA.length === item.coderB.length
    && item.coderA.every(category => item.coderB.includes(category))
}

function isPartiallyAgreed(item: AgreementItem): boolean {
  return !isAgreed(item) && item.coderA.some(category => item.coderB.includes(category))
}

function statusType(item: AgreementItem): 'success' | 'warning' | 'info' {
  if (isAgreed(item)) return 'success'
  if (item.coderA.length && item.coderB.length) return 'warning'
  return 'info'
}

function statusText(item: AgreementItem): string {
  if (isAgreed(item)) return '一致'
  if (isPartiallyAgreed(item)) return '部分一致'
  if (item.coderA.length && item.coderB.length) return '不一致'
  return '未完成 A/B'
}

function fillAgreedFinals() {
  let filled = 0
  for (const item of items.value) {
    if (!item.finalCategories.length && isAgreed(item)) {
      item.finalCategories = [...item.coderA]
      filled += 1
    }
  }
  ElMessage.success(`已填入 ${filled} 条一致编码`)
}

function setFinalCategory(index: number, cat: CoiCategory) {
  const item = items.value[index]
  if (!item) return
  if (cat === 'OTHER') {
    item.finalCategories = item.finalCategories.includes('OTHER') ? [] : ['OTHER']
    return
  }
  const current = item.finalCategories.filter(category => category !== 'OTHER')
  item.finalCategories = current.includes(cat)
    ? current.filter(category => category !== cat)
    : COI_KEYS.filter(category => [...current, cat].includes(category))
}

function tagLabel(cat: CoiCategory): string {
  return `${cat} ${COI_LABELS[cat].label}`
}

async function handleSave() {
  if (!selectedSessionId.value) { ElMessage.warning('请先选择会话'); return }
  if (finalCount.value === 0) { ElMessage.warning('还没有最终编码'); return }
  const missing = totalCount.value - finalCount.value
  try {
    await ElMessageBox.confirm(
      `将保存最终协商编码：已完成 ${finalCount.value} 条，未完成 ${missing} 条不会写入数据库。确认保存？`,
      '确认保存最终编码',
      { type: 'warning', confirmButtonText: '保存', cancelButtonText: '取消' },
    )
  } catch { return }

  saving.value = true
  try {
    const codes = items.value
      .filter(item => item.finalCategories.length > 0)
      .map(item => ({
        unit_id: item.unitId,
        coi_categories: item.finalCategories,
        coded_by: '最终协商',
      }))
    const res = await saveFinalCoiCodes(selectedSessionId.value, codes)
    clearDraft()
    ElMessage.success(`最终编码已保存：${res.saved} 条`)
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">CoI 最终协商</h2>
      <span class="header-desc">查看 A/B 独立编码差异，并保存最终 CoI 编码</span>
    </div>

    <el-card shadow="never" class="control-card">
      <div class="control-bar">
        <div class="control-left">
          <div class="control-item">
            <span class="control-label">群组</span>
            <el-select
              v-model="selectedGroupId"
              placeholder="选择群组"
              style="width: 200px"
              :loading="loadingGroups"
              filterable
              @change="onGroupChange"
            >
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </div>

          <div v-if="sessions.length > 0" class="control-item">
            <span class="control-label">会话</span>
            <el-select
              v-model="selectedSessionId"
              style="width: 240px"
              :loading="loadingSessions"
              filterable
              @change="onSessionChange"
            >
              <el-option v-for="s in sessions" :key="s.id" :label="s.session_title" :value="s.id" />
            </el-select>
          </div>
        </div>

        <div class="control-right">
          <template v-if="totalCount > 0">
            <el-progress
              :percentage="progressPct"
              :stroke-width="8"
              style="width: 120px"
              :color="progressPct === 100 ? '#67c23a' : '#409eff'"
            />
            <span class="progress-text">{{ finalCount }} / {{ totalCount }}</span>
          </template>
          <el-button
            :disabled="!selectedSessionId"
            :loading="loadingItems"
            @click="loadAgreement"
          >
            加载协商数据
          </el-button>
          <template v-if="items.length > 0">
            <el-button @click="fillAgreedFinals">填入一致项</el-button>
            <el-button @click="saveDraft">保存草稿</el-button>
            <el-button type="primary" :loading="saving" @click="handleSave">保存最终编码</el-button>
          </template>
        </div>
      </div>
    </el-card>

    <el-alert
      v-if="hasDraft && items.length > 0 && draftInfo"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #default>
        <span>发现最终协商草稿：已定 {{ draftInfo.count }} 条，保存于 {{ draftInfo.savedAt }}</span>
        <el-button size="small" type="primary" style="margin-left:12px" @click="restoreDraft">恢复草稿</el-button>
        <el-button size="small" style="margin-left:6px" @click="clearDraft">丢弃</el-button>
      </template>
    </el-alert>

    <el-card v-if="items.length > 0" shadow="never" v-loading="loadingItems">
      <template #header>
        <div class="list-header">
          <span class="list-title">协商列表</span>
          <div class="list-tags">
            <el-tag size="small" type="success">一致 {{ agreedCount }}</el-tag>
            <el-tag size="small" type="warning">不一致 {{ disagreementCount }}</el-tag>
            <el-tag size="small" type="info">最终已定 {{ finalCount }}</el-tag>
          </div>
        </div>
      </template>

      <div class="agreement-list">
        <div
          v-for="(item, i) in items"
          :key="item.unitId"
          class="agreement-row"
          :class="{ 'is-final': item.finalCategories.length > 0, 'is-disagreement': item.coderA.length && item.coderB.length && !isAgreed(item) }"
        >
          <div class="unit-top">
            <span class="unit-num">{{ item.orderIndex }}</span>
            <span class="unit-time">{{ fmt(item.startTime) }}</span>
            <span class="unit-content">{{ item.content }}</span>
          </div>

          <div class="code-grid">
            <div class="code-cell">
              <span class="code-label">研究员 A</span>
              <template v-if="item.coderA.length">
                <el-tag v-for="cat in item.coderA" :key="cat" size="small" :color="COI_LABELS[cat].bg" effect="plain">
                  {{ tagLabel(cat) }}
                </el-tag>
              </template>
              <el-tag v-else size="small" type="info">未编码</el-tag>
            </div>
            <div class="code-cell">
              <span class="code-label">研究员 B</span>
              <template v-if="item.coderB.length">
                <el-tag v-for="cat in item.coderB" :key="cat" size="small" :color="COI_LABELS[cat].bg" effect="plain">
                  {{ tagLabel(cat) }}
                </el-tag>
              </template>
              <el-tag v-else size="small" type="info">未编码</el-tag>
            </div>
            <div class="code-cell">
              <span class="code-label">状态</span>
              <el-tag size="small" :type="statusType(item)">{{ statusText(item) }}</el-tag>
            </div>
          </div>

          <div class="final-row">
            <span class="final-label">最终编码</span>
            <div class="category-buttons">
              <button
                v-for="cat in COI_KEYS"
                :key="cat"
                class="cat-btn"
                :class="{ 'is-active': item.finalCategories.includes(cat) }"
                :style="item.finalCategories.includes(cat)
                  ? { background: COI_LABELS[cat].color, borderColor: COI_LABELS[cat].color, color: '#fff' }
                  : { borderColor: COI_LABELS[cat].color, color: COI_LABELS[cat].color, background: COI_LABELS[cat].bg }"
                @click="setFinalCategory(i, cat)"
              >{{ cat }} {{ COI_LABELS[cat].label }}</button>
              <button
                v-if="item.finalCategories.length"
                class="clear-btn"
                @click="item.finalCategories = []"
              >清除</button>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <el-card v-else shadow="never" class="empty-card" v-loading="loadingItems">
      <el-empty
        :image-size="120"
        :description="selectedSessionId ? '该会话暂无观点单元，请先完成 CoI 观点整理' : '请先选择群组'"
      />
    </el-card>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.header-desc { font-size: 13px; color: #909399; }
.control-card :deep(.el-card__body) { padding: 14px 20px; }
.control-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.control-left { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.control-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.control-item { display: flex; align-items: center; gap: 8px; }
.control-label { font-size: 14px; color: #606266; white-space: nowrap; }
.progress-text { font-size: 14px; font-weight: 500; color: #303133; white-space: nowrap; }
.list-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }
.list-title { font-size: 15px; font-weight: 600; color: #303133; }
.list-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.agreement-list { display: flex; flex-direction: column; gap: 8px; max-height: calc(100vh - 310px); overflow-y: auto; }
.agreement-row {
  padding: 12px;
  border: 1.5px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
}
.agreement-row.is-final { border-left: 3px solid #67c23a; }
.agreement-row.is-disagreement { background: #fffaf0; border-color: #f3d19e; }
.unit-top { display: flex; align-items: baseline; gap: 8px; margin-bottom: 10px; }
.unit-num { font-size: 11px; color: #c0c4cc; font-weight: 600; width: 24px; text-align: right; flex-shrink: 0; }
.unit-time { font-size: 12px; color: #909399; width: 40px; flex-shrink: 0; }
.unit-content { font-size: 15px; color: #303133; line-height: 1.7; word-break: break-word; }
.code-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-left: 72px; margin-bottom: 10px; }
.code-cell { display: flex; align-items: center; gap: 8px; min-width: 0; }
.code-label, .final-label { font-size: 14px; color: #606266; white-space: nowrap; }
.final-row { display: flex; align-items: center; gap: 12px; margin-left: 72px; flex-wrap: wrap; }
.category-buttons { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cat-btn {
  padding: 3px 12px;
  border: 1.5px solid;
  border-radius: 5px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.12s;
  line-height: 1.6;
}
.cat-btn:hover { opacity: 0.8; }
.cat-btn.is-active { box-shadow: 0 2px 6px rgba(0,0,0,0.15); }
.clear-btn {
  padding: 3px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 5px;
  font-size: 13px;
  color: #909399;
  background: #fff;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.12s;
}
.clear-btn:hover { color: #f56c6c; border-color: #f56c6c; }
.empty-card { min-height: 320px; display: flex; align-items: center; justify-content: center; }
@media (max-width: 820px) {
  .code-grid { grid-template-columns: 1fr; margin-left: 0; }
  .final-row { margin-left: 0; }
  .unit-top { display: grid; grid-template-columns: 28px 44px minmax(0, 1fr); }
}
</style>
