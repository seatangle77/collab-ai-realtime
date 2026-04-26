<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminPushLog, DeliveryStatus, PushChannel } from '../../types/admin'
import { listPushLogs, deletePushLog, batchDeletePushLogs } from '../../api/admin/push-logs'
import { formatDateTimeToCST } from '../../utils/datetime'
import { exportRowsToCsv } from '../../utils/csv'

const CHANNEL_LABELS: Record<PushChannel, string> = { web: 'Web', app: 'App', glasses: '眼镜', info_gap: '信息缺口' }
const STATUS_LABELS: Record<DeliveryStatus, string> = {
  pending: '待送达',
  delivered: '已送达',
  failed: '失败',
  skipped: '已跳过',
  deferred: '已暂缓',
}
const REASON_LABELS: Record<string, string> = {
  ws_pending: '等待 WebSocket 实时发送',
  ws_delivered: 'WebSocket 实时送达',
  ws_user_not_connected: 'WebSocket 未找到用户连接',
  ws_send_error: 'WebSocket 发送异常',
  polling_delivered: '用户端轮询补达',
  jpush_pending: '等待极光推送',
  jpush_delivered: '极光推送送达',
  jpush_no_device_token: '没有极光 device_token',
  jpush_send_error: '极光发送失败',
  vad_speaking_deferred: '当前有人说话，暂缓推送',
  same_round_dedup_skipped: '同轮同用户重复，跳过',
  recent_exact_content_skipped: '近期完全相同内容，跳过',
  content_similarity_skipped: '近期相似内容，跳过',
  group_ws_pending: '等待群组 WebSocket 广播',
  group_ws_delivered: '群组 WebSocket 广播送达',
  group_ws_no_online_users: '群组无在线连接',
  hook_skip: '外部规则跳过',
}

const loading = ref(false)
const rows = ref<AdminPushLog[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminPushLog[]>([])
const contentDialogVisible = ref(false)
const contentDialogTitle = ref('')
const contentDialogValue = ref('')

const filters = reactive({
  session_id: '',
  state_id: '',
  target_user_id: '',
  push_channel: '' as PushChannel | '',
  delivery_status: '' as DeliveryStatus | '',
  jpush_message_id: '',
  triggeredRange: [] as Date[],
})

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.triggeredRange.length === 2 ? filters.triggeredRange : [undefined, undefined]
    const res = await listPushLogs({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      state_id: filters.state_id || undefined,
      target_user_id: filters.target_user_id || undefined,
      push_channel: filters.push_channel || undefined,
      delivery_status: filters.delivery_status || undefined,
      jpush_message_id: filters.jpush_message_id || undefined,
      triggered_from: from ? from.toISOString() : undefined,
      triggered_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载推送日志失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; fetchData() }
function handleReset() {
  filters.session_id = ''
  filters.state_id = ''
  filters.target_user_id = ''
  filters.push_channel = ''
  filters.delivery_status = ''
  filters.jpush_message_id = ''
  filters.triggeredRange = []
  page.value = 1
  fetchData()
}
function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminPushLog[]) { selectedRows.value = r }
function truncateContent(content: string | null, maxLength = 40) {
  if (!content) return '-'
  if (content.length <= maxLength) return content
  return `${content.slice(0, maxLength)}...`
}
function handleViewContent(row: AdminPushLog) {
  contentDialogTitle.value = `${row.session_title || row.session_id} - 推送内容`
  contentDialogValue.value = row.push_content || ''
  contentDialogVisible.value = true
}

async function handleDelete(row: AdminPushLog) {
  try {
    await ElMessageBox.confirm('确认删除该推送日志吗？', '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch { return }
  try {
    await deletePushLog(row.id)
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
    const res = await batchDeletePushLogs(ids)
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
  exportRowsToCsv<AdminPushLog>({
    filename: `推送日志-选中导出-${ts}.csv`,
    columns: [
      { key: 'id', title: 'ID' },
      { key: 'session_id', title: '会话 ID' },
      { key: 'session_title', title: '会话标题', format: (r) => r.session_title || '' },
      { key: 'state_type', title: '状态类型', format: (r) => r.state_type || '' },
      { key: 'target_user_name', title: '目标用户', format: (r) => r.target_user_name || '' },
      { key: 'push_content', title: '推送内容', format: (r) => r.push_content || '' },
      { key: 'push_channel', title: '推送渠道', format: (r) => CHANNEL_LABELS[r.push_channel] || r.push_channel },
      { key: 'delivery_status', title: '送达状态', format: (r) => STATUS_LABELS[r.delivery_status] || r.delivery_status },
      { key: 'delivery_reason', title: '送达说明', format: (r) => r.delivery_reason ? (REASON_LABELS[r.delivery_reason] || r.delivery_reason) : '' },
      { key: 'triggered_at', title: '触发时间', format: (r) => formatDateTimeToCST(r.triggered_at) },
      { key: 'delivered_at', title: '送达时间', format: (r) => formatDateTimeToCST(r.delivered_at) },
    ],
    rows: selectedRows.value,
  })
}

onMounted(() => { fetchData() })
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">推送日志</h2>
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
            <el-form-item label="推送渠道">
              <el-select v-model="filters.push_channel" placeholder="全部" clearable style="width: 100%">
                <el-option v-for="(label, val) in CHANNEL_LABELS" :key="val" :label="label" :value="val" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="送达状态">
              <el-select v-model="filters.delivery_status" placeholder="全部" clearable style="width: 100%">
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
          <el-col :span="6">
            <el-form-item label="状态记录 ID">
              <el-input v-model="filters.state_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="极光消息 ID">
              <el-input v-model="filters.jpush_message_id" placeholder="精确匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="触发时间">
              <el-date-picker v-model="filters.triggeredRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width: 100%" />
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
        <el-table-column prop="session_title" label="会话" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.session_title || row.session_id }}</template>
        </el-table-column>
        <el-table-column prop="state_type" label="状态类型" min-width="120" show-overflow-tooltip />
        <el-table-column prop="target_user_name" label="目标用户" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target_user_name || row.target_user_id }}</template>
        </el-table-column>
        <el-table-column label="推送内容" min-width="240">
          <template #default="{ row }">
            <div class="content-cell">
              <span class="content-preview">{{ truncateContent(row.push_content) }}</span>
              <el-button type="primary" link size="small" @click="handleViewContent(row)">查看全文</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="渠道" min-width="80">
          <template #default="{ row }">{{ CHANNEL_LABELS[row.push_channel as PushChannel] || row.push_channel }}</template>
        </el-table-column>
        <el-table-column label="状态" min-width="90">
          <template #default="{ row }">
            <el-tag :type="row.delivery_status === 'delivered' ? 'success' : row.delivery_status === 'failed' ? 'danger' : row.delivery_status === 'skipped' ? 'info' : 'warning'">
              {{ STATUS_LABELS[row.delivery_status as DeliveryStatus] || row.delivery_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="送达说明" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.delivery_reason ? (REASON_LABELS[row.delivery_reason] || row.delivery_reason) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="触发时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ formatDateTimeToCST(row.triggered_at) }}</template>
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
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[10, 20, 50, 100, 150, 200]" layout="total, sizes, prev, pager, next, jumper" @current-change="handlePageChange" @size-change="handlePageSizeChange" />
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
