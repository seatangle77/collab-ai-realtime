<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AdminGroup } from '../../types/admin'
import { listAdminGroups, deleteAdminGroup, deleteAdminGroupsBatch, updateAdminGroup, createAdminGroup } from '../../api/admin/groups'
import { formatDateTimeToCST } from '../../utils/datetime'
import { exportRowsToCsv } from '../../utils/csv'

interface Filters {
  name: string
  is_active: '' | boolean
  createdAtRange: Date[] | []
}

const loading = ref(false)
const groups = ref<AdminGroup[]>([])

const filters = reactive<Filters>({
  name: '',
  is_active: '',
  createdAtRange: [],
})

const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selectedRows = ref<AdminGroup[]>([])

const editDialogVisible = ref(false)
const editFormRef = ref<FormInstance>()
const editForm = reactive({
  id: '',
  name: '',
  is_active: true,
})

const editRules: FormRules<typeof editForm> = {
  name: [{ required: true, message: '请输入群组名称', trigger: 'blur' }],
}

const createDialogVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive({
  name: '',
  is_active: true,
})

const createRules: FormRules<typeof createForm> = {
  name: [{ required: true, message: '请输入群组名称', trigger: 'blur' }],
}

async function fetchGroups() {
  loading.value = true
  try {
    const [from, to] = filters.createdAtRange.length === 2 ? filters.createdAtRange : [undefined, undefined]
    const res = await listAdminGroups({
      page: page.value,
      page_size: pageSize.value,
      name: filters.name || undefined,
      is_active: filters.is_active === '' ? undefined : filters.is_active,
      created_from: from ? from.toISOString() : undefined,
      created_to: to ? to.toISOString() : undefined,
    })
    groups.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '加载群组列表失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchGroups()
}

function handleReset() {
  filters.name = ''
  filters.is_active = ''
  filters.createdAtRange = []
  page.value = 1
  fetchGroups()
}

function handlePageChange(p: number) {
  page.value = p
  fetchGroups()
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  fetchGroups()
}

function openCreateDialog() {
  createForm.name = ''
  createForm.is_active = true
  createDialogVisible.value = true
}

function openEditDialog(row: AdminGroup) {
  editForm.id = row.id
  editForm.name = row.name
  editForm.is_active = row.is_active
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      await updateAdminGroup(editForm.id, {
        name: editForm.name,
        is_active: editForm.is_active,
      })
      ElMessage.success('更新群组成功')
      editDialogVisible.value = false
      fetchGroups()
    } catch (e: any) {
      console.error(e)
      ElMessage.error(e?.message || '更新群组失败')
    }
  })
}

async function submitCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      await createAdminGroup({
        name: createForm.name,
        is_active: createForm.is_active,
      })
      ElMessage.success('创建群组成功')
      createDialogVisible.value = false
      page.value = 1
      fetchGroups()
    } catch (e: any) {
      console.error(e)
      ElMessage.error(e?.message || '创建群组失败')
    }
  })
}

function handleSelectionChange(rows: AdminGroup[]) {
  selectedRows.value = rows
}

async function handleBatchDelete() {
  if (selectedRows.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除已选 ${selectedRows.value.length} 条群组记录吗？该操作不可恢复。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const ids = selectedRows.value.map((r) => r.id)
    const res = await deleteAdminGroupsBatch(ids)
    ElMessage.success(`成功删除 ${res.deleted} 条群组`)
    tableRef.value?.clearSelection?.()
    if (groups.value.length === selectedRows.value.length && page.value > 1) {
      page.value -= 1
    }
    fetchGroups()
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '批量删除群组失败')
  }
}

function handleExportSelectedCsv() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选择要导出的群组')
    return
  }

  const now = new Date()
  const ts = now.toISOString().slice(0, 19).replace(/[:T]/g, '-')
  const filename = `群组管理-选中导出-${ts}.csv`

  exportRowsToCsv<AdminGroup>({
    filename,
    columns: [
      { key: 'id', title: 'ID' },
      { key: 'name', title: '名称' },
      {
        key: 'created_at',
        title: '创建时间',
        format: (row) => formatDateTimeToCST(row.created_at),
      },
      {
        key: 'is_active',
        title: '状态',
        format: (row) => (row.is_active ? '启用' : '停用'),
      },
    ],
    rows: selectedRows.value,
  })
}

async function handleDelete(row: AdminGroup) {
  try {
    await ElMessageBox.confirm(`确认删除群组「${row.name}」吗？该操作不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  try {
    await deleteAdminGroup(row.id)
    ElMessage.success('删除群组成功')
    if (groups.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    fetchGroups()
  } catch (e: any) {
    console.error(e)
    ElMessage.error(e?.message || '删除群组失败')
  }
}

const router = useRouter()

onMounted(() => {
  fetchGroups()
})
</script>

<template>
  <div class="admin-groups-page">
    <div class="admin-groups-header">
      <h2 class="admin-groups-title">群组管理</h2>
      <el-button type="primary" @click="openCreateDialog">新建群组</el-button>
    </div>

    <el-card class="admin-groups-filters" shadow="never">
      <el-form :model="filters" label-width="84px" class="admin-groups-filters-form">
        <el-row :gutter="12">
          <el-col :span="5">
            <el-form-item label="名称">
              <el-input v-model="filters.name" placeholder="按群组名称模糊搜索" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="状态">
              <el-select v-model="filters.is_active" placeholder="全部" clearable style="width: 100%">
                <el-option label="全部" value="" />
                <el-option label="启用" :value="true" />
                <el-option label="停用" :value="false" />
              </el-select>
            </el-form-item>
          </el-col>
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
          <el-col :span="6" class="admin-groups-filters-actions">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="admin-groups-table" shadow="never">
      <div class="admin-groups-toolbar">
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
        :data="groups"
        v-loading="loading"
        border
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="id" label="ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="创建时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDateTimeToCST(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="router.push('/admin/groups/' + row.id)">详情</el-button>
            <el-button type="primary" link size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="admin-groups-pagination">
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

    <el-dialog v-model="editDialogVisible" title="编辑群组" width="420px">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="editForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="editDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitEdit">保存</el-button>
        </span>
      </template>
    </el-dialog>

    <el-dialog v-model="createDialogVisible" title="新建群组" width="420px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="createForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="createDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="submitCreate">创建</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-groups-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-groups-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.admin-groups-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.admin-groups-filters :deep(.el-form-item) {
  margin-bottom: 0;
}

.admin-groups-filters-form {
  width: 100%;
}

.admin-groups-filters-actions {
  display: flex;
  align-items: center;
}

.admin-groups-table {
  margin-top: 4px;
}

.admin-groups-toolbar {
  margin-bottom: 8px;
}

.admin-groups-pagination {
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
