<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminChatSession, AdminGroup } from '../../types/admin'
import {
  listAdminChatSessions,
  updateAdminChatSession,
  deleteAdminChatSession,
  deleteAdminChatSessionsBatch,
  createAdminChatSession,
} from '../../api/admin/chat-sessions'
import { listAdminGroups } from '../../api/admin/groups'
import { formatDateTimeToCST } from '../../utils/datetime'

interface Filters {
  group_id: string
  session_title: string
  status: '' | 'not_started' | 'ongoing' | 'ended'
  createdAtRange: Date[] | []
  lastUpdatedRange: Date[] | []
  endedAtRange: Date[] | []
}

const loading = ref(false)
const sessions = ref<AdminChatSession[]>([])

const filters = reactive<Filters>({
  group_id: '',
  session_title: '',
  status: '',
  createdAtRange: [],
  lastUpdatedRange: [],
  endedAtRange: [],
})

const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminChatSession[]>([])

const createDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive({
  group_id: '',
  session_title: '',
  created_at: null as Date | null,
})

const groupOptions = ref<AdminGroup[]>([])
const groupLoading = ref(false)

const createRules: FormRules<typeof createForm> = {
  group_id: [{ required: true, message: '请选择群组', trigger: 'change' }],
  session_title: [{ required: true, message: '请输入会话标题', trigger: 'blur' }],
}

const editDialogVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({
  id: '',
  session_title: '',
  is_active: true as boolean | null,
  created_at: null as Date | null,
  ended_at: null as Date | null,
})

const editRules: FormRules<typeof editForm> = {
  session_title: [{ required: true, message: '请输入会话标题', trigger: 'blur' }],
}

async function fetchSessions() {
  loading.value = true
  try {
    const [createdFrom, createdTo] =
      filters.createdAtRange.length === 2 ? filters.createdAtRange : [undefined, undefined]
    const [lastUpdatedFrom, lastUpdatedTo] =
      filters.lastUpdatedRange.length === 2 ? filters.lastUpdatedRange : [undefined, undefined]
    const [endedFrom, endedTo] =
      filters.endedAtRange.length === 2 ? filters.endedAtRange : [undefined, undefined]

    const res = await listAdminChatSessions({
      page: page.value,
      page_size: pageSize.value,
      group_id: filters.group_id || undefined,
      session_title: filters.session_title || undefined,
      status: filters.status || undefined,
      created_from: createdFrom ? createdFrom.toISOString() : undefined,
      created_to: createdTo ? createdTo.toISOString() : undefined,
      last_updated_from: lastUpdatedFrom ? lastUpdatedFrom.toISOString() : undefined,
      last_updated_to: lastUpdatedTo ? lastUpdatedTo.toISOString() : undefined,
      ended_from: endedFrom ? endedFrom.toISOString() : undefined,
      ended_to: endedTo ? endedTo.toISOString() : undefined,
    })
    sessions.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '加载会话列表失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchSessions()
}

function handleReset() {
  filters.group_id = ''
  filters.session_title = ''
  filters.status = ''
  filters.createdAtRange = []
  filters.lastUpdatedRange = []
  filters.endedAtRange = []
  page.value = 1
  fetchSessions()
}

function handlePageChange(p: number) {
  page.value = p
  fetchSessions()
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  fetchSessions()
}

async function loadInitialGroupOptions() {
  groupLoading.value = true
  try {
    const res = await listAdminGroups({
      page: 1,
      page_size: 50,
      name: undefined,
    })
    groupOptions.value = res.items
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '加载群组列表失败')
  } finally {
    groupLoading.value = false
  }
}

function openCreateDialog() {
  createForm.group_id = ''
  createForm.session_title = ''
  createForm.created_at = null
  loadInitialGroupOptions()
  createDialogVisible.value = true
}

function openEditDialog(row: AdminChatSession) {
  editForm.id = row.id
  editForm.session_title = row.session_title
  editForm.is_active = row.is_active
  editForm.created_at = row.created_at ? new Date(row.created_at) : null
  editForm.ended_at = row.ended_at ? new Date(row.ended_at) : null
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const payload: Record<string, any> = {
        session_title: editForm.session_title,
        is_active: editForm.is_active,
      }
      if (editForm.created_at) {
        payload.created_at = editForm.created_at.toISOString()
      }
      if (editForm.ended_at) {
        payload.ended_at = editForm.ended_at.toISOString()
      }
      await updateAdminChatSession(editForm.id, payload)
      ElMessage.success('更新会话成功')
      editDialogVisible.value = false
      fetchSessions()
    } catch (e: any) {
      console.error(e)
      ElMessage.error(e?.message || '更新会话失败')
    }
  })
}

async function submitCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      const payload: Record<string, any> = {
        group_id: createForm.group_id,
        session_title: createForm.session_title,
      }
      if (createForm.created_at) {
        const iso = createForm.created_at.toISOString()
        payload.created_at = iso
        // 默认将 last_updated 与创建时间对齐，便于“未开始/进行中”状态判断
        payload.last_updated = iso
      }

      await createAdminChatSession(payload)
      ElMessage.success('创建会话成功')
      createDialogVisible.value = false
      if (!filters.group_id) {
        filters.group_id = createForm.group_id
      }
      page.value = 1
      fetchSessions()
    } catch (e: any) {
      console.error(e)
      const msg = e?.response?.data?.detail || e?.message || '创建会话失败'
      ElMessage.error(msg)
    }
  })
}

function handleSelectionChange(rows: AdminChatSession[]) {
  selectedRows.value = rows
}

