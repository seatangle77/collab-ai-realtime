<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminKeywordSkw } from '../../types/admin'
import { listKeywordSkw, deleteKeywordSkw, batchDeleteKeywordSkw } from '../../api/admin/keyword-skw'
import { formatDateTimeToCST } from '../../utils/datetime'

const loading = ref(false)
const rows = ref<AdminKeywordSkw[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminKeywordSkw[]>([])

const filters = reactive({
  session_id: '',
  keyword: '',
  user_a_id: '',
  user_b_id: '',
  skw_score_min: undefined as number | undefined,
  skw_score_max: undefined as number | undefined,
  windowStartRange: [] as Date[],
})

function formatScore(value: number | null | undefined) {
  if (value == null) return '-'
  return value.toFixed(4)
}

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.windowStartRange.length === 2 ? filters.windowStartRange : [undefined, undefined]
    const res = await listKeywordSkw({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      keyword: filters.keyword || undefined,
      user_a_id: filters.user_a_id || undefined,
      user_b_id: filters.user_b_id || undefined,
      skw_score_min: filters.skw_score_min,
      skw_score_max: filters.skw_score_max,
      window_start_from: from ? from.toISOString() : undefined,
      window_start_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载关键词 SKW 失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  if (
    filters.skw_score_min !== undefined &&
    filters.skw_score_max !== undefined &&
    filters.skw_score_min > filters.skw_score_max
  ) {
    ElMessage.warning('SKW 最小值不能大于最大值')
    return
  }
  page.value = 1
  fetchData()
}

function handleReset() {
  filters.session_id = ''
  filters.keyword = ''
  filters.user_a_id = ''
  filters.user_b_id = ''
  filters.skw_score_min = undefined
  filters.skw_score_max = undefined
  filters.windowStartRange = []
  page.value = 1
  fetchData()
}

function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminKeywordSkw[]) { selectedRows.value = r }

async function handleDelete(row: AdminKeywordSkw) {
  try {
    await ElMessageBox.confirm('确认删除该关键词 SKW 记录吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteKeywordSkw(row.id)
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
    const res = await batchDeleteKeywordSkw(ids)
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
      <h2 class="page-title">关键词 SKW</h2>
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
            <el-form-item label="关键词">
              <el-input v-model="filters.keyword" placeholder="模糊匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="用户 A ID">
              <el-input v-model="filters.user_a_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="用户 B ID">
              <el-input v-model="filters.user_b_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="5">
            <el-form-item label="SKW 最小值">
              <el-input-number v-model="filters.skw_score_min" :precision="4" :step="0.0001" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="SKW 最大值">
              <el-input-number v-model="filters.skw_score_max" :precision="4" :step="0.0001" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="10">
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
        <el-button type="danger" :disabled="selectedRows.length === 0" @click="handleBatchDelete">
          {{ selectedRows.length > 0 ? `批量删除 (${selectedRows.length})` : '批量删除' }}
        </el-button>
      </div>
      <el-table ref="tableRef" :data="rows" v-loading="loading" border style="width: 100%" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="48" />
        <el-table-column label="窗口开始" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.window_start) }}</template>
        </el-table-column>
        <el-table-column prop="keyword" label="关键词" min-width="180" show-overflow-tooltip />
        <el-table-column label="用户 A" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.user_a_name || row.user_a_id }}</template>
        </el-table-column>
        <el-table-column label="用户 B" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.user_b_name || row.user_b_id || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag v-if="row.skw_status === 'computed'" type="success" size="small">已计算</el-tag>
            <el-tag v-else-if="row.skw_status === 'single_mention'" type="warning" size="small">单人提及</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="SKW 分数" min-width="100">
          <template #default="{ row }">
            <span :class="{ 'high-score': row.skw_score >= 0.7 }">{{ formatScore(row.skw_score) }}</span>
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
.high-score {
  color: #c2410c;
  font-weight: 700;
}
</style>
