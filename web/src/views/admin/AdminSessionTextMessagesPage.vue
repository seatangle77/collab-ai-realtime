<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminSessionTextMessage } from '../../types/admin'
import {
  listSessionTextMessages,
  deleteSessionTextMessage,
  batchDeleteSessionTextMessages,
} from '../../api/admin/session-text-messages'
import { formatDateTimeToCST } from '../../utils/datetime'

const loading = ref(false)
const rows = ref<AdminSessionTextMessage[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminSessionTextMessage[]>([])
const contentDialogVisible = ref(false)
const contentDialogTitle = ref('')
const contentDialogValue = ref('')

const filters = reactive({
  session_id: '',
  group_id: '',
  user_id: '',
  sender_name: '',
  content: '',
  createdRange: [] as Date[],
})

function truncateContent(content: string | null, maxLength = 50) {
  if (!content) return '-'
  if (content.length <= maxLength) return content
  return `${content.slice(0, maxLength)}...`
}

function resolveDisplayName(row: AdminSessionTextMessage) {
  return row.user_name || row.sender_name || row.user_id || '-'
}

function handleViewContent(row: AdminSessionTextMessage) {
  contentDialogTitle.value = `${resolveDisplayName(row)} - 消息内容`
  contentDialogValue.value = row.content || ''
  contentDialogVisible.value = true
}

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.createdRange.length === 2 ? filters.createdRange : [undefined, undefined]
    const res = await listSessionTextMessages({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      group_id: filters.group_id || undefined,
      user_id: filters.user_id || undefined,
      sender_name: filters.sender_name || undefined,
      content: filters.content || undefined,
      created_from: from ? from.toISOString() : undefined,
      created_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载文字消息失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; fetchData() }
function handleReset() {
  filters.session_id = ''
  filters.group_id = ''
  filters.user_id = ''
  filters.sender_name = ''
  filters.content = ''
  filters.createdRange = []
  page.value = 1
  fetchData()
}
function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminSessionTextMessage[]) { selectedRows.value = r }

async function handleDelete(row: AdminSessionTextMessage) {
  try {
    await ElMessageBox.confirm('确认删除该文字消息记录吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteSessionTextMessage(row.id)
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
    const res = await batchDeleteSessionTextMessages(ids)
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
      <h2 class="page-title">文字消息</h2>
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
            <el-form-item label="群组 ID">
              <el-input v-model="filters.group_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="用户 ID">
              <el-input v-model="filters.user_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="发送者">
              <el-input v-model="filters.sender_name" placeholder="模糊匹配" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="内容关键词">
              <el-input v-model="filters.content" placeholder="模糊匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="创建时间">
              <el-date-picker v-model="filters.createdRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
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
        <el-table-column prop="group_id" label="群组 ID" min-width="180" show-overflow-tooltip />
        <el-table-column prop="session_id" label="会话 ID" min-width="180" show-overflow-tooltip />
        <el-table-column label="发送者" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ resolveDisplayName(row) }}</template>
        </el-table-column>
        <el-table-column label="内容" min-width="260">
          <template #default="{ row }">
            <div class="content-cell">
              <span class="content-preview">{{ truncateContent(row.content) }}</span>
              <el-button type="primary" link size="small" @click="handleViewContent(row)">查看全文</el-button>
            </div>
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
