<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminDiscussionState, DiscussionStateType } from '../../types/admin'
import {
  listDiscussionStates,
  deleteDiscussionState,
  batchDeleteDiscussionStates,
} from '../../api/admin/discussion-states'
import { formatDateTimeToCST } from '../../utils/datetime'
import { exportRowsToCsv } from '../../utils/csv'
import { DISCUSSION_STATE_LABELS, DISCUSSION_STATE_TAGS } from '../../utils/discussion'

const loading = ref(false)
const rows = ref<AdminDiscussionState[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminDiscussionState[]>([])
const metricsDialogVisible = ref(false)
const metricsDialogTitle = ref('')
const metricsContent = ref('')

const filters = reactive({
  session_id: '',
  state_type: '' as DiscussionStateType | '',
  target_user_id: '',
  ai_analysis_done: '' as '' | 'true' | 'false',
  push_sent: '' as '' | 'true' | 'false',
  triggeredRange: [] as Date[],
})

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.triggeredRange.length === 2 ? filters.triggeredRange : [undefined, undefined]
    const res = await listDiscussionStates({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      state_type: filters.state_type || undefined,
      target_user_id: filters.target_user_id || undefined,
      ai_analysis_done: filters.ai_analysis_done === '' ? undefined : filters.ai_analysis_done === 'true',
      push_sent: filters.push_sent === '' ? undefined : filters.push_sent === 'true',
      triggered_from: from ? from.toISOString() : undefined,
      triggered_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载讨论状态失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; fetchData() }
function handleReset() {
  filters.session_id = ''
  filters.state_type = ''
  filters.target_user_id = ''
  filters.ai_analysis_done = ''
  filters.push_sent = ''
  filters.triggeredRange = []
  page.value = 1
  fetchData()
}
function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminDiscussionState[]) { selectedRows.value = r }
function handleViewMetrics(row: AdminDiscussionState) {
  metricsDialogTitle.value = `触发指标 - ${DISCUSSION_STATE_LABELS[row.state_type] || row.state_type}`
  metricsContent.value = row.trigger_metrics
    ? JSON.stringify(row.trigger_metrics, null, 2)
    : '暂无指标数据'
  metricsDialogVisible.value = true
}

async function handleDelete(row: AdminDiscussionState) {
  try {
    await ElMessageBox.confirm(`确认删除该讨论状态记录吗？`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  try {
    await deleteDiscussionState(row.id)
    ElMessage.success('删除成功')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    fetchData()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

async function handleBatchDelete() {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(`确认删除已选 ${selectedRows.value.length} 条记录吗？`, '批量删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  try {
    const ids = selectedRows.value.map((r) => r.id)
    const res = await batchDeleteDiscussionStates(ids)
    ElMessage.success(`成功删除 ${res.deleted} 条记录`)
    tableRef.value?.clearSelection?.()
    if (rows.value.length === selectedRows.value.length && page.value > 1) page.value -= 1
    fetchData()
  } catch (e: any) {
    ElMessage.error(e?.message || '批量删除失败')
  }
}

function handleExportCsv() {
  if (selectedRows.value.length === 0) { ElMessage.warning('请先选择要导出的记录'); return }
  const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
  exportRowsToCsv<AdminDiscussionState>({
    filename: `讨论状态-选中导出-${ts}.csv`,
    columns: [
      { key: 'id', title: 'ID' },
      { key: 'session_id', title: '会话 ID' },
      { key: 'state_type', title: '状态类型', format: (r) => DISCUSSION_STATE_LABELS[r.state_type] || r.state_type },
      { key: 'target_user_id', title: '目标用户 ID', format: (r) => r.target_user_id || '' },
      { key: 'target_user_name', title: '目标用户名', format: (r) => r.target_user_name || '' },
      { key: 'ai_analysis_done', title: 'AI分析完成', format: (r) => r.ai_analysis_done ? '是' : '否' },
      { key: 'push_sent', title: '推送已发', format: (r) => r.push_sent ? '是' : '否' },
      { key: 'triggered_at', title: '触发时间', format: (r) => formatDateTimeToCST(r.triggered_at) },
    ],
    rows: selectedRows.value,
  })
}

onMounted(() => { fetchData() })
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">讨论状态</h2>
    </div>

    <el-card shadow="never">
      <el-form :model="filters" label-width="96px">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="会话 ID">
              <el-input v-model="filters.session_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="状态类型">
              <el-select v-model="filters.state_type" placeholder="全部" clearable style="width: 100%">
                <el-option v-for="(label, val) in DISCUSSION_STATE_LABELS" :key="val" :label="label" :value="val" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="目标用户 ID">
              <el-input v-model="filters.target_user_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="AI分析">
              <el-select v-model="filters.ai_analysis_done" placeholder="全部" clearable style="width: 100%">
                <el-option label="已完成" value="true" />
                <el-option label="未完成" value="false" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="推送状态">
              <el-select v-model="filters.push_sent" placeholder="全部" clearable style="width: 100%">
                <el-option label="已推送" value="true" />
                <el-option label="未推送" value="false" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="触发时间">
              <el-date-picker v-model="filters.triggeredRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <div class="toolbar">
        <el-button type="primary" :disabled="selectedRows.length === 0" @click="handleExportCsv">
          {{ selectedRows.length > 0 ? `导出选中 (${selectedRows.length})` : '导出选中' }}
        </el-button>
        <el-button type="danger" :disabled="selectedRows.length === 0" @click="handleBatchDelete">
          {{ selectedRows.length > 0 ? `批量删除 (${selectedRows.length})` : '批量删除' }}
        </el-button>
      </div>
      <el-table ref="tableRef" :data="rows" v-loading="loading" border style="width: 100%" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="48" />
        <el-table-column prop="id" label="ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="session_id" label="会话 ID" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态类型" min-width="120">
          <template #default="{ row }">
            <el-tag :type="DISCUSSION_STATE_TAGS[row.state_type as DiscussionStateType]">
              {{ DISCUSSION_STATE_LABELS[row.state_type as DiscussionStateType] || row.state_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target_user_name" label="目标用户" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target_user_name || row.target_user_id || '-' }}</template>
        </el-table-column>
        <el-table-column label="AI分析" min-width="90">
          <template #default="{ row }">
            <el-tag :type="row.ai_analysis_done ? 'success' : 'info'">{{ row.ai_analysis_done ? '完成' : '未完成' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送" min-width="90">
          <template #default="{ row }">
            <el-tag :type="row.push_sent ? 'success' : 'warning'">{{ row.push_sent ? '已推送' : '未推送' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="触发时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.triggered_at) }}</template>
        </el-table-column>
        <el-table-column label="触发指标" min-width="100">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="handleViewMetrics(row)">查看指标</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[10, 20, 50, 100]" layout="total, sizes, prev, pager, next, jumper" @current-change="handlePageChange" @size-change="handlePageSizeChange" />
      </div>
    </el-card>

    <el-dialog v-model="metricsDialogVisible" :title="metricsDialogTitle" width="640px">
      <pre class="metrics-json">{{ metricsContent }}</pre>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.toolbar { margin-bottom: 8px; }
.pagination { display: flex; justify-content: flex-end; margin-top: 12px; }
.metrics-json {
  margin: 0;
  max-height: 420px;
  overflow: auto;
  padding: 12px;
  border-radius: 8px;
  background: #111827;
  color: #e5e7eb;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
