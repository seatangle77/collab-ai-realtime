<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminUser } from '../../types/admin'
import { listAdminUsers, deleteAdminUser, deleteAdminUsersBatch, updateAdminUser } from '../../api/admin/users'
import { registerUser } from '../../api/auth'
import { formatDateTimeToCST } from '../../utils/datetime'
import { exportRowsToCsv } from '../../utils/csv'

interface Filters {
  email: string
  name: string
  id: string
  device_token: string
  createdAtRange: Date[] | []
  group_name: string
  group_id: string
}

const loading = ref(false)
const users = ref<AdminUser[]>([])

const filters = reactive<Filters>({
  email: '',
  name: '',
  id: '',
  device_token: '',
  createdAtRange: [],
  group_name: '',
  group_id: '',
})

const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminUser[]>([])

const filterCardRef = ref<HTMLElement | { $el?: HTMLElement } | null>(null)

// 新建 / 编辑弹窗相关
const createDialogVisible = ref(false)
const editDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const editFormRef = ref<FormInstance>()

const createForm = reactive({
  name: '',
  email: '',
  password: '',
  device_token: '',
})

const editForm = reactive({
  id: '',
  name: '',
  email: '',
  device_token: '' as string | null,
})

const createRules: FormRules<typeof createForm> = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: ['blur', 'change'] },
  ],
  password: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (!value || value.length !== 4) {
          callback(new Error('密码必须为 4 位'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

const editRules: FormRules<typeof editForm> = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
}

function _createdAtBounds(): { from?: Date; to?: Date } {
  const range = filters.createdAtRange
  if (!range || !Array.isArray(range)) return {}
  const from = range[0]
  const to = range[1]
  const fromDate = from instanceof Date && !Number.isNaN(from.getTime()) ? from : null
  const toDate = to instanceof Date && !Number.isNaN(to.getTime()) ? to : null
  return { from: fromDate ?? undefined, to: toDate ?? undefined }
}

async function fetchUsers() {
  loading.value = true
  try {
    const { from, to } = _createdAtBounds()
    const res = await listAdminUsers({
      page: page.value,
      page_size: pageSize.value,
      email: filters.email || undefined,
      name: filters.name || undefined,
      id: filters.id || undefined,
      device_token: filters.device_token || undefined,
      group_name: filters.group_name || undefined,
      group_id: filters.group_id || undefined,
      created_from: from ? from.toISOString() : undefined,
      created_to: to ? to.toISOString() : undefined,
    })
    users.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '加载用户列表失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  // 点击查询时从 DOM 同步筛选条件，保证 E2E 用 fill() 填写的值能被带上（fill 不触发 v-model）
  const cardEl = (filterCardRef.value as { $el?: HTMLElement } | null)?.$el ?? filterCardRef.value
  if (cardEl && cardEl instanceof HTMLElement) {
    const byPlaceholder = (p: string) =>
      cardEl.querySelector<HTMLInputElement>(`[placeholder="${p}"]`)?.value?.trim() ?? ''
    filters.id = byPlaceholder('按用户 ID 精确查询')
    filters.email = byPlaceholder('按邮箱模糊搜索')
    filters.name = byPlaceholder('按姓名模糊搜索')
    filters.device_token = byPlaceholder('按设备 Token 模糊搜索')
    filters.group_id = byPlaceholder('按小组 ID 精确查询')
    filters.group_name = byPlaceholder('按小组名称模糊搜索')

    const startInput = cardEl.querySelector<HTMLInputElement>('[placeholder="开始"]')
    const endInput = cardEl.querySelector<HTMLInputElement>('[placeholder="结束"]')
    if (startInput?.value?.trim() && endInput?.value?.trim()) {
      try {
        const parseAsUtcIfNeeded = (s: string): Date => {
          const t = s.trim().replace(' ', 'T')
          const withTz = /Z|[+-]\d{2}:?\d{2}$/.test(t) ? t : `${t}Z`
          return new Date(withTz)
        }
        const start = parseAsUtcIfNeeded(startInput.value)
        const end = parseAsUtcIfNeeded(endInput.value)
        if (!Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime())) {
          filters.createdAtRange = [start, end]
        }
      } catch {
        // ignore parse error
      }
    }
  }
  page.value = 1
  fetchUsers()
}

function handleReset() {
  filters.email = ''
  filters.name = ''
  filters.id = ''
  filters.device_token = ''
  filters.createdAtRange = []
  filters.group_name = ''
  filters.group_id = ''
  page.value = 1
  fetchUsers()
}

function handlePageChange(p: number) {
  page.value = p
  fetchUsers()
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  fetchUsers()
}

function openCreateDialog() {
  createForm.name = ''
  createForm.email = ''
  createForm.password = ''
  createForm.device_token = ''
  createDialogVisible.value = true
}

async function submitCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      await registerUser({
        name: createForm.name,
        email: createForm.email,
        password: createForm.password,
        device_token: createForm.device_token || undefined,
      })
      ElMessage.success('创建用户成功')
      createDialogVisible.value = false
      fetchUsers()
    } catch (e: any) {
      console.error(e)
      ElMessage.error(e?.message || '创建用户失败')
    }
  })
}

