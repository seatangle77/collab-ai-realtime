<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminWindowMetricsBatchReasoning } from '../../types/admin'
import {
  listWindowMetricsBatchReasoning,
  deleteWindowMetricsBatchReasoning,
  batchDeleteWindowMetricsBatchReasoning,
} from '../../api/admin/window-metrics-batch-reasoning'
import { formatDateTimeToCST } from '../../utils/datetime'
import { exportRowsToCsv } from '../../utils/csv'

const loading = ref(false)
const rows = ref<AdminWindowMetricsBatchReasoning[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminWindowMetricsBatchReasoning[]>([])
const membersDialogVisible = ref(false)
const membersDialogTitle = ref('')
const membersDialogContent = ref('')

const filters = reactive({
  session_id: '',
  windowStartRange: [] as Date[],
})

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.windowStartRange.length === 2 ? filters.windowStartRange : [undefined, undefined]
    const res = await listWindowMetricsBatchReasoning({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      window_start_from: from ? from.toISOString() : undefined,
      window_start_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: unknown) {
    ElMessage.error((e as Error)?.message || '加载窗口论证批量日志失败')
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
  filters.windowStartRange = []
  page.value = 1
  fetchData()
}

function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminWindowMetricsBatchReasoning[]) { selectedRows.value = r }

function handleViewMembers(row: AdminWindowMetricsBatchReasoning) {
  membersDialogTitle.value = `成员 JSON - ${row.session_id}`
  membersDialogContent.value = JSON.stringify(row.members, null, 2)
  membersDialogVisible.value = true
}

function handleExportCsv() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选择要导出的记录')
    return
  }

  exportRowsToCsv<AdminWindowMetricsBatchReasoning>({
    filename: `窗口论证批量日志-选中导出-${Date.now()}.csv`,
    rows: selectedRows.value,
    columns: [
      { key: 'id', title: 'ID' },
      { key: 'session_id', title: '会话 ID' },
      { key: 'window_start', title: '窗口开始', format: (row) => formatDateTimeToCST(row.window_start) },
      { key: 'members', title: '成员数', format: (row) => String(row.members.length) },
      { key: 'members_json', title: '成员 JSON', format: (row) => JSON.stringify(row.members, null, 2) },
      { key: 'created_at', title: '创建时间', format: (row) => formatDateTimeToCST(row.created_at) },
    ],
  })
}

async function handleDelete(row: AdminWindowMetricsBatchReasoning) {
  try {
    await ElMessageBox.confirm('确认删除该窗口论证批量日志吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteWindowMetricsBatchReasoning(row.id)
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
    const res = await batchDeleteWindowMetricsBatchReasoning(ids)
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
      <h2 class="page-title">窗口论证批量日志</h2>
    </div>

    <el-card shadow="never">
      <el-form :model="filters" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="会话 ID">
              <el-input v-model="filters.session_id" placeholder="精确匹配" clearable />
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
      <div class="filter-actions">
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
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

      <el-table
        ref="tableRef"
        :data="rows"
        v-loading="loading"
        border
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="id" label="ID" min-width="180" show-overflow-tooltip />
        <el-table-column prop="session_id" label="会话 ID" min-width="180" show-overflow-tooltip />
        <el-table-column label="窗口开始" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.window_start) }}</template>
        </el-table-column>
        <el-table-column label="成员数" width="100">
          <template #default="{ row }">{{ row.members.length }}</template>
        </el-table-column>
        <el-table-column label="成员 JSON" min-width="120">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="handleViewMembers(row)">查看 JSON</el-button>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180" show-overflow-tooltip>
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

    <el-dialog v-model="membersDialogVisible" :title="membersDialogTitle" width="680px">
      <pre class="members-json">{{ membersDialogContent }}</pre>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.filter-actions { text-align: right; margin-top: 8px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
.pagination { display: flex; justify-content: flex-end; margin-top: 12px; }
.members-json {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  color: #1f2937;
}
</style>
