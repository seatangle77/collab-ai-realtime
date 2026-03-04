<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { AdminUser } from '../../types/admin'
import { listAdminUsers } from '../../api/admin/users'

interface Filters {
  email: string
  name: string
}

const loading = ref(false)
const users = ref<AdminUser[]>([])

const filters = reactive<Filters>({
  email: '',
  name: '',
})

const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

async function fetchUsers() {
  loading.value = true
  try {
    const res = await listAdminUsers({
      page: page.value,
      page_size: pageSize.value,
      email: filters.email || undefined,
      name: filters.name || undefined,
    })
    users.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e) {
    console.error(e)
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

onMounted(() => {
  fetchUsers()
})
</script>

<template>
  <div class="admin-users-page">
    <div class="admin-users-header">
      <h2 class="admin-users-title">用户管理</h2>
    </div>

    <el-card class="admin-users-filters" shadow="never">
      <el-form :inline="true" :model="filters" label-width="64px">
        <el-form-item label="邮箱">
          <el-input v-model="filters.email" placeholder="按邮箱模糊搜索" clearable />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="filters.name" placeholder="按姓名模糊搜索" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
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

.admin-users-table {
  margin-top: 4px;
}

.admin-users-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>

