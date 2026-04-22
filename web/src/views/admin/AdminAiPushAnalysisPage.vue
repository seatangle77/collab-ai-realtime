<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminAiPushAnalysis, AiPushDropReason } from '../../types/admin'
import {
  listAiPushAnalysis,
  deleteAiPushAnalysis,
  batchDeleteAiPushAnalysis,
} from '../../api/admin/ai-push-analysis'
import { formatDateTimeToCST } from '../../utils/datetime'
import { exportRowsToCsv } from '../../utils/csv'

const loading = ref(false)
const rows = ref<AdminAiPushAnalysis[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminAiPushAnalysis[]>([])
const analysisDialogVisible = ref(false)
const analysisDialogTitle = ref('')
const analysisDialogContent = ref('')

const filters = reactive({
  session_id: '',
  target_user_id: '',
  state_type: '',
  ai_needs_prompt: '' as '' | 'true' | 'false',
  drop_reason: '' as '' | AiPushDropReason,
  windowStartRange: [] as Date[],
})

const STATE_TYPE_OPTIONS = [
  { label: '全部', value: '' },
  { label: 'stagnation', value: 'stagnation' },
  { label: 'shallow', value: 'shallow' },
  { label: 'none', value: 'none' },
  { label: 'group_silence', value: 'group_silence' },
]

const DROP_REASON_OPTIONS = [
  { label: '全部', value: '' },
  { label: '通过', value: 'passed' },
  { label: 'AI 判断不需要', value: 'needs_prompt_false' },
  { label: 'Anchor 校验失败', value: 'anchor_invalid' },
  { label: '文案为空', value: 'content_empty' },
  { label: '落库失败', value: 'persist_failed' },
]

function formatDropReason(reason: string | null) {
  const map: Record<string, string> = {
    passed: '通过',
    needs_prompt_false: 'AI 判断不需要',
    anchor_invalid: 'Anchor 校验失败',
    content_empty: '文案为空',
    persist_failed: '落库失败',
  }
  return reason ? (map[reason] ?? reason) : '—'
}

function dropReasonTagType(reason: string | null): 'success' | 'warning' | 'danger' | 'info' | '' {
  if (reason === 'passed') return 'success'
  if (reason === 'needs_prompt_false') return 'info'
  if (reason === 'anchor_invalid') return 'danger'
  if (reason === 'content_empty') return 'warning'
  if (reason === 'persist_failed') return 'danger'
  return ''
}

function formatAnchor(anchor: AdminAiPushAnalysis['ai_anchor']): string {
  if (!anchor) return '—'
  return `${anchor.speaker_name}：${anchor.text}`
}

function truncateText(text: string | null | undefined, maxLength = 24): string {
  if (!text) return '—'
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength)}...`
}

function handleViewAnalysis(row: AdminAiPushAnalysis) {
  analysisDialogTitle.value = `AI 分析 - ${row.target_user_name || row.target_user_id}`
  analysisDialogContent.value = row.ai_analysis || '暂无 AI 分析'
  analysisDialogVisible.value = true
}

async function fetchData() {
  loading.value = true
  try {
    const [from, to] =
      filters.windowStartRange.length === 2 ? filters.windowStartRange : [undefined, undefined]
    const res = await listAiPushAnalysis({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      target_user_id: filters.target_user_id || undefined,
      state_type: filters.state_type || undefined,
      ai_needs_prompt:
        filters.ai_needs_prompt === '' ? undefined : filters.ai_needs_prompt === 'true',
      drop_reason: (filters.drop_reason as AiPushDropReason) || undefined,
      window_start_from: from ? from.toISOString() : undefined,
      window_start_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: unknown) {
    ElMessage.error((e as Error)?.message || '加载 AI 推送分析失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchData()
}

function handleReset() {
  filters.session_id = ''
  filters.target_user_id = ''
  filters.state_type = ''
  filters.ai_needs_prompt = ''
  filters.drop_reason = ''
  filters.windowStartRange = []
  page.value = 1
  fetchData()
}

function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminAiPushAnalysis[]) { selectedRows.value = r }

function handleExportCsv() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选择要导出的记录')
    return
  }
  exportRowsToCsv<AdminAiPushAnalysis>({
    filename: `AI推送分析-选中导出-${Date.now()}.csv`,
    rows: selectedRows.value,
    columns: [
      { key: 'id', title: 'ID' },
      { key: 'session_id', title: '会话 ID' },
      { key: 'window_start', title: '窗口开始', format: (row) => formatDateTimeToCST(row.window_start) },
      { key: 'target_user_id', title: '目标用户 ID' },
      { key: 'target_user_name', title: '目标用户', format: (row) => row.target_user_name || '' },
      { key: 'state_type', title: '触发类型' },
      { key: 'ai_needs_prompt', title: 'AI 判断需推送', format: (row) => row.ai_needs_prompt ? '是' : '否' },
      { key: 'ai_content', title: '生成文案', format: (row) => row.ai_content || '' },
      { key: 'ai_analysis', title: 'AI 分析', format: (row) => row.ai_analysis || '' },
      { key: 'ai_anchor', title: 'Anchor', format: (row) => formatAnchor(row.ai_anchor) },
      { key: 'drop_reason', title: '结果', format: (row) => formatDropReason(row.drop_reason) },
      { key: 'created_at', title: '创建时间', format: (row) => formatDateTimeToCST(row.created_at) },
    ],
  })
}

async function handleDelete(row: AdminAiPushAnalysis) {
  try {
    await ElMessageBox.confirm('确认删除该记录吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch { return }
  try {
    await deleteAiPushAnalysis(row.id)
    ElMessage.success('删除成功')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    fetchData()
  } catch (e: unknown) {
    ElMessage.error((e as Error)?.message || '删除失败')
  }
}

async function handleBatchDelete() {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除已选 ${selectedRows.value.length} 条记录吗？`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    const ids = selectedRows.value.map((r) => r.id)
    const res = await batchDeleteAiPushAnalysis(ids)
    ElMessage.success(`成功删除 ${res.deleted} 条记录`)
    tableRef.value?.clearSelection?.()
    if (rows.value.length === selectedRows.value.length && page.value > 1) page.value -= 1
    fetchData()
  } catch (e: unknown) {
    ElMessage.error((e as Error)?.message || '批量删除失败')
  }
}

