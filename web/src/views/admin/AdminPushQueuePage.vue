<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminPushQueue, DiscussionStateType, PushQueueStatus } from '../../types/admin'
import { listPushQueue, deletePushQueueItem, batchDeletePushQueue } from '../../api/admin/push-queue'
import { formatDateTimeToCST } from '../../utils/datetime'
import { DISCUSSION_STATE_LABELS, DISCUSSION_STATE_TAGS } from '../../utils/discussion'

const STATUS_LABELS: Record<PushQueueStatus, string> = {
  pending: '待发送',
  delivered: '已发送',
}

const loading = ref(false)
const rows = ref<AdminPushQueue[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminPushQueue[]>([])
const contentDialogVisible = ref(false)
const contentDialogTitle = ref('')
const contentDialogValue = ref('')

const filters = reactive({
  session_id: '',
  target_user_id: '',
  state_type: '' as DiscussionStateType | '',
  status: '' as PushQueueStatus | '',
  createdRange: [] as Date[],
})

function truncateContent(content: string, maxLength = 40) {
  if (content.length <= maxLength) return content
  return `${content.slice(0, maxLength)}...`
}

function handleViewContent(row: AdminPushQueue) {
  contentDialogTitle.value = `${row.session_title || row.session_id} - 推送内容`
  contentDialogValue.value = row.push_content
  contentDialogVisible.value = true
}

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.createdRange.length === 2 ? filters.createdRange : [undefined, undefined]
    const res = await listPushQueue({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      target_user_id: filters.target_user_id || undefined,
      state_type: filters.state_type || undefined,
      status: filters.status || undefined,
      created_from: from ? from.toISOString() : undefined,
      created_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载推送队列失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; fetchData() }
function handleReset() {
  filters.session_id = ''
  filters.target_user_id = ''
  filters.state_type = ''
  filters.status = ''
  filters.createdRange = []
  page.value = 1
  fetchData()
}
function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminPushQueue[]) { selectedRows.value = r }

async function handleDelete(row: AdminPushQueue) {
  try {
    await ElMessageBox.confirm('确认删除该推送队列记录吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deletePushQueueItem(row.id)
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
    const res = await batchDeletePushQueue(ids)
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
      <h2 class="page-title">推送队列</h2>
    </div>

    <el-card shadow="never">
      <el-form :model="filters" label-width="100px">
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
          <el-col :span="5">
            <el-form-item label="状态类型">
              <el-select v-model="filters.state_type" placeholder="全部" clearable style="width: 100%">
                <el-option v-for="(label, val) in DISCUSSION_STATE_LABELS" :key="val" :label="label" :value="val" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="队列状态">
              <el-select v-model="filters.status" placeholder="全部" clearable style="width: 100%">
                <el-option v-for="(label, val) in STATUS_LABELS" :key="val" :label="label" :value="val" />
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
            <el-form-item label="创建时间">
              <el-date-picker v-model="filters.createdRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width: 100%" />
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
        <el-table-column prop="session_title" label="会话" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ row.session_title || row.session_id }}</template>
        </el-table-column>
        <el-table-column prop="target_user_name" label="目标用户" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target_user_name || row.target_user_id }}</template>
        </el-table-column>
        <el-table-column label="状态类型" min-width="120">
          <template #default="{ row }">
            <el-tag :type="DISCUSSION_STATE_TAGS[row.state_type as DiscussionStateType]">
              {{ DISCUSSION_STATE_LABELS[row.state_type as DiscussionStateType] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="推送内容" min-width="240">
          <template #default="{ row }">
            <div class="content-cell">
              <span class="content-preview">{{ truncateContent(row.push_content) }}</span>
              <el-button type="primary" link size="small" @click="handleViewContent(row)">查看全文</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="队列状态" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'pending' ? 'warning' : 'success'">
              {{ STATUS_LABELS[row.status as PushQueueStatus] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分析窗口开始" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.analysis_window_start) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="送达时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.delivered_at) }}</template>
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

    <el-dialog v-model="contentDialogVisible" :title="contentDialogTitle" width="720px">
      <el-input :model-value="contentDialogValue" type="textarea" :rows="12" readonly />
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.toolbar { margin-bottom: 8px; }
.pagination { display: flex; justify-content: flex-end; margin-top: 12px; }
.content-cell { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.content-preview {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
