<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminWindowMetric } from '../../types/admin'
import {
  listWindowMetrics,
  deleteWindowMetric,
  batchDeleteWindowMetrics,
} from '../../api/admin/window-metrics'
import { formatDateTimeToCST } from '../../utils/datetime'

const loading = ref(false)
const rows = ref<AdminWindowMetric[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminWindowMetric[]>([])

const filters = reactive({
  session_id: '',
  user_id: '',
  has_reasoning: '' as '' | 'true' | 'false',
  has_evidence: '' as '' | 'true' | 'false',
  windowStartRange: [] as Date[],
})

function formatMetric(value: number | null | undefined, digits = 4) {
  if (value == null) return '-'
  return value.toFixed(digits)
}

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.windowStartRange.length === 2 ? filters.windowStartRange : [undefined, undefined]
    const res = await listWindowMetrics({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      user_id: filters.user_id || undefined,
      has_reasoning: filters.has_reasoning === '' ? undefined : filters.has_reasoning === 'true',
      has_evidence: filters.has_evidence === '' ? undefined : filters.has_evidence === 'true',
      window_start_from: from ? from.toISOString() : undefined,
      window_start_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载窗口指标失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; fetchData() }
function handleReset() {
  filters.session_id = ''
  filters.user_id = ''
  filters.has_reasoning = ''
  filters.has_evidence = ''
  filters.windowStartRange = []
  page.value = 1
  fetchData()
}
function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminWindowMetric[]) { selectedRows.value = r }

async function handleDelete(row: AdminWindowMetric) {
  try {
    await ElMessageBox.confirm('确认删除该窗口指标记录吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteWindowMetric(row.id)
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
    const res = await batchDeleteWindowMetrics(ids)
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
      <h2 class="page-title">窗口指标</h2>
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
            <el-form-item label="用户 ID">
              <el-input v-model="filters.user_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="有推理">
              <el-select v-model="filters.has_reasoning" placeholder="全部" clearable style="width: 100%">
                <el-option label="是" value="true" />
                <el-option label="否" value="false" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="有证据">
              <el-select v-model="filters.has_evidence" placeholder="全部" clearable style="width: 100%">
                <el-option label="是" value="true" />
                <el-option label="否" value="false" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="2">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="10">
            <el-form-item label="窗口开始时间">
              <el-date-picker v-model="filters.windowStartRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label=" ">
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <div class="toolbar">
        <el-button type="danger" :disabled="selectedRows.length === 0" @click="handleBatchDelete">
          {{ selectedRows.length > 0 ? `批量删除 (${selectedRows.length})` : '批量删除' }}
        </el-button>
      </div>
      <el-table ref="tableRef" :data="rows" v-loading="loading" border style="width: 100%" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="48" />
        <el-table-column prop="user_name" label="用户" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.user_name || row.user_id }}</template>
        </el-table-column>
        <el-table-column label="窗口开始" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.window_start) }}</template>
        </el-table-column>
        <el-table-column label="窗口结束" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.window_end) }}</template>
        </el-table-column>
        <el-table-column label="发言比例" min-width="100">
          <template #default="{ row }">{{ formatMetric(row.speaking_ratio, 4) }}</template>
        </el-table-column>
        <el-table-column label="静默(s)" min-width="90">
          <template #default="{ row }">{{ formatMetric(row.silence_s, 2) }}</template>
        </el-table-column>
        <el-table-column label="TTR" min-width="90">
          <template #default="{ row }">{{ formatMetric(row.ttr, 4) }}</template>
        </el-table-column>
        <el-table-column label="论点密度" min-width="100">
          <template #default="{ row }">{{ formatMetric(row.arg_density, 4) }}</template>
        </el-table-column>
        <el-table-column label="SREP" min-width="90">
          <template #default="{ row }">{{ formatMetric(row.srep, 4) }}</template>
        </el-table-column>
        <el-table-column label="信息增益" min-width="100">
          <template #default="{ row }">{{ formatMetric(row.info_gain, 4) }}</template>
        </el-table-column>
        <el-table-column label="有推理" min-width="90">
          <template #default="{ row }">
            <el-tag :type="row.has_reasoning ? 'success' : 'info'">{{ row.has_reasoning ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="有证据" min-width="90">
          <template #default="{ row }">
            <el-tag :type="row.has_evidence ? 'success' : 'info'">{{ row.has_evidence ? '是' : '否' }}</el-tag>
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
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.toolbar { margin-bottom: 8px; }
.pagination { display: flex; justify-content: flex-end; margin-top: 12px; }
</style>
