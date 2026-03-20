<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { AdminVoiceProfileSummary } from '../../types/admin'
import { batchDeleteAdminVoiceProfiles, listAdminVoiceProfiles } from '../../api/admin/voice-profiles'
import { formatDateTimeToCST } from '../../utils/datetime'
import type { PageMeta } from '../../types/admin'
import { ElMessage, ElMessageBox } from 'element-plus'

interface Filters {
  user_id: string
  has_samples: '' | 'true' | 'false'
  has_embedding: '' | 'true' | 'false'
}

const router = useRouter()
const route = useRoute()

const loading = ref(false)
const profiles = ref<AdminVoiceProfileSummary[]>([])
const meta = ref<PageMeta | null>(null)
const selectedRows = ref<AdminVoiceProfileSummary[]>([])
const batchDeleting = ref(false)
const tableRef = ref<any>(null)

const filters = reactive<Filters>({
  user_id: '',
  has_samples: '',
  has_embedding: '',
})

const page = ref(1)
const pageSize = ref(20)

/** 仅在「筛选/分页/删除成功」等语境变化时调用；不要放在 fetchProfiles 里，否则会与列表二次请求、用户勾选竞态 */
function clearListSelection() {
  selectedRows.value = []
  tableRef.value?.clearSelection?.()
}

async function fetchProfiles() {
  loading.value = true
  try {
    const res = await listAdminVoiceProfiles({
      page: page.value,
      page_size: pageSize.value,
      user_id: filters.user_id || undefined,
      has_samples:
        filters.has_samples === ''
          ? undefined
          : filters.has_samples === 'true'
            ? true
            : false,
      has_embedding:
        filters.has_embedding === ''
          ? undefined
          : filters.has_embedding === 'true'
            ? true
            : false,
    })
    profiles.value = res.items
    meta.value = res.meta
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (err: any) {
    console.error(err)
    ElMessage.error(err?.message || '加载声纹配置列表失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  clearListSelection()
  void fetchProfiles()
}

function handleReset() {
  filters.user_id = ''
  filters.has_samples = ''
  filters.has_embedding = ''
  page.value = 1
  clearListSelection()
  void fetchProfiles()
}

/** 仅用户操作分页时由 @current-change 调用；不要用 v-model，否则接口回写 page 会触发二次 fetch */
function handlePageChange(p: number) {
  page.value = p
  clearListSelection()
  void fetchProfiles()
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  clearListSelection()
  void fetchProfiles()
}

function goDetail(row: AdminVoiceProfileSummary) {
  router.push({
    name: 'AdminVoiceProfileDetail',
    params: { id: row.id },
    query: {
      page: String(page.value),
      page_size: String(pageSize.value),
      ...(filters.user_id ? { user_id: filters.user_id } : {}),
      ...(filters.has_samples ? { has_samples: filters.has_samples } : {}),
      ...(filters.has_embedding ? { has_embedding: filters.has_embedding } : {}),
    },
  })
}

function handleSelectionChange(rows: AdminVoiceProfileSummary[]) {
  selectedRows.value = rows
}

async function handleBatchDelete() {
  const ids = selectedRows.value.map((r) => r.id)
  if (!ids.length) return

  try {
    await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 条声纹配置吗？`, '批量删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }

  batchDeleting.value = true
  try {
    const res = await batchDeleteAdminVoiceProfiles(ids)
    ElMessage.success(`已删除 ${res.deleted} 条声纹配置`)

    clearListSelection()
    await fetchProfiles()
    if (profiles.value.length === 0 && page.value > 1) {
      page.value -= 1
      await fetchProfiles()
    }
  } catch (err: any) {
    console.error(err)
    ElMessage.error(err?.message || '批量删除失败')
  } finally {
    batchDeleting.value = false
  }
}

onMounted(() => {
  const q = route.query
  if (q.page) page.value = Math.max(1, parseInt(String(q.page), 10) || 1)
  if (q.page_size) pageSize.value = Math.max(1, Math.min(100, parseInt(String(q.page_size), 10) || 20))
  if (q.user_id) filters.user_id = String(q.user_id)
  if (q.has_samples === 'true' || q.has_samples === 'false') filters.has_samples = q.has_samples
  if (q.has_embedding === 'true' || q.has_embedding === 'false') filters.has_embedding = q.has_embedding
  void fetchProfiles()
})
</script>

<template>
  <div class="admin-voice-profiles-page">
    <div class="admin-voice-profiles-header">
      <h2 class="admin-voice-profiles-title">用户声纹管理</h2>
    </div>

    <el-card class="admin-voice-profiles-filters" shadow="never">
      <el-form :model="filters" label-width="90px" class="admin-voice-profiles-filters-form">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="用户 ID">
              <el-input v-model="filters.user_id" placeholder="按用户 ID 精确查询" clearable />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="是否有样本">
              <el-select v-model="filters.has_samples" placeholder="全部" clearable>
                <el-option label="全部" value="" />
                <el-option label="有样本" value="true" />
                <el-option label="无样本" value="false" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="是否有声纹">
              <el-select v-model="filters.has_embedding" placeholder="全部" clearable>
                <el-option label="全部" value="" />
                <el-option label="已生成" value="true" />
                <el-option label="未生成" value="false" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6" class="admin-voice-profiles-filters-actions">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="admin-voice-profiles-table" shadow="never">
      <div class="admin-voice-profiles-actions">
        <el-button
          type="danger"
          :disabled="!selectedRows.length || batchDeleting"
          :loading="batchDeleting"
          @click="handleBatchDelete"
        >
          批量删除
        </el-button>
      </div>
      <el-table
        ref="tableRef"
        :data="profiles"
        row-key="id"
        v-loading="loading"
        border
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column label="用户" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.user_name">
              {{ row.user_name }} <span class="user-email">（{{ row.user_email || row.user_id }}）</span>
            </span>
            <span v-else>
              {{ row.user_email || row.user_id }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="user_id" label="用户 ID" min-width="160" show-overflow-tooltip />
        <el-table-column label="当前小组" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.primary_group_id">
              {{ row.primary_group_id }} / {{ row.primary_group_name || '未命名小组' }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="sample_count" label="样本数量" width="100" />
        <el-table-column label="声纹状态" width="120">
          <template #default="{ row }">
            <el-tag
              v-if="row.has_embedding"
              type="success"
              size="small"
              effect="light"
            >
              已生成
            </el-tag>
            <el-tag
              v-else
              type="info"
              size="small"
              effect="light"
            >
              未生成
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatDateTimeToCST(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="goDetail(row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="admin-voice-profiles-pagination">
        <el-pagination
          v-if="meta"
          :current-page="page"
          :page-size="pageSize"
          :total="meta.total"
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
.admin-voice-profiles-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-voice-profiles-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.admin-voice-profiles-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.admin-voice-profiles-filters-form {
  width: 100%;
}

.admin-voice-profiles-filters-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.admin-voice-profiles-table {
  margin-top: 4px;
}

.admin-voice-profiles-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.admin-voice-profiles-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.user-email {
  color: #6b7280;
  font-size: 12px;
}
</style>

