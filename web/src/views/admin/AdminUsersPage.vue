<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminUser } from '../../types/admin'
import { listAdminUsers, deleteAdminUser, updateAdminUser } from '../../api/admin/users'
import { registerUser } from '../../api/auth'

interface Filters {
  email: string
  name: string
  id: string
  device_token: string
  createdAtRange: Date[] | []
}

const loading = ref(false)
const users = ref<AdminUser[]>([])

const filters = reactive<Filters>({
  email: '',
  name: '',
  id: '',
  device_token: '',
  createdAtRange: [],
})

const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

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
  password: [{ required: true, message: '请输入初始密码', trigger: 'blur' }],
}

const editRules: FormRules<typeof editForm> = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
}

async function fetchUsers() {
  loading.value = true
  try {
    const [from, to] = filters.createdAtRange.length === 2 ? filters.createdAtRange : [undefined, undefined]
    const res = await listAdminUsers({
      page: page.value,
      page_size: pageSize.value,
      email: filters.email || undefined,
      name: filters.name || undefined,
      id: filters.id || undefined,
      device_token: filters.device_token || undefined,
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
  page.value = 1
  fetchUsers()
}

function handleReset() {
  filters.email = ''
  filters.name = ''
  filters.id = ''
  filters.device_token = ''
  filters.createdAtRange = []
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

    <el-card class="admin-users-filters" shadow="never">
      <el-form :model="filters" label-width="84px" class="admin-users-filters-form">
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
            <el-form-item label="设备 Token">
              <el-input v-model="filters.device_token" placeholder="按设备 Token 模糊搜索" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12" class="admin-users-filters-row-bottom">
          <el-col :span="10">
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
          <el-col :span="14" class="admin-users-filters-actions">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="admin-users-table" shadow="never">
      <el-table :data="users" v-loading="loading" border style="width: 100%">
        <el-table-column prop="id" label="ID" min-width="220" show-overflow-tooltip />
        <el-table-column prop="name" label="姓名" min-width="120" show-overflow-tooltip />
        <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
        <el-table-column prop="device_token" label="设备 Token" min-width="220" show-overflow-tooltip />
        <el-table-column
          prop="created_at"
          label="创建时间"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column label="操作" min-width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
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
          <el-input v-model="createForm.password" type="password" show-password />
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
}

.admin-users-table {
  margin-top: 4px;
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