function openEditDialog(row: AdminUser) {
  editForm.id = row.id
  editForm.name = row.name
  editForm.email = row.email
  editForm.device_token = row.device_token
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      await updateAdminUser(editForm.id, {
        name: editForm.name,
        device_token: editForm.device_token ?? null,
      })
      ElMessage.success('更新用户成功')
      editDialogVisible.value = false
      fetchUsers()
    } catch (e: any) {
      console.error(e)
      ElMessage.error(e?.message || '更新用户失败')
    }
  })
}

function handleSelectionChange(rows: AdminUser[]) {
  selectedRows.value = rows
}

async function handleBatchDelete() {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除已选 ${selectedRows.value.length} 条用户记录吗？该操作不可恢复。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const ids = selectedRows.value.map((r) => r.id)
    const res = await deleteAdminUsersBatch(ids)
    ElMessage.success(`成功删除 ${res.deleted} 条用户`)
    tableRef.value?.clearSelection?.()
    if (users.value.length === selectedRows.value.length && page.value > 1) {
      page.value -= 1
    }
    fetchUsers()
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '批量删除用户失败')
  }
}

function handleExportSelectedCsv() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选择要导出的用户')
    return
  }

  const now = new Date()
  const ts = now.toISOString().slice(0, 19).replace(/[:T]/g, '-')
  const filename = `用户管理-选中导出-${ts}.csv`

  exportRowsToCsv<AdminUser>({
    filename,
    columns: [
      { key: 'id', title: 'ID' },
      { key: 'name', title: '姓名' },
      { key: 'email', title: '邮箱' },
      {
        key: 'device_token',
        title: '设备 Token',
        format: (row) => row.device_token ?? '',
      },
      {
        key: 'group_ids',
        title: '小组 ID',
        format: (row) => (row.group_ids?.length ? row.group_ids.join(', ') : ''),
      },
      {
        key: 'group_names',
        title: '小组名称',
        format: (row) => (row.group_names?.length ? row.group_names.join(', ') : ''),
      },
      {
        key: 'created_at',
        title: '创建时间',
        format: (row) => formatDateTimeToCST(row.created_at),
      },
    ],
    rows: selectedRows.value,
  })
}

