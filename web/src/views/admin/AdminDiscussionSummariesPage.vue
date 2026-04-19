<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminDiscussionSummary } from '../../types/admin'
import {
  listDiscussionSummaries,
  updateDiscussionSummary,
  deleteDiscussionSummary,
  batchDeleteDiscussionSummaries,
} from '../../api/admin/discussion-summaries'
import { formatDateTimeToCST } from '../../utils/datetime'
import { exportRowsToCsv } from '../../utils/csv'

const loading = ref(false)
const saving = ref(false)
const rows = ref<AdminDiscussionSummary[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminDiscussionSummary[]>([])

const viewDialogVisible = ref(false)
const viewDialogTitle = ref('')
const viewContent = ref('')

const editDialogVisible = ref(false)
const editingId = ref<string | null>(null)
const editDialogTitle = ref('')
const editContent = ref('')

const filters = reactive({
  session_id: '',
  version: undefined as number | undefined,
  windowStartRange: [] as Date[],
})

function truncateContent(content: string, maxLength = 80) {
  if (content.length <= maxLength) return content
  return `${content.slice(0, maxLength)}...`
}

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.windowStartRange.length === 2 ? filters.windowStartRange : [undefined, undefined]
    const res = await listDiscussionSummaries({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      version: filters.version,
      window_start_from: from ? from.toISOString() : undefined,
      window_start_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载讨论摘要失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; fetchData() }
function handleReset() {
  filters.session_id = ''
  filters.version = undefined
  filters.windowStartRange = []
  page.value = 1
  fetchData()
}
function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminDiscussionSummary[]) { selectedRows.value = r }

function handleExportCsv() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选择要导出的记录')
    return
  }

  const ts = Date.now()
  exportRowsToCsv<AdminDiscussionSummary>({
    filename: `讨论摘要-选中导出-${ts}.csv`,
    rows: selectedRows.value,
    columns: [
      { key: 'id', title: 'ID' },
      { key: 'session_id', title: '会话 ID' },
      { key: 'session_title', title: '会话标题', format: (row) => row.session_title || row.session_id },
      { key: 'version', title: '版本' },
      { key: 'window_start', title: '窗口开始', format: (row) => formatDateTimeToCST(row.window_start) },
      { key: 'window_end', title: '窗口结束', format: (row) => formatDateTimeToCST(row.window_end) },
      { key: 'created_at', title: '创建时间', format: (row) => formatDateTimeToCST(row.created_at) },
      { key: 'content', title: '摘要内容', format: (row) => row.content || '' },
    ],
  })
}

function handleView(row: AdminDiscussionSummary) {
  viewDialogTitle.value = `${row.session_title || row.session_id} - v${row.version}`
  viewContent.value = row.content || ''
  viewDialogVisible.value = true
}

function handleEdit(row: AdminDiscussionSummary) {
  editingId.value = row.id
  editDialogTitle.value = `${row.session_title || row.session_id} - 编辑摘要`
  editContent.value = row.content || ''
  editDialogVisible.value = true
}

async function handleSaveEdit() {
  if (!editingId.value) return
  if (!editContent.value.trim()) {
    ElMessage.warning('摘要内容不能为空')
    return
  }
  saving.value = true
  try {
    const updated = await updateDiscussionSummary(editingId.value, editContent.value)
    const index = rows.value.findIndex((row) => row.id === updated.id)
    if (index >= 0) rows.value[index] = updated
    editDialogVisible.value = false
    ElMessage.success('摘要更新成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '更新摘要失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row: AdminDiscussionSummary) {
  try {
    await ElMessageBox.confirm('确认删除该讨论摘要吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteDiscussionSummary(row.id)
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
    await ElMessageBox.confirm(`确认删除已选 ${selectedRows.value.length} 条记录吗？`, '批量删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    const ids = selectedRows.value.map((row) => row.id)
    const res = await batchDeleteDiscussionSummaries(ids)
    ElMessage.success(`成功删除 ${res.deleted} 条记录`)
    tableRef.value?.clearSelection?.()
    if (rows.value.length === selectedRows.value.length && page.value > 1) page.value -= 1
    fetchData()
  } catch (e: any) {
    ElMessage.error(e?.message || '批量删除失败')
  }
}

onMounted(() => { fetchData() })
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">讨论摘要</h2>
    </div>

    <el-card shadow="never">
      <el-form :model="filters" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="7">
            <el-form-item label="会话 ID">
              <el-input v-model="filters.session_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="版本号">
              <el-input-number v-model="filters.version" :min="1" :precision="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="窗口开始时间">
              <el-date-picker v-model="filters.windowStartRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
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
        <el-table-column prop="session_title" label="会话标题" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.session_title || row.session_id }}</template>
        </el-table-column>
        <el-table-column prop="version" label="版本" min-width="80" />
        <el-table-column label="窗口开始" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.window_start) }}</template>
        </el-table-column>
        <el-table-column label="窗口结束" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.window_end) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="摘要内容" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">{{ truncateContent(row.content || '') }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleView(row)">查看</el-button>
            <el-button type="primary" link size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[10, 20, 50, 100, 150, 200]" layout="total, sizes, prev, pager, next, jumper" @current-change="handlePageChange" @size-change="handlePageSizeChange" />
      </div>
    </el-card>

    <el-dialog v-model="viewDialogVisible" :title="viewDialogTitle" width="720px">
      <el-input :model-value="viewContent" type="textarea" :rows="14" readonly />
    </el-dialog>

    <el-dialog v-model="editDialogVisible" :title="editDialogTitle" width="720px">
      <el-input v-model="editContent" type="textarea" :rows="14" />
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
.pagination { display: flex; justify-content: flex-end; margin-top: 12px; }
</style>
