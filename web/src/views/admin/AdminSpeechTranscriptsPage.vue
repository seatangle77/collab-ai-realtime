<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminSpeechTranscript } from '../../types/admin'
import {
  listSpeechTranscripts,
  deleteSpeechTranscript,
  updateSpeechTranscript,
  batchDeleteSpeechTranscripts,
} from '../../api/admin/speech-transcripts'
import { formatDateTimeToCST } from '../../utils/datetime'
import { exportRowsToCsv } from '../../utils/csv'

const loading = ref(false)
const rows = ref<AdminSpeechTranscript[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminSpeechTranscript[]>([])
const textDialogVisible = ref(false)
const textDialogTitle = ref('')
const textDialogValue = ref('')
const editDialogVisible = ref(false)
const editSaving = ref(false)
const editingRow = ref<AdminSpeechTranscript | null>(null)
const editText = ref('')

const filters = reactive({
  session_id: '',
  group_id: '',
  speaker: '',
  text: '',
  createdRange: [] as Date[],
})

function truncateText(text: string | null, maxLength = 80) {
  if (!text) return '-'
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength)}...`
}

function openTextDialog(row: AdminSpeechTranscript) {
  textDialogTitle.value = `${row.speaker || row.speaker_user_id || '-'} - 转写文本`
  textDialogValue.value = row.text || ''
  textDialogVisible.value = true
}

function openEditDialog(row: AdminSpeechTranscript) {
  editingRow.value = row
  editText.value = row.text || ''
  editDialogVisible.value = true
}

function formatConfidence(value: number | null) {
  if (value == null) return '-'
  return value.toFixed(3)
}

function formatDuration(value: number | null) {
  if (value == null) return '-'
  return `${value.toFixed(2)}s`
}

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.createdRange.length === 2 ? filters.createdRange : [undefined, undefined]
    const res = await listSpeechTranscripts({
      page: page.value,
      page_size: pageSize.value,
      session_id: filters.session_id || undefined,
      group_id: filters.group_id || undefined,
      speaker: filters.speaker || undefined,
      text: filters.text || undefined,
      created_from: from ? from.toISOString() : undefined,
      created_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载语音转写失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { page.value = 1; fetchData() }
function handleReset() {
  filters.session_id = ''
  filters.group_id = ''
  filters.speaker = ''
  filters.text = ''
  filters.createdRange = []
  page.value = 1
  fetchData()
}
function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }
function handleSelectionChange(r: AdminSpeechTranscript[]) { selectedRows.value = r }

function handleExportCsv() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选择要导出的转写记录')
    return
  }

  const ts = Date.now()
  exportRowsToCsv<AdminSpeechTranscript>({
    filename: `语音转写-选中导出-${ts}.csv`,
    rows: selectedRows.value,
    columns: [
      { key: 'transcript_id', title: '转写 ID' },
      { key: 'group_id', title: '群组 ID' },
      { key: 'session_id', title: '会话 ID' },
      { key: 'speaker', title: '说话人', format: (row) => row.speaker || row.speaker_user_id || row.user_id || '' },
      { key: 'text', title: '转写文本', format: (row) => row.text || '' },
      { key: 'duration', title: '时长', format: (row) => formatDuration(row.duration) },
      { key: 'confidence', title: '置信度', format: (row) => formatConfidence(row.confidence) },
      { key: 'created_at', title: '创建时间', format: (row) => formatDateTimeToCST(row.created_at) },
    ],
  })
}

async function handleDelete(row: AdminSpeechTranscript) {
  try {
    await ElMessageBox.confirm('确认删除该转写记录吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteSpeechTranscript(row.transcript_id)
    ElMessage.success('删除成功')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    fetchData()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

async function handleSaveEdit() {
  if (!editingRow.value) return
  const nextText = editText.value.trim()
  if (!nextText) {
    ElMessage.warning('转写文本不能为空')
    return
  }
  editSaving.value = true
  try {
    const updated = await updateSpeechTranscript(editingRow.value.transcript_id, nextText)
    const index = rows.value.findIndex((row) => row.transcript_id === updated.transcript_id)
    if (index >= 0) rows.value[index] = updated
    ElMessage.success('转写文本已更新')
    editDialogVisible.value = false
    editingRow.value = null
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    editSaving.value = false
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
    const ids = selectedRows.value.map((row) => row.transcript_id)
    const res = await batchDeleteSpeechTranscripts(ids)
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
      <h2 class="page-title">语音转写</h2>
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
            <el-form-item label="说话人">
              <el-input v-model="filters.speaker" placeholder="模糊匹配" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="文本关键词">
              <el-input v-model="filters.text" placeholder="模糊匹配" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="10">
            <el-form-item label="创建时间">
              <el-date-picker v-model="filters.createdRange" type="datetimerange" range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="14">
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
        <el-table-column prop="group_id" label="群组 ID" min-width="160" show-overflow-tooltip />
        <el-table-column prop="session_id" label="会话 ID" min-width="160" show-overflow-tooltip />
        <el-table-column prop="speaker" label="说话人" min-width="140" show-overflow-tooltip />
        <el-table-column label="转写文本" min-width="320">
          <template #default="{ row }">
            <div class="text-cell">
              <span class="text-preview">{{ truncateText(row.text) }}</span>
              <div class="text-actions">
                <el-button type="primary" link size="small" @click="openTextDialog(row)">查看全文</el-button>
                <el-button type="primary" link size="small" @click="openEditDialog(row)">编辑</el-button>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="已编辑" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_edited" type="warning" size="small">是</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="时长" min-width="100" align="right">
          <template #default="{ row }">{{ formatDuration(row.duration) }}</template>
        </el-table-column>
        <el-table-column label="置信度" min-width="100" align="right">
          <template #default="{ row }">{{ formatConfidence(row.confidence) }}</template>
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
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[10, 20, 50, 100, 150, 200]" layout="total, sizes, prev, pager, next, jumper" @current-change="handlePageChange" @size-change="handlePageSizeChange" />
      </div>
    </el-card>

    <el-dialog v-model="textDialogVisible" :title="textDialogTitle" width="720px">
      <el-input :model-value="textDialogValue" type="textarea" :rows="12" readonly />
    </el-dialog>

    <el-dialog v-model="editDialogVisible" title="编辑转写文本" width="720px">
      <el-input v-model="editText" type="textarea" :rows="12" maxlength="12000" show-word-limit />
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="handleSaveEdit">保存</el-button>
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
.text-cell { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.text-actions { display: flex; flex: none; gap: 4px; }
.text-preview {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
