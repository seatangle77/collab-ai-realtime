<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import {
  getCoiCodes,
  mergeCoiUnitWithNext,
  saveCoiCodes,
  splitCoiUnit,
  type CoiCategory,
  type CoiCoderRole,
  type UnitWithCode,
} from '../../api/admin/coi-units'
import type { AdminChatSession, AdminGroup } from '../../types/admin'
import { coiCodesDraftKey, coiReviewStarsKey } from '../../utils/coiDraftKeys'

type IndependentCoderRole = 'coder_a' | 'coder_b' | 'coder_c'

interface CodingItem {
  unitId: string
  orderIndex: number
  content: string
  startTime: number | null
  categories: CoiCategory[]
  starred: boolean
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
const CODER_OPTIONS: { label: string; value: IndependentCoderRole }[] = [
  { label: '研究员 A', value: 'coder_a' },
  { label: '研究员 B', value: 'coder_b' },
  { label: '研究员 C（AI 辅助）', value: 'coder_c' },
]

const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const selectedGroupId = ref('')
const selectedSessionId = ref('')
const coderRole = ref<IndependentCoderRole>('coder_a')
const loadingGroups = ref(false)
const loadingSessions = ref(false)
const loadingItems = ref(false)
const saving = ref(false)
const mutatingStructure = ref(false)
const items = ref<CodingItem[]>([])
const focusedIndex = ref(0)
const hasDraft = ref(false)
const draftInfo = ref<{ savedAt: string; count: number } | null>(null)
const showStarredOnly = ref(false)
const splitDialogVisible = ref(false)
const splitTargetIndex = ref<number | null>(null)
const splitContent = ref('')
const splitTextareaRef = ref<HTMLTextAreaElement | null>(null)

const totalCount = computed(() => items.value.length)
const codedCount = computed(() => items.value.filter(item => item.categories.length > 0).length)
const multiCodedCount = computed(() => items.value.filter(item => item.categories.length > 1).length)
const starredCount = computed(() => items.value.filter(item => item.starred).length)
const visibleItems = computed(() => items.value
  .map((item, index) => ({ item, index }))
  .filter(({ item }) => !showStarredOnly.value || item.starred))
const progressPct = computed(() =>
  totalCount.value > 0 ? Math.round((codedCount.value / totalCount.value) * 100) : 0,
)
const coderLabel = computed(() =>
  CODER_OPTIONS.find(option => option.value === coderRole.value)?.label ?? '研究员 A',
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
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => window.removeEventListener('keydown', handleKeydown))

function resetItems() {
  items.value = []
  focusedIndex.value = 0
  hasDraft.value = false
  draftInfo.value = null
  showStarredOnly.value = false
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
      await loadCodes()
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载会话失败')
  } finally {
    loadingSessions.value = false
  }
}

async function onSessionChange() {
  resetItems()
  await loadCodes()
}

async function onCoderRoleChange() {
  resetItems()
  await loadCodes()
}

function draftKey() {
  return selectedSessionId.value ? coiCodesDraftKey(selectedSessionId.value, coderRole.value) : ''
}

function reviewStarsKey() {
  return selectedSessionId.value ? coiReviewStarsKey(selectedSessionId.value, coderRole.value) : ''
}

function readReviewStars(): Set<string> {
  const key = reviewStarsKey()
  if (!key) return new Set()
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? '[]')
    return new Set(Array.isArray(value) ? value.filter(id => typeof id === 'string') : [])
  } catch {
    return new Set()
  }
}

function persistReviewStars() {
  const key = reviewStarsKey()
  if (!key) return
  localStorage.setItem(key, JSON.stringify(items.value.filter(item => item.starred).map(item => item.unitId)))
}

function toggleStar(index: number) {
  const item = items.value[index]
  if (!item) return
  item.starred = !item.starred
  persistReviewStars()
  if (showStarredOnly.value && !item.starred) {
    nextTick(() => {
      focusedIndex.value = visibleItems.value[0]?.index ?? 0
      scrollToFocused()
    })
  }
}

