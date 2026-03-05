<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminGroup, AdminMembership, AdminUser } from '../../types/admin'
import { listAdminMemberships, updateAdminMembership, deleteAdminMembership, createAdminMembership } from '../../api/admin/memberships'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminUsers } from '../../api/admin/users'

interface Filters {
  group_id: string
  user_id: string
  status: string
  createdAtRange: Date[] | []
}

const loading = ref(false)
const memberships = ref<AdminMembership[]>([])

const filters = reactive<Filters>({
  group_id: '',
  user_id: '',
  status: '',
  createdAtRange: [],
})

const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const createDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive({
  group_id: '',
  user_id: '',
  role: 'member',
  status: 'active',
})

const groupOptions = ref<AdminGroup[]>([])
const groupLoading = ref(false)
const userOptions = ref<AdminUser[]>([])
const userLoading = ref(false)

const createRules: FormRules<typeof createForm> = {
  group_id: [{ required: true, message: '请输入群组 ID', trigger: 'blur' }],
  user_id: [{ required: true, message: '请输入用户 ID', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
}

const editDialogVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({
  id: '',
  role: '',
  status: '',
})

const editRules: FormRules<typeof editForm> = {
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
}

async function fetchMemberships() {
  loading.value = true
  try {
    const [from, to] = filters.createdAtRange.length === 2 ? filters.createdAtRange : [undefined, undefined]
    const res = await listAdminMemberships({
      page: page.value,
      page_size: pageSize.value,
      group_id: filters.group_id || undefined,
      user_id: filters.user_id || undefined,
      status: filters.status || undefined,
      created_from: from ? from.toISOString() : undefined,
      created_to: to ? to.toISOString() : undefined,
    })
    memberships.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '加载成员关系列表失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchMemberships()
}

function handleReset() {
  filters.group_id = ''
  filters.user_id = ''
  filters.status = ''
  filters.createdAtRange = []
  page.value = 1
  fetchMemberships()
}

function handlePageChange(p: number) {
  page.value = p
  fetchMemberships()
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  fetchMemberships()
}

function openCreateDialog() {
  createForm.group_id = ''
  createForm.user_id = ''
  createForm.role = 'member'
  createForm.status = 'active'
  // 预先加载一批群组和用户，先下拉再在下拉内搜索
  loadInitialGroupOptions()
  loadInitialUserOptions()
  createDialogVisible.value = true
}

async function loadInitialGroupOptions() {
  groupLoading.value = true
  try {
    const res = await listAdminGroups({
      page: 1,
      page_size: 20,
      name: undefined,
    })
    groupOptions.value = res.items
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '搜索群组失败')
  } finally {
    groupLoading.value = false
  }
}

async function loadInitialUserOptions() {
  userLoading.value = true
  try {
    const res = await listAdminUsers({
      page: 1,
      page_size: 20,
      email: undefined,
      name: undefined,
    })
    userOptions.value = res.items
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '搜索用户失败')
  } finally {
    userLoading.value = false
  }
}

function openEditDialog(row: AdminMembership) {
  editForm.id = row.id
  editForm.role = row.role
  editForm.status = row.status
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      await updateAdminMembership(editForm.id, {
        role: editForm.role,
        status: editForm.status,
      })
      ElMessage.success('更新成员关系成功')
      editDialogVisible.value = false
      fetchMemberships()
    } catch (e: any) {
      console.error(e)
      ElMessage.error(e?.message || '更新成员关系失败')
    }
  })
}

async function submitCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      await createAdminMembership({
        group_id: createForm.group_id,
        user_id: createForm.user_id,
        role: createForm.role as 'leader' | 'member',
        status: createForm.status as 'active' | 'left' | 'kicked',
      })
      ElMessage.success('创建成员关系成功')
      createDialogVisible.value = false
      // 默认用当前筛选条件刷新；若当前未筛选，可根据需要设置为新建的 group_id/user_id
      if (!filters.group_id) {
        filters.group_id = createForm.group_id
      }
      if (!filters.user_id) {
        filters.user_id = createForm.user_id
      }
      page.value = 1
      fetchMemberships()
    } catch (e: any) {
      console.error(e)
      const msg = e?.response?.data?.detail || e?.message || '创建成员关系失败'
      ElMessage.error(msg)
    }
  })
}

