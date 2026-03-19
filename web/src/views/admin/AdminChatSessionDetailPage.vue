<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminChatSession, AdminTranscript } from '../../types/admin'
import { getAdminChatSession, updateAdminChatSession, deleteAdminChatSession } from '../../api/admin/chat-sessions'
import {
  listAdminTranscripts,
  createAdminTranscript,
  updateAdminTranscript,
  deleteAdminTranscript,
  deleteAdminTranscriptsBatch,
  type CreateAdminTranscriptPayload,
  type UpdateAdminTranscriptPayload,
} from '../../api/admin/adminTranscripts'
import { formatDateTimeToCST } from '../../utils/datetime'

const route = useRoute()
const router = useRouter()
const sessionId = route.params.id as string

// ── 页面状态 ─────────────────────────────────────────────
const session = ref<AdminChatSession | null>(null)
const pageLoading = ref(true)
const error = ref('')

// ── 转写列表 ─────────────────────────────────────────────
const transcripts = ref<AdminTranscript[]>([])
const transcriptTotal = ref(0)
const transcriptPage = ref(1)
const transcriptPageSize = ref(20)
const transcriptLoading = ref(false)
const selectedTranscripts = ref<AdminTranscript[]>([])
const transcriptTableRef = ref<{ clearSelection: () => void } | null>(null)

// ── 编辑会话 dialog ──────────────────────────────────────
const editSessionVisible = ref(false)
const editSessionFormRef = ref<FormInstance>()
const editSessionForm = reactive({
  session_title: '',
  status: 'not_started' as 'not_started' | 'ongoing' | 'ended',
  ended_at: null as Date | null,
})
const editSessionRules: FormRules<typeof editSessionForm> = {
  session_title: [{ required: true, message: '请输入会话标题', trigger: 'blur' }],
}

function openEditSession() {
  if (!session.value) return
  editSessionForm.session_title = session.value.session_title
  editSessionForm.status = session.value.status ?? 'not_started'
  editSessionForm.ended_at = session.value.ended_at ? new Date(session.value.ended_at) : null
  editSessionVisible.value = true
}

async function submitEditSession() {
  if (!editSessionFormRef.value) return
  await editSessionFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const updated = await updateAdminChatSession(sessionId, {
        session_title: editSessionForm.session_title,
        status: editSessionForm.status,
        ended_at: editSessionForm.ended_at ? editSessionForm.ended_at.toISOString() : null,
      })
      session.value = updated
      editSessionVisible.value = false
      ElMessage.success('会话信息已更新')
    } catch (e: any) {
      ElMessage.error(e?.message || '更新会话失败')
    }
  })
}

// ── 新增转写 dialog ──────────────────────────────────────
const addTranscriptVisible = ref(false)
const addTranscriptFormRef = ref<FormInstance>()
const addTranscriptForm = reactive({
  speaker: '',
  text: '',
  start: '',
  end: '',
})
const addTranscriptRules: FormRules<typeof addTranscriptForm> = {
  text: [{ required: true, message: '请输入转写文本', trigger: 'blur' }],
  start: [{ required: true, message: '请输入开始时间', trigger: 'blur' }],
  end: [{ required: true, message: '请输入结束时间', trigger: 'blur' }],
}

function openAddTranscript() {
  addTranscriptForm.speaker = ''
  addTranscriptForm.text = ''
  addTranscriptForm.start = ''
  addTranscriptForm.end = ''
  addTranscriptVisible.value = true
}

async function submitAddTranscript() {
  if (!addTranscriptFormRef.value) return
  await addTranscriptFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const payload: CreateAdminTranscriptPayload = {
        session_id: sessionId,
        group_id: session.value!.group_id,
        text: addTranscriptForm.text,
        start: addTranscriptForm.start,
        end: addTranscriptForm.end,
        speaker: addTranscriptForm.speaker || null,
      }
      await createAdminTranscript(payload)
      ElMessage.success('转写记录已添加')
      addTranscriptVisible.value = false
      await fetchTranscripts(1)
    } catch (e: any) {
      ElMessage.error(e?.message || '添加转写失败')
    }
  })
}