function toggleStarredFilter() {
  showStarredOnly.value = !showStarredOnly.value
  focusedIndex.value = visibleItems.value[0]?.index ?? 0
  nextTick(scrollToFocused)
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
    .filter(item => item.categories.length > 0)
    .map(item => ({ unitId: item.unitId, categories: [...item.categories] }))
  const draft: LocalDraft = {
    codes,
    savedAt: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  }
  localStorage.setItem(key, JSON.stringify(draft))
  hasDraft.value = true
  draftInfo.value = { savedAt: draft.savedAt, count: draft.codes.length }
  ElMessage.success('草稿已保存到本地')
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
      categories: categoriesByUnit.get(item.unitId) ?? [],
    }))
    focusedIndex.value = 0
    ElMessage.success(`已恢复 ${coderLabel.value} 草稿：${draft.codes.length} 条编码`)
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

function toCodingItem(row: UnitWithCode, starredUnitIds: Set<string>): CodingItem {
  return {
    unitId: row.unit.id,
    orderIndex: row.unit.order_index,
    content: row.unit.content,
    startTime: row.unit.start_time,
    categories: [...(row.code?.coi_categories ?? [])],
    starred: starredUnitIds.has(row.unit.id),
  }
}

async function loadCodes() {
  if (!selectedSessionId.value) return
  loadingItems.value = true
  try {
    const res = await getCoiCodes(selectedSessionId.value, coderRole.value)
    const starredUnitIds = readReviewStars()
    items.value = res.map(row => toCodingItem(row, starredUnitIds))
    // Drop stars that referenced units replaced during upstream preparation.
    persistReviewStars()
    focusedIndex.value = 0
    checkDraft()
    if (res.length === 0) {
      ElMessage.info('该会话暂无观点单元，请先完成「CoI 观点整理」')
    } else {
      nextTick(scrollToFocused)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载编码数据失败')
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

function scrollToFocused() {
  document.getElementById(`coi-code-${focusedIndex.value}`)?.scrollIntoView({ behavior: 'auto', block: 'nearest' })
}

function setCategory(index: number, cat: CoiCategory) {
  const item = items.value[index]
  if (!item) return
  if (cat === 'OTHER') {
    item.categories = item.categories.includes('OTHER') ? [] : ['OTHER']
    return
  }
  const current: CoiCategory[] = item.categories.filter(category => category !== 'OTHER')
  item.categories = current.includes(cat)
    ? current.filter(category => category !== cat)
    : COI_KEYS.filter(category => [...current, cat].includes(category))
}

function advance() {
  const position = visibleItems.value.findIndex(({ index }) => index === focusedIndex.value)
  const next = visibleItems.value[position + 1]
  if (next) {
    focusedIndex.value = next.index
    nextTick(scrollToFocused)
  }
}

function moveFocus(offset: -1 | 1) {
  const position = visibleItems.value.findIndex(({ index }) => index === focusedIndex.value)
  const fallbackPosition = offset > 0 ? 0 : visibleItems.value.length - 1
  const target = visibleItems.value[position >= 0 ? position + offset : fallbackPosition]
  if (!target) return
  focusedIndex.value = target.index
  nextTick(scrollToFocused)
}

function codeAndAdvance(cat: CoiCategory) {
  const item = items.value[focusedIndex.value]
  if (!item) return
  setCategory(focusedIndex.value, cat)
}

function buildCodePayload() {
  return items.value
    .filter(item => item.categories.length > 0)
    .map(item => ({
      unit_id: item.unitId,
      coi_categories: item.categories,
      coded_by: coderLabel.value,
    }))
}

async function saveCurrentCodesBeforeMutation() {
  if (!selectedSessionId.value) throw new Error('请先选择会话')
  await saveCoiCodes(
    selectedSessionId.value,
    coderRole.value as CoiCoderRole,
    buildCodePayload(),
  )
  clearDraft()
}

function openSplitDialog(index: number) {
  if (coderRole.value !== 'coder_a') return
  const item = items.value[index]
  if (!item) return
  splitTargetIndex.value = index
  splitContent.value = item.content
  splitDialogVisible.value = true
  nextTick(() => {
    const textarea = splitTextareaRef.value
    if (!textarea) return
    const midpoint = Math.floor(item.content.length / 2)
    textarea.focus()
    textarea.setSelectionRange(midpoint, midpoint)
  })
}

function closeSplitDialog() {
  if (mutatingStructure.value) return
  splitDialogVisible.value = false
  splitTargetIndex.value = null
  splitContent.value = ''
}

async function focusMutatedUnits(unitIds: string[]) {
  showStarredOnly.value = false
  await loadCodes()
  const idSet = new Set(unitIds)
  for (const item of items.value) {
    if (idSet.has(item.unitId)) item.starred = true
  }
  persistReviewStars()
  const firstIndex = items.value.findIndex(item => idSet.has(item.unitId))
  focusedIndex.value = firstIndex >= 0 ? firstIndex : 0
  nextTick(scrollToFocused)
}

async function confirmSplitAtCursor() {
  if (coderRole.value !== 'coder_a' || splitTargetIndex.value === null || !selectedSessionId.value) return
  const textarea = splitTextareaRef.value
  const item = items.value[splitTargetIndex.value]
  if (!textarea || !item) return
  const position = textarea.selectionStart
  const firstContent = splitContent.value.slice(0, position).trim()
  const secondContent = splitContent.value.slice(position).trim()
  if (!firstContent || !secondContent) {
    ElMessage.warning('请把光标放在观点文字中间，再点击确认拆分')
    return
  }

  mutatingStructure.value = true
  try {
    await saveCurrentCodesBeforeMutation()
    const res = await splitCoiUnit(selectedSessionId.value, item.unitId, firstContent, secondContent)
    splitDialogVisible.value = false
    splitTargetIndex.value = null
    splitContent.value = ''
    await focusMutatedUnits(res.units.map(unit => unit.id))
    ElMessage.success(`已拆分为 2 条；${res.invalidated_codes} 条相关编码需重新确认`)
  } catch (e: any) {
    ElMessage.error(e?.message || '拆分失败，请重新加载后再试')
  } finally {
    mutatingStructure.value = false
  }
}

async function mergeWithNext(index: number) {
  if (coderRole.value !== 'coder_a' || !selectedSessionId.value) return
  const current = items.value[index]
  const following = items.value[index + 1]
  if (!current || !following) return
  try {
    await ElMessageBox.confirm(
      `将观点 ${current.orderIndex} 与 ${following.orderIndex} 合并。两条观点现有的 A/B/C/final 编码会失效，其他编码不受影响。确认合并？`,
      '确认合并观点',
      { type: 'warning', confirmButtonText: '合并', cancelButtonText: '取消' },
    )
  } catch { return }

  mutatingStructure.value = true
  try {
    await saveCurrentCodesBeforeMutation()
    const res = await mergeCoiUnitWithNext(selectedSessionId.value, current.unitId)
    await focusMutatedUnits(res.units.map(unit => unit.id))
    ElMessage.success(`已合并观点；${res.invalidated_codes} 条相关编码需重新确认`)
  } catch (e: any) {
    ElMessage.error(e?.message || '合并失败，请重新加载后再试')
  } finally {
    mutatingStructure.value = false
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (!items.value.length) return
  const tag = (e.target as HTMLElement).tagName
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return
  switch (e.key) {
    case '1': e.preventDefault(); codeAndAdvance('TE'); break
    case '2': e.preventDefault(); codeAndAdvance('EX'); break
    case '3': e.preventDefault(); codeAndAdvance('IN'); break
    case '4': e.preventDefault(); codeAndAdvance('RE'); break
    case '5': e.preventDefault(); codeAndAdvance('OTHER'); break
    case '0': e.preventDefault(); advance(); break
    case 's':
    case 'S': e.preventDefault(); toggleStar(focusedIndex.value); break
    case 'ArrowDown':
      e.preventDefault()
      moveFocus(1)
      break
    case 'ArrowUp':
      e.preventDefault()
      moveFocus(-1)
      break
  }
}

async function handleSave() {
  if (!selectedSessionId.value) { ElMessage.warning('请先选择会话'); return }
  if (codedCount.value === 0) { ElMessage.warning('还没有已编码的观点单元'); return }
  const uncoded = totalCount.value - codedCount.value
  try {
    await ElMessageBox.confirm(
      `将保存 ${coderLabel.value} 的编码结果：已编码 ${codedCount.value} 条，未编码 ${uncoded} 条不会写入数据库。确认保存？`,
      '确认保存独立编码',
      { type: 'warning', confirmButtonText: '保存', cancelButtonText: '取消' },
    )
  } catch { return }

  saving.value = true
  try {
    const res = await saveCoiCodes(
      selectedSessionId.value,
      coderRole.value as CoiCoderRole,
      buildCodePayload(),
    )
    clearDraft()
    ElMessage.success(`${coderLabel.value} 编码已保存：${res.saved} 条`)
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
      <h2 class="page-title">CoI 独立编码</h2>
      <span class="header-desc">
        键盘：<kbd>1</kbd>TE <kbd>2</kbd>EX <kbd>3</kbd>IN <kbd>4</kbd>RE <kbd>5</kbd>OTHER <kbd>S</kbd>星标 <kbd>0</kbd>跳过 <kbd>↑↓</kbd>切换焦点行
      </span>
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

          <div class="control-item">
            <span class="control-label">编码身份</span>
            <el-select
              v-model="coderRole"
              style="width: 140px"
              @change="onCoderRoleChange"
            >
              <el-option v-for="option in CODER_OPTIONS" :key="option.value" :label="option.label" :value="option.value" />
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
            <span class="progress-text">当前已编码 {{ codedCount }} / {{ totalCount }}</span>
            <el-button
              :type="showStarredOnly ? 'warning' : 'default'"
              :disabled="starredCount === 0 && !showStarredOnly"
              @click="toggleStarredFilter"
            >
              {{ showStarredOnly ? '显示全部' : `只看星标（${starredCount}）` }}
            </el-button>
          </template>
          <el-button
            :disabled="!selectedSessionId"
            :loading="loadingItems"
            @click="loadCodes"
          >
            加载编码
          </el-button>
          <template v-if="items.length > 0">
            <el-button @click="saveDraft">保存草稿</el-button>
            <el-button type="primary" :loading="saving" @click="handleSave">保存编码结果</el-button>
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
        <span>发现 {{ coderLabel }} 草稿：已编码 {{ draftInfo.count }} 条，保存于 {{ draftInfo.savedAt }}</span>
        <el-button size="small" type="primary" style="margin-left:12px" @click="restoreDraft">恢复草稿</el-button>
        <el-button size="small" style="margin-left:6px" @click="clearDraft">丢弃</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="coderRole === 'coder_a' && items.length > 0"
      type="info"
      :closable="false"
      show-icon
      title="研究员 A 可直接拆分或合并观点；仅受影响观点的 A/B/C/final 编码需要重新确认，其他编码会保留。"
    />

    <el-card v-if="items.length > 0" shadow="never" v-loading="loadingItems">
      <template #header>
        <div class="list-header">
          <span class="list-title">观点单元列表</span>
          <div class="list-tags">
            <el-tag size="small" type="success">已编 {{ codedCount }}</el-tag>
            <el-tag size="small" type="info">未编 {{ totalCount - codedCount }}</el-tag>
            <el-tag v-if="multiCodedCount > 0" size="small" type="warning">多编码 {{ multiCodedCount }}</el-tag>
            <el-tag size="small" type="warning">星标 {{ starredCount }}</el-tag>
          </div>
        </div>
      </template>

      <div class="coding-list">
        <div
          v-for="entry in visibleItems"
          :id="`coi-code-${entry.index}`"
          :key="entry.item.unitId"
          class="coding-row"
          :class="{
            'is-focused': entry.index === focusedIndex,
            'is-coded': entry.item.categories.length > 0,
            'is-multi-coded': entry.item.categories.length > 1,
            'is-starred': entry.item.starred,
          }"
          @click="focusedIndex = entry.index"
        >
          <div class="unit-top">
            <span class="unit-num">{{ entry.item.orderIndex }}</span>
            <span class="unit-time">{{ fmt(entry.item.startTime) }}</span>
            <span class="unit-content">{{ entry.item.content }}</span>
            <el-tag v-if="entry.item.categories.length > 1" size="small" type="warning" effect="dark">多编码</el-tag>
            <button
              class="star-btn"
              :class="{ 'is-active': entry.item.starred }"
              :title="entry.item.starred ? '取消待复核星标' : '标记为待复核'"
              :aria-label="entry.item.starred ? '取消待复核星标' : '标记为待复核'"
              @click.stop="toggleStar(entry.index)"
            >{{ entry.item.starred ? '★' : '☆' }}</button>
          </div>
          <div class="unit-bottom">
            <div class="category-buttons">
              <button
                v-for="cat in COI_KEYS"
                :key="cat"
                class="cat-btn"
                :class="{ 'is-active': entry.item.categories.includes(cat) }"
                :style="entry.item.categories.includes(cat)
                  ? { background: COI_LABELS[cat].color, borderColor: COI_LABELS[cat].color, color: '#fff' }
                  : { borderColor: COI_LABELS[cat].color, color: COI_LABELS[cat].color, background: COI_LABELS[cat].bg }"
                @click.stop="setCategory(entry.index, cat)"
              >{{ cat }} {{ COI_LABELS[cat].label }}</button>
              <button
                v-if="entry.item.categories.length"
                class="clear-btn"
                @click.stop="entry.item.categories = []"
              >清除</button>
            </div>
            <div v-if="coderRole === 'coder_a'" class="structure-actions">
              <button
                class="structure-btn"
                :disabled="mutatingStructure"
                @click.stop="openSplitDialog(entry.index)"
              >拆分</button>
              <button
                v-if="entry.index < items.length - 1"
                class="structure-btn"
                :disabled="mutatingStructure"
                @click.stop="mergeWithNext(entry.index)"
              >与下一条合并</button>
            </div>
          </div>
        </div>
        <el-empty
          v-if="showStarredOnly && visibleItems.length === 0"
          :image-size="80"
          description="当前没有待复核的星标项"
        />
      </div>
    </el-card>

    <el-card v-else shadow="never" class="empty-card" v-loading="loadingItems">
      <el-empty
        :image-size="120"
        :description="selectedSessionId ? '该会话暂无观点单元，请先完成 CoI 观点整理' : '请先选择群组'"
      />
    </el-card>

    <el-dialog
      v-model="splitDialogVisible"
      title="拆分观点单元"
      width="min(680px, 92vw)"
      :close-on-click-modal="!mutatingStructure"
      :close-on-press-escape="!mutatingStructure"
      :show-close="!mutatingStructure"
      @closed="closeSplitDialog"
    >
      <p class="split-hint">把光标放在需要拆开的文字位置，然后点击“按光标拆分”。</p>
      <textarea
        ref="splitTextareaRef"
        v-model="splitContent"
        class="split-textarea"
        rows="8"
      />
      <template #footer>
        <el-button :disabled="mutatingStructure" @click="closeSplitDialog">取消</el-button>
        <el-button type="primary" :loading="mutatingStructure" @click="confirmSplitAtCursor">
          按光标拆分
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.header-desc { font-size: 13px; color: #909399; }
.header-desc kbd {
  display: inline-block;
  padding: 1px 5px;
  border: 1px solid #dcdfe6;
  border-radius: 3px;
  background: #f5f7fa;
  font-size: 11px;
  margin: 0 2px;
}

.control-card :deep(.el-card__body) { padding: 14px 20px; }
.control-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.control-left { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.control-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.control-item { display: flex; align-items: center; gap: 8px; }
.control-label { font-size: 14px; color: #606266; white-space: nowrap; }
.progress-text { font-size: 14px; font-weight: 500; color: #303133; white-space: nowrap; }

.list-header { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }
.list-title { font-size: 15px; font-weight: 600; color: #303133; }
.list-tags { display: flex; gap: 6px; }

.coding-list { display: flex; flex-direction: column; gap: 6px; max-height: calc(100vh - 300px); overflow-y: auto; }
.coding-row {
  padding: 10px 12px;
  border: 1.5px solid transparent;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  transition: all 0.12s;
}
.coding-row:hover { background: #f8fafc; }
.coding-row.is-focused { border-color: #409eff; background: #f0f7ff; }
.coding-row.is-coded { border-left: 3px solid #67c23a; }
.coding-row.is-focused.is-coded { border-left-color: #409eff; }
.coding-row.is-starred { box-shadow: inset 0 0 0 1px #f3d19e; background: #fffaf0; }
.coding-row.is-focused.is-starred { background: #fff7e6; }
.coding-row.is-multi-coded,
.coding-row.is-multi-coded:hover,
.coding-row.is-multi-coded.is-focused,
.coding-row.is-multi-coded.is-starred {
  border-color: #e6a23c;
  border-left-color: #e6a23c;
  background: #fff3bf;
}
.unit-top { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.unit-bottom { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.unit-num {
  font-size: 11px;
  color: #c0c4cc;
  font-weight: 600;
  flex-shrink: 0;
  width: 24px;
  text-align: right;
}
.unit-time { font-size: 12px; color: #909399; flex-shrink: 0; width: 40px; }
.unit-content { flex: 1; min-width: 0; font-size: 15px; color: #303133; line-height: 1.7; word-break: break-word; }
.star-btn {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid #dcdfe6;
  border-radius: 50%;
  color: #a8abb2;
  background: #fff;
  font-size: 20px;
  line-height: 28px;
  cursor: pointer;
  transition: all 0.12s;
}
.star-btn:hover { color: #e6a23c; border-color: #e6a23c; }
.star-btn.is-active { color: #e6a23c; border-color: #e6a23c; background: #fdf6ec; }
.category-buttons { display: flex; align-items: center; gap: 6px; padding-left: 72px; flex-wrap: wrap; }
.structure-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.structure-btn {
  padding: 3px 9px;
  border: 1px solid #dcdfe6;
  border-radius: 5px;
  color: #606266;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  line-height: 1.6;
}
.structure-btn:hover:not(:disabled) { color: #409eff; border-color: #409eff; }
.structure-btn:disabled { cursor: not-allowed; opacity: 0.55; }
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
.split-hint { margin: 0 0 10px; color: #606266; font-size: 14px; }
.split-textarea {
  box-sizing: border-box;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  color: #303133;
  background: #fff;
  font: inherit;
  line-height: 1.7;
  resize: vertical;
}
.split-textarea:focus { outline: none; border-color: #409eff; box-shadow: 0 0 0 2px rgba(64,158,255,0.12); }
.empty-card { min-height: 320px; display: flex; align-items: center; justify-content: center; }
@media (max-width: 760px) {
  .category-buttons { padding-left: 0; }
  .unit-bottom { align-items: flex-start; flex-direction: column; }
  .unit-top { display: grid; grid-template-columns: 28px 44px minmax(0, 1fr); }
}
</style>