async function handleDelete(row: AdminUser) {
  try {
    await ElMessageBox.confirm(`确认删除用户「${row.name || row.email}」吗？该操作不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await deleteAdminUser(row.id)
    ElMessage.success('删除用户成功')
    if (users.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    fetchUsers()
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '删除用户失败')
  }
}

async function handleImpersonate(row: AdminUser) {
  try {
    const { impersonateUser } = await import('../../api/admin/users')
    const res = await impersonateUser(row.id)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('app_access_token', res.access_token)
      window.open('/app', '_blank')
    }
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '以该用户身份打开 App 失败')
  }
}

async function handleMarkPasswordReset(row: AdminUser) {
  try {
    await ElMessageBox.confirm(
      `确认要求用户「${row.name || row.email}」下次登录时修改密码吗？`,
      '标记修改密码',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  try {
    const { markUserPasswordReset } = await import('../../api/admin/users')
    await markUserPasswordReset(row.id)
    ElMessage.success('已标记该用户下次登录必须修改密码')
    fetchUsers()
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '标记用户下次必须修改密码失败')
  }
}

onMounted(() => {
  fetchUsers()
})
</script>

<template>
  <div class="admin-users-page">
    <div class="admin-users-header">
      <h2 class="admin-users-title">用户管理</h2>
      <el-button type="primary" @click="openCreateDialog">新建用户</el-button>
    </div>

    <el-card ref="filterCardRef" class="admin-users-filters" shadow="never">
      <el-form :model="filters" label-width="72px" class="admin-users-filters-form">
        <!-- 第一行：用户维度 -->
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="ID">
              <el-input v-model="filters.id" placeholder="按用户 ID 精确查询" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="邮箱">
              <el-input v-model="filters.email" placeholder="按邮箱模糊搜索" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="姓名">
              <el-input v-model="filters.name" placeholder="按姓名模糊搜索" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="设备">
              <el-input v-model="filters.device_token" placeholder="按设备 Token 模糊搜索" clearable />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 第二行：小组维度 + 时间 + 按钮 -->
        <el-row :gutter="12" class="admin-users-filters-row-bottom">
          <el-col :span="6">
            <el-form-item label="小组 ID">
              <el-input v-model="filters.group_id" placeholder="按小组 ID 精确查询" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="小组名称">
              <el-input v-model="filters.group_name" placeholder="按小组名称模糊搜索" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="创建时间">
              <el-date-picker
                v-model="filters.createdAtRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始"
                end-placeholder="结束"
                value-format=""
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="4" class="admin-users-filters-actions">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="admin-users-table" shadow="never">
      <div class="admin-users-toolbar">
        <el-button
          type="primary"
          :disabled="selectedRows.length === 0"
          @click="handleExportSelectedCsv"
        >
          {{ selectedRows.length > 0 ? `导出选中 (${selectedRows.length})` : '导出选中' }}
        </el-button>
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
        :data="users"
        v-loading="loading"
        border
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="id" label="ID" min-width="220" show-overflow-tooltip />
        <el-table-column prop="name" label="姓名" min-width="120" show-overflow-tooltip />
        <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
        <el-table-column prop="device_token" label="设备 Token" min-width="220" show-overflow-tooltip />
        <el-table-column label="小组 ID" min-width="220">
          <template #default="{ row }">
            <span v-if="row.group_ids?.length">
              {{ row.group_ids.join(', ') }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="小组名称" min-width="220">
          <template #default="{ row }">
            <span v-if="row.group_names?.length">
              {{ row.group_names.join(', ') }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="密码状态" min-width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.password_needs_reset"
              type="warning"
              effect="light"
              size="small"
            >
              需修改
            </el-tag>
            <el-tag
              v-else
              type="success"
              effect="light"
              size="small"
            >
              正常
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDateTimeToCST(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="260" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
            <el-button type="primary" link size="small" @click="handleImpersonate(row)">以此身份打开 App</el-button>
            <el-button type="warning" link size="small" @click="handleMarkPasswordReset(row)">要求修改密码</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="admin-users-pagination">
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

    <!-- 新建用户 -->
    <el-dialog v-model="createDialogVisible" title="新建用户" width="420px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <el-form-item label="姓名" prop="name">
          <el-input v-model="createForm.name" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="createForm.email" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="4 位密码" />
        </el-form-item>
        <el-form-item label="设备 Token">
          <el-input v-model="createForm.device_token" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitCreate">创建</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 编辑用户 -->
    <el-dialog v-model="editDialogVisible" title="编辑用户" width="420px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="80px">
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" disabled />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="设备 Token">
          <el-input v-model="editForm.device_token" />
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
.admin-users-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-users-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.admin-users-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.admin-users-filters :deep(.el-form-item) {
  margin-bottom: 0;
}

.admin-users-filters-form {
  width: 100%;
}

.admin-users-filters-row-bottom {
  margin-top: 8px;
}

.admin-users-filters-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.admin-users-table {
  margin-top: 4px;
}

.admin-users-toolbar {
  margin-bottom: 8px;
}

.admin-users-pagination {
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