// ── 编辑转写 dialog ──────────────────────────────────────
const editTranscriptVisible = ref(false)
const editTranscriptFormRef = ref<FormInstance>()
const editTranscriptForm = reactive({
  transcript_id: '',
  speaker: '',
  text: '',
  start: '',
  end: '',
})
const editTranscriptRules: FormRules<typeof editTranscriptForm> = {
  text: [{ required: true, message: '请输入转写文本', trigger: 'blur' }],
  start: [{ required: true, message: '请输入开始时间', trigger: 'blur' }],
  end: [{ required: true, message: '请输入结束时间', trigger: 'blur' }],
}

function openEditTranscript(row: AdminTranscript) {
  editTranscriptForm.transcript_id = row.transcript_id
  editTranscriptForm.speaker = row.speaker ?? ''
  editTranscriptForm.text = row.text ?? ''
  editTranscriptForm.start = row.start ?? ''
  editTranscriptForm.end = row.end ?? ''
  editTranscriptVisible.value = true
}

async function submitEditTranscript() {
  if (!editTranscriptFormRef.value) return
  await editTranscriptFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const payload: UpdateAdminTranscriptPayload = {
        text: editTranscriptForm.text,
        start: editTranscriptForm.start,
        end: editTranscriptForm.end,
        speaker: editTranscriptForm.speaker || null,
      }
      await updateAdminTranscript(editTranscriptForm.transcript_id, payload)
      ElMessage.success('转写记录已更新')
      editTranscriptVisible.value = false
      await fetchTranscripts(transcriptPage.value)
    } catch (e: any) {
      ElMessage.error(e?.message || '更新转写失败')
    }
  })
}