async function handleDelete(row: AdminMembership) {
  try {
    await ElMessageBox.confirm(
      `确认删除成员关系（group_id=${row.group_id}, user_id=${row.user_id}）吗？该操作不可恢复。`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      },
    )
  } catch {
    return
  }

  try {
    await deleteAdminMembership(row.id)
    ElMessage.success('删除成员关系成功')
    if (memberships.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    fetchMemberships()
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '删除成员关系失败')
  }
}

onMounted(() => {
  fetchMemberships()
})
</script>

<template>
  <div class="admin-memberships-page">
    <div class="admin-memberships-header">
      <h2 class="admin-memberships-title">成员关系管理</h2>
      <el-button type="primary" @click="openCreateDialog">新建成员关系</el-button>
    </div>

    <el-card class="admin-memberships-filters" shadow="never">
      <el-form :model="filters" label-width="96px" class="admin-memberships-filters-form">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="群组 ID">
              <el-input v-model="filters.group_id" placeholder="按群组 ID 精确查询" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="用户 ID">
              <el-input v-model="filters.user_id" placeholder="按用户 ID 精确查询" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="成员状态">
              <el-select v-model="filters.status" placeholder="全部" clearable style="width: 100%">
                <el-option label="全部" value="" />
                <el-option label="有效 (active)" value="active" />
                <el-option label="已退出 (left)" value="left" />
                <el-option label="被移除 (kicked)" value="kicked" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="7">
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
        </el-row>
        <el-row :gutter="12" class="admin-memberships-filters-actions-row">
          <el-col :span="24" class="admin-memberships-filters-actions">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="admin-memberships-table" shadow="never">
      <el-table :data="memberships" v-loading="loading" border style="width: 100%">
        <el-table-column prop="id" label="ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="group_id" label="群组 ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="user_id" label="用户 ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="role" label="角色" min-width="120">
          <template #default="{ row }">
            <el-tag :type="row.role === 'leader' ? 'warning' : 'info'">
              {{ row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" min-width="140">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : row.status === 'kicked' ? 'danger' : 'info'">
              <span v-if="row.status === 'active'">有效 (active)</span>
              <span v-else-if="row.status === 'left'">已退出 (left)</span>
              <span v-else-if="row.status === 'kicked'">被移除 (kicked)</span>
              <span v-else>{{ row.status }}</span>
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" min-width="180" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="admin-memberships-pagination">
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

    <el-dialog v-model="createDialogVisible" title="新建成员关系" width="460px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="96px">
        <el-form-item label="群组 ID" prop="group_id">
          <el-select
            v-model="createForm.group_id"
            filterable
            clearable
            placeholder="从下拉中选择或搜索群组"
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
        <el-form-item label="用户 ID" prop="user_id">
          <el-select
            v-model="createForm.user_id"
            filterable
            clearable
            placeholder="从下拉中选择或搜索用户"
            style="width: 100%"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :label="`${u.name || u.email}（${u.email} / ${u.id}）`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="createForm.role" placeholder="请选择角色" style="width: 100%">
            <el-option label="群主 / 负责人 (leader)" value="leader" />
            <el-option label="普通成员 (member)" value="member" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="createForm.status" placeholder="请选择状态" style="width: 100%">
            <el-option label="有效 (active)" value="active" />
            <el-option label="已退出 (left)" value="left" />
            <el-option label="被移除 (kicked)" value="kicked" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitCreate">创建</el-button>
        </span>
      </template>
    </el-dialog>

    <el-dialog v-model="editDialogVisible" title="编辑成员关系" width="420px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="80px">
        <el-form-item label="角色" prop="role">
          <el-select v-model="editForm.role" placeholder="请选择角色" style="width: 100%">
            <el-option label="群主 / 负责人 (leader)" value="leader" />
            <el-option label="普通成员 (member)" value="member" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-select v-model="editForm.status" placeholder="请选择状态" style="width: 100%">
            <el-option label="有效 (active)" value="active" />
            <el-option label="已退出 (left)" value="left" />
            <el-option label="被移除 (kicked)" value="kicked" />
          </el-select>
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
.admin-memberships-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-memberships-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.admin-memberships-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.admin-memberships-filters :deep(.el-form-item) {
  margin-bottom: 0;
}

.admin-memberships-filters-form {
  width: 100%;
}

.admin-memberships-filters-actions-row {
  margin-top: 8px;
}

.admin-memberships-filters-actions {
  display: flex;
  justify-content: flex-end;
}

.admin-memberships-table {
  margin-top: 4px;
}

.admin-memberships-pagination {
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