async function handleBatchDelete() {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除已选 ${selectedRows.value.length} 条会话记录吗？该操作不可恢复。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const ids = selectedRows.value.map((r) => r.id)
    const res = await deleteAdminChatSessionsBatch(ids)
    ElMessage.success(`成功删除 ${res.deleted} 条会话`)
    tableRef.value?.clearSelection?.()
    if (sessions.value.length === selectedRows.value.length && page.value > 1) {
      page.value -= 1
    }
    fetchSessions()
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '批量删除会话失败')
  }
}

async function handleDelete(row: AdminChatSession) {
  try {
    await ElMessageBox.confirm(`确认删除会话「${row.session_title || row.id}」吗？该操作不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await deleteAdminChatSession(row.id)
    ElMessage.success('删除会话成功')
    if (sessions.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    fetchSessions()
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '删除会话失败')
  }
}

onMounted(() => {
  fetchSessions()
})
</script>

<template>
  <div class="admin-chat-sessions-page">
    <div class="admin-chat-sessions-header">
      <h2 class="admin-chat-sessions-title">会话管理</h2>
      <el-button type="primary" @click="openCreateDialog">新建会话</el-button>
    </div>

    <el-card class="admin-chat-sessions-filters" shadow="never">
      <el-form :model="filters" label-width="96px" class="admin-chat-sessions-filters-form">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="群组 ID">
              <el-input v-model="filters.group_id" placeholder="按群组 ID 精确查询" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="会话标题">
              <el-input v-model="filters.session_title" placeholder="按会话标题模糊搜索" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="会话状态">
              <el-select v-model="filters.status" placeholder="全部" clearable style="width: 100%">
                <el-option label="全部" value="" />
                <el-option label="未开始" value="not_started" />
                <el-option label="进行中" value="ongoing" />
                <el-option label="已结束" value="ended" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5" class="admin-chat-sessions-filters-actions">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12" style="margin-top: 8px">
          <el-col :span="8">
            <el-form-item label="创建时间">
              <el-date-picker
                v-model="filters.createdAtRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始时间"
                end-placeholder="结束时间"
                value-format=""
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="更新时间">
              <el-date-picker
                v-model="filters.lastUpdatedRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始时间"
                end-placeholder="结束时间"
                value-format=""
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="结束时间">
              <el-date-picker
                v-model="filters.endedAtRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始时间"
                end-placeholder="结束时间"
                value-format=""
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="admin-chat-sessions-table" shadow="never">
      <div class="admin-chat-sessions-toolbar">
        <el-button
          type="danger"
          :disabled="selectedRows.length === 0"
          @click="handleBatchDelete"
        >
          {{ selectedRows.length > 0 ? `批量删除 (${selectedRows.length})` : '批量删除' }}
        </el-button>
      </div>
      <el-table
        ref="tableRef"
        :data="sessions"
        v-loading="loading"
        border
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="id" label="ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="group_id" label="群组 ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="group_name" label="群组名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.group_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="session_title" label="会话标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="创建时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDateTimeToCST(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="最后更新时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDateTimeToCST(row.last_updated) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag
              :type="
                row.ended_at
                  ? 'info'
                  : row.created_at === row.last_updated
                    ? 'warning'
                    : 'success'
              "
            >
              <span v-if="row.ended_at">已结束</span>
              <span v-else-if="row.created_at === row.last_updated">未开始</span>
              <span v-else>进行中</span>
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结束时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDateTimeToCST(row.ended_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="180" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="admin-chat-sessions-pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="createDialogVisible" title="新建会话" width="480px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="96px">
        <el-form-item label="所属群组" prop="group_id">
          <el-select
            v-model="createForm.group_id"
            filterable
            clearable
            placeholder="从下拉中选择或搜索群组"
            :loading="groupLoading"
            style="width: 100%"
          >
            <el-option
              v-for="g in groupOptions"
              :key="g.id"
              :label="`${g.name}（${g.id}）`"
              :value="g.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="会话标题" prop="session_title">
          <el-input v-model="createForm.session_title" placeholder="请输入会话标题" />
        </el-form-item>
        <el-form-item label="开始时间">
          <el-date-picker
            v-model="createForm.created_at"
            type="datetime"
            placeholder="不填则默认为当前时间"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitCreate">创建</el-button>
        </span>
      </template>
    </el-dialog>

    <el-dialog v-model="editDialogVisible" title="编辑会话" width="480px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="96px">
        <el-form-item label="会话标题" prop="session_title">
          <el-input v-model="editForm.session_title" />
        </el-form-item>
        <el-form-item label="会话状态">
          <el-select v-model="editForm.is_active" placeholder="请选择状态" style="width: 100%">
            <el-option label="进行中" :value="true" />
            <el-option label="已结束" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="创建时间">
          <el-date-picker
            v-model="editForm.created_at"
            type="datetime"
            placeholder="留空则不修改"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker
            v-model="editForm.ended_at"
            type="datetime"
            placeholder="留空则不修改"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="editDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitEdit">保存</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-chat-sessions-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-chat-sessions-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.admin-chat-sessions-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.admin-chat-sessions-filters :deep(.el-form-item) {
  margin-bottom: 0;
}

.admin-chat-sessions-filters-form {
  width: 100%;
}

.admin-chat-sessions-filters-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.admin-chat-sessions-table {
  margin-top: 4px;
}

.admin-chat-sessions-toolbar {
  margin-bottom: 8px;
}

.admin-chat-sessions-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>

