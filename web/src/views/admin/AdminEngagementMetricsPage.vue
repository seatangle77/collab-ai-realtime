<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminEngagementMetric } from '../../types/admin'
import {
  listEngagementMetrics,
  deleteEngagementMetric,
  batchDeleteEngagementMetrics,
} from '../../api/admin/engagement-metrics'
import { formatDateTimeToCST } from '../../utils/datetime'
import { exportRowsToCsv } from '../../utils/csv'

const loading = ref(false)
const rows = ref<AdminEngagementMetric[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminEngagementMetric[]>([])
const detailDialogVisible = ref(false)
const detailRow = ref<AdminEngagementMetric | null>(null)

const filters = reactive({
  session_id: '',
  user_id: '',
  calculatedRange: [] as Date[],
})

function formatMetric(value: number | null | undefined, digits = 4) {
  if (value == null) return '-'
  return value.toFixed(digits)
}

function handleViewDetail(row: AdminEngagementMetric) {
  detailRow.value = row
  detailDialogVisible.value = true
}

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.calculatedRange.length === 2 ? filters.calculatedRange : [undefined, undefined]
    const res = await listEngagementMetrics({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      user_id: filters.user_id || undefined,
      calculated_from: from ? from.toISOString() : undefined,
      calculated_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载参与度指标失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; fetchData() }
function handleReset() {
  filters.session_id = ''
  filters.user_id = ''
  filters.calculatedRange = []
  page.value = 1
  fetchData()
}
function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminEngagementMetric[]) { selectedRows.value = r }

async function handleDelete(row: AdminEngagementMetric) {
  try {
    await ElMessageBox.confirm('确认删除该参与度指标记录吗？', '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  try {
    await deleteEngagementMetric(row.id)
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
    const res = await batchDeleteEngagementMetrics(ids)
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
  exportRowsToCsv<AdminEngagementMetric>({
    filename: `参与度指标-选中导出-${ts}.csv`,
    columns: [
      { key: 'id', title: 'ID' },
      { key: 'session_id', title: '会话 ID' },
      { key: 'user_id', title: '用户 ID' },
      { key: 'user_name', title: '用户名', format: (r) => r.user_name || '' },
      { key: 'calculated_at', title: '计算时间', format: (r) => formatDateTimeToCST(r.calculated_at) },
      { key: 'speaking_ratio', title: '发言比例', format: (r) => r.speaking_ratio?.toFixed(4) ?? '' },
      { key: 'speaking_frequency', title: '发言频率', format: (r) => r.speaking_frequency?.toFixed(4) ?? '' },
      { key: 'silence_duration_s', title: '静默时长(s)', format: (r) => r.silence_duration_s?.toFixed(2) ?? '' },
      { key: 'mattr_score', title: 'MATTR', format: (r) => r.mattr_score?.toFixed(4) ?? '' },
      { key: 'avg_sentence_length', title: '平均句长', format: (r) => r.avg_sentence_length?.toFixed(2) ?? '' },
      { key: 'response_rate', title: '回应率', format: (r) => r.response_rate?.toFixed(4) ?? '' },
      { key: 'new_idea_rate', title: '新想法率', format: (r) => r.new_idea_rate?.toFixed(4) ?? '' },
      { key: 'topic_cosine_similarity', title: '话题余弦相似度', format: (r) => r.topic_cosine_similarity?.toFixed(4) ?? '' },
      { key: 'semantic_cohesion', title: '语义凝聚度', format: (r) => r.semantic_cohesion?.toFixed(4) ?? '' },
      { key: 'semantic_uniqueness', title: '语义独特度', format: (r) => r.semantic_uniqueness?.toFixed(4) ?? '' },
    ],
    rows: selectedRows.value,
  })
}

onMounted(() => { fetchData() })
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">参与度指标</h2>
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
            <el-form-item label="用户 ID">
              <el-input v-model="filters.user_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="计算时间">
              <el-date-picker v-model="filters.calculatedRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width: 100%" />
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
        <el-table-column prop="id" label="ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="session_id" label="会话 ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="user_name" label="用户" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.user_name || row.user_id }}</template>
        </el-table-column>
        <el-table-column label="计算时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.calculated_at) }}</template>
        </el-table-column>
        <el-table-column prop="speaking_ratio" label="发言比例" min-width="100">
          <template #default="{ row }">{{ formatMetric(row.speaking_ratio, 4) }}</template>
        </el-table-column>
        <el-table-column prop="silence_duration_s" label="静默(s)" min-width="90">
          <template #default="{ row }">{{ formatMetric(row.silence_duration_s, 2) }}</template>
        </el-table-column>
        <el-table-column prop="mattr_score" label="MATTR" min-width="90">
          <template #default="{ row }">{{ formatMetric(row.mattr_score, 4) }}</template>
        </el-table-column>
        <el-table-column prop="new_idea_rate" label="新想法率" min-width="100">
          <template #default="{ row }">{{ formatMetric(row.new_idea_rate, 4) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleViewDetail(row)">查看详情</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[10, 20, 50, 100]" layout="total, sizes, prev, pager, next, jumper" @current-change="handlePageChange" @size-change="handlePageSizeChange" />
      </div>
    </el-card>

    <el-dialog v-model="detailDialogVisible" title="参与度指标详情" width="760px">
      <el-descriptions v-if="detailRow" :column="2" :border="true">
        <el-descriptions-item label="会话 ID">{{ detailRow.session_id }}</el-descriptions-item>
        <el-descriptions-item label="用户">{{ detailRow.user_name || detailRow.user_id }}</el-descriptions-item>
        <el-descriptions-item label="计算时间">{{ formatDateTimeToCST(detailRow.calculated_at) }}</el-descriptions-item>
        <el-descriptions-item label="发言比例">{{ formatMetric(detailRow.speaking_ratio, 4) }}</el-descriptions-item>
        <el-descriptions-item label="发言频率">{{ formatMetric(detailRow.speaking_frequency, 4) }}</el-descriptions-item>
        <el-descriptions-item label="静默时长(s)">{{ formatMetric(detailRow.silence_duration_s, 2) }}</el-descriptions-item>
        <el-descriptions-item label="MATTR">{{ formatMetric(detailRow.mattr_score, 4) }}</el-descriptions-item>
        <el-descriptions-item label="平均句长">{{ formatMetric(detailRow.avg_sentence_length, 2) }}</el-descriptions-item>
        <el-descriptions-item label="回应率">{{ formatMetric(detailRow.response_rate, 4) }}</el-descriptions-item>
        <el-descriptions-item label="新想法率">{{ formatMetric(detailRow.new_idea_rate, 4) }}</el-descriptions-item>
        <el-descriptions-item label="话题余弦相似度">{{ formatMetric(detailRow.topic_cosine_similarity, 4) }}</el-descriptions-item>
        <el-descriptions-item label="语义凝聚度">{{ formatMetric(detailRow.semantic_cohesion, 4) }}</el-descriptions-item>
        <el-descriptions-item label="语义独特度">{{ formatMetric(detailRow.semantic_uniqueness, 4) }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.toolbar { margin-bottom: 8px; }
.pagination { display: flex; justify-content: flex-end; margin-top: 12px; }
</style>