// ── 删除转写 ─────────────────────────────────────────────
async function handleDeleteTranscript(row: AdminTranscript) {
  try {
    await ElMessageBox.confirm('确认删除这条转写记录吗？该操作不可恢复。', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteAdminTranscript(row.transcript_id)
    ElMessage.success('转写记录已删除')
    if (transcripts.value.length === 1 && transcriptPage.value > 1) {
      transcriptPage.value -= 1
    }
    await fetchTranscripts(transcriptPage.value)
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

// ── 批量删除转写 ─────────────────────────────────────────
async function handleBatchDeleteTranscripts() {
  if (selectedTranscripts.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除已选 ${selectedTranscripts.value.length} 条转写记录吗？该操作不可恢复。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const ids = selectedTranscripts.value.map((t) => t.transcript_id)
    const res = await deleteAdminTranscriptsBatch(ids)
    ElMessage.success(`成功删除 ${res.deleted} 条转写记录`)
    transcriptTableRef.value?.clearSelection?.()
    if (transcripts.value.length === selectedTranscripts.value.length && transcriptPage.value > 1) {
      transcriptPage.value -= 1
    }
    await fetchTranscripts(transcriptPage.value)
  } catch (e: any) {
    ElMessage.error(e?.message || '批量删除失败')
  }
}

// ── 删除会话 ─────────────────────────────────────────────
async function handleDeleteSession() {
  if (!session.value) return
  try {
    await ElMessageBox.confirm(
      `确认删除会话「${session.value.session_title}」吗？该操作不可恢复。`,
      '删除会话',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteAdminChatSession(sessionId)
    ElMessage.success('会话已删除')
    router.push('/admin/chat-sessions')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除会话失败')
  }
}

// ── 数据加载 ─────────────────────────────────────────────
async function fetchTranscripts(p: number) {
  transcriptPage.value = p
  transcriptLoading.value = true
  try {
    const res = await listAdminTranscripts({
      session_id: sessionId,
      page: p,
      page_size: transcriptPageSize.value,
    })
    transcripts.value = res.items
    transcriptTotal.value = res.meta.total
  } catch (e: any) {
    ElMessage.error(e?.message || '加载转写列表失败')
  } finally {
    transcriptLoading.value = false
  }
}

async function loadData() {
  pageLoading.value = true
  error.value = ''
  const [sessionResult, transcriptsResult] = await Promise.allSettled([
    getAdminChatSession(sessionId),
    listAdminTranscripts({ session_id: sessionId, page: 1, page_size: transcriptPageSize.value }),
  ])
  if (sessionResult.status === 'fulfilled') {
    session.value = sessionResult.value
  } else {
    error.value = '会话不存在或加载失败'
  }
  if (transcriptsResult.status === 'fulfilled') {
    transcripts.value = transcriptsResult.value.items
    transcriptTotal.value = transcriptsResult.value.meta.total
  }
  pageLoading.value = false
}

function handleTranscriptSelectionChange(rows: AdminTranscript[]) {
  selectedTranscripts.value = rows
}

function handleTranscriptPageChange(p: number) {
  void fetchTranscripts(p)
}

function handleTranscriptPageSizeChange(size: number) {
  transcriptPageSize.value = size
  void fetchTranscripts(1)
}

function statusLabel(s: string | null | undefined) {
  if (s === 'ended') return '已结束'
  if (s === 'ongoing') return '进行中'
  return '未开始'
}

function statusType(s: string | null | undefined) {
  if (s === 'ended') return 'info'
  if (s === 'ongoing') return 'success'
  return 'warning'
}

onMounted(() => {
  void loadData()
})
</script>

<template>
  <div class="admin-session-detail-page">
    <div class="admin-session-detail-back">
      <el-button link @click="router.push('/admin/chat-sessions')">← 返回会话列表</el-button>
    </div>

    <div v-if="pageLoading" class="admin-session-detail-loading">正在加载...</div>

    <div v-else-if="error" class="admin-session-detail-error">{{ error }}</div>

    <template v-else-if="session">
      <!-- 会话基本信息 -->
      <el-card class="admin-session-detail-info-card" shadow="never">
        <template #header>
          <div class="admin-session-detail-name-row">
            <span class="admin-session-detail-name">{{ session.session_title }}</span>
            <el-tag :type="statusType(session.status)" size="small">
              {{ statusLabel(session.status) }}
            </el-tag>
          </div>
        </template>
        <div class="admin-session-detail-id">ID：{{ session.id }}</div>
        <el-descriptions :column="2" border size="small" style="margin-top: 12px">
          <el-descriptions-item label="群组 ID">{{ session.group_id }}</el-descriptions-item>
          <el-descriptions-item label="群组名称">{{ session.group_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTimeToCST(session.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="最后更新">{{ formatDateTimeToCST(session.last_updated) }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ session.started_at ? formatDateTimeToCST(session.started_at) : '-' }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ session.ended_at ? formatDateTimeToCST(session.ended_at) : '-' }}</el-descriptions-item>
        </el-descriptions>
        <div class="admin-session-detail-info-actions">
          <el-button type="primary" size="small" @click="openEditSession">编辑会话</el-button>
          <el-button type="danger" size="small" @click="handleDeleteSession">删除会话</el-button>
        </div>
      </el-card>

      <!-- 转写记录 -->
      <el-card class="admin-session-detail-transcripts-card" shadow="never">
        <template #header>
          <div class="admin-session-detail-transcripts-header">
            <span>转写记录（{{ transcriptTotal }}）</span>
            <div class="admin-session-detail-transcripts-toolbar">
              <el-button
                type="danger"
                size="small"
                :disabled="selectedTranscripts.length === 0"
                @click="handleBatchDeleteTranscripts"
              >
                {{ selectedTranscripts.length > 0 ? `批量删除 (${selectedTranscripts.length})` : '批量删除' }}
              </el-button>
              <el-button type="primary" size="small" @click="openAddTranscript">新增转写</el-button>
            </div>
          </div>
        </template>

        <div v-if="!transcripts.length && !transcriptLoading" class="admin-session-detail-empty">
          暂无转写记录
        </div>

        <el-table
          v-else
          ref="transcriptTableRef"
          :data="transcripts"
          v-loading="transcriptLoading"
          border
          size="small"
          style="width: 100%"
          @selection-change="handleTranscriptSelectionChange"
        >
          <el-table-column type="selection" width="44" />
          <el-table-column prop="transcript_id" label="ID" min-width="200" show-overflow-tooltip />
          <el-table-column prop="speaker" label="说话人" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ row.speaker || '-' }}</template>
          </el-table-column>
          <el-table-column prop="text" label="内容" min-width="240" show-overflow-tooltip />
          <el-table-column prop="start" label="开始" min-width="100" show-overflow-tooltip />
          <el-table-column prop="end" label="结束" min-width="100" show-overflow-tooltip />
          <el-table-column label="是否已编辑" min-width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_edited ? 'warning' : 'info'" size="small">
                {{ row.is_edited ? '已编辑' : '原始' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ formatDateTimeToCST(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" min-width="140" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="openEditTranscript(row)">编辑</el-button>
              <el-button type="danger" link size="small" @click="handleDeleteTranscript(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="transcriptTotal > transcriptPageSize" class="admin-session-detail-pagination">
          <el-pagination
            v-model:current-page="transcriptPage"
            v-model:page-size="transcriptPageSize"
            :total="transcriptTotal"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            @current-change="handleTranscriptPageChange"
            @size-change="handleTranscriptPageSizeChange"
          />
        </div>
      </el-card>
    </template>

    <!-- 编辑会话 dialog -->
    <el-dialog v-model="editSessionVisible" title="编辑会话" width="480px">
      <el-form ref="editSessionFormRef" :model="editSessionForm" :rules="editSessionRules" label-width="80px">
        <el-form-item label="会话标题" prop="session_title">
          <el-input v-model="editSessionForm.session_title" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editSessionForm.status" style="width: 100%">
            <el-option label="未开始" value="not_started" />
            <el-option label="进行中" value="ongoing" />
            <el-option label="已结束" value="ended" />
          </el-select>
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker
            v-model="editSessionForm.ended_at"
            type="datetime"
            placeholder="留空则不修改"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editSessionVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditSession">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增转写 dialog -->
    <el-dialog v-model="addTranscriptVisible" title="新增转写" width="480px">
      <el-form ref="addTranscriptFormRef" :model="addTranscriptForm" :rules="addTranscriptRules" label-width="80px">
        <el-form-item label="说话人">
          <el-input v-model="addTranscriptForm.speaker" placeholder="可选" />
        </el-form-item>
        <el-form-item label="内容" prop="text">
          <el-input v-model="addTranscriptForm.text" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="开始时间" prop="start">
          <el-input v-model="addTranscriptForm.start" placeholder="如 00:00:01.000" />
        </el-form-item>
        <el-form-item label="结束时间" prop="end">
          <el-input v-model="addTranscriptForm.end" placeholder="如 00:00:05.000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addTranscriptVisible = false">取消</el-button>
        <el-button type="primary" @click="submitAddTranscript">添加</el-button>
      </template>
    </el-dialog>

    <!-- 编辑转写 dialog -->
    <el-dialog v-model="editTranscriptVisible" title="编辑转写" width="480px">
      <el-form ref="editTranscriptFormRef" :model="editTranscriptForm" :rules="editTranscriptRules" label-width="80px">
        <el-form-item label="说话人">
          <el-input v-model="editTranscriptForm.speaker" placeholder="可选" />
        </el-form-item>
        <el-form-item label="内容" prop="text">
          <el-input v-model="editTranscriptForm.text" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="开始时间" prop="start">
          <el-input v-model="editTranscriptForm.start" />
        </el-form-item>
        <el-form-item label="结束时间" prop="end">
          <el-input v-model="editTranscriptForm.end" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editTranscriptVisible = false">取消</el-button>
        <el-button type="primary" @click="submitEditTranscript">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-session-detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-session-detail-back {
  margin-bottom: 4px;
}

.admin-session-detail-loading {
  font-size: 13px;
  color: #6b7280;
  padding: 16px 0;
}

.admin-session-detail-error {
  padding: 14px 18px;
  border-radius: 8px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #b91c1c;
  font-size: 14px;
}

.admin-session-detail-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.admin-session-detail-name {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.admin-session-detail-id {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 4px;
}

.admin-session-detail-info-actions {
  margin-top: 14px;
  display: flex;
  gap: 8px;
}

.admin-session-detail-transcripts-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 500;
}

.admin-session-detail-transcripts-toolbar {
  display: flex;
  gap: 8px;
}

.admin-session-detail-empty {
  font-size: 13px;
  color: #9ca3af;
  padding: 12px 0;
}

.admin-session-detail-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