onMounted(() => { fetchData() })
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">AI 推送分析</h2>
    </div>

    <el-card shadow="never">
      <el-form :model="filters" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="会话 ID">
              <el-input v-model="filters.session_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="目标用户 ID">
              <el-input v-model="filters.target_user_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="触发类型">
              <el-select v-model="filters.state_type" placeholder="全部" clearable style="width: 100%">
                <el-option
                  v-for="opt in STATE_TYPE_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="AI 判断推送">
              <el-select v-model="filters.ai_needs_prompt" placeholder="全部" clearable style="width: 100%">
                <el-option label="全部" value="" />
                <el-option label="需要" value="true" />
                <el-option label="不需要" value="false" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="结果">
              <el-select v-model="filters.drop_reason" placeholder="全部" clearable style="width: 100%">
                <el-option
                  v-for="opt in DROP_REASON_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="18">
            <el-form-item label="窗口开始时间">
              <el-date-picker
                v-model="filters.windowStartRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始"
                end-placeholder="结束"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <div style="text-align: right; margin-top: 8px;">
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="toolbar">
        <el-button
          type="primary"
          :disabled="selectedRows.length === 0"
          @click="handleExportCsv"
        >
          {{ selectedRows.length > 0 ? `导出选中 (${selectedRows.length})` : '导出选中' }}
        </el-button>
        <el-button
          type="danger"
          :disabled="selectedRows.length === 0"
          @click="handleBatchDelete"
        >
          {{ selectedRows.length > 0 ? `批量删除 (${selectedRows.length})` : '批量删除' }}
        </el-button>
      </div>

      <el-table
        ref="tableRef"
        :data="rows"
        v-loading="loading"
        border
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="窗口开始" min-width="175" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.window_start) }}</template>
        </el-table-column>
        <el-table-column label="目标用户" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target_user_name || row.target_user_id }}</template>
        </el-table-column>
        <el-table-column prop="state_type" label="触发类型" min-width="150" show-overflow-tooltip />
        <el-table-column label="AI 判断" width="100">
          <template #default="{ row }">
            <el-tag :type="row.ai_needs_prompt ? 'success' : 'info'" size="small">
              {{ row.ai_needs_prompt ? '需要推送' : '不需要' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="生成文案" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.ai_content || '—' }}</template>
        </el-table-column>
        <el-table-column label="AI 分析" min-width="240">
          <template #default="{ row }">
            <div class="analysis-cell">
              <span class="analysis-text" :title="row.ai_analysis || ''">{{ truncateText(row.ai_analysis) }}</span>
              <el-button
                v-if="row.ai_analysis"
                link
                size="small"
                type="primary"
                @click="handleViewAnalysis(row)"
              >
                查看分析
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="Anchor" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tooltip
              v-if="row.ai_anchor"
              :content="`transcript_id: ${row.ai_anchor.transcript_id}`"
              placement="top"
            >
              <span>{{ formatAnchor(row.ai_anchor) }}</span>
            </el-tooltip>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="140">
          <template #default="{ row }">
            <el-tag :type="dropReasonTagType(row.drop_reason)" size="small">
              {{ formatDropReason(row.drop_reason) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="175" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100, 150, 200]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="analysisDialogVisible" :title="analysisDialogTitle" width="680px">
      <pre class="analysis-dialog-content">{{ analysisDialogContent }}</pre>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
.pagination { display: flex; justify-content: flex-end; margin-top: 12px; }
.analysis-cell { display: flex; align-items: center; gap: 8px; }
.analysis-text {
  flex: 1;
  min-width: 0;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.analysis-dialog-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  color: #1f2937;
}
</style>
