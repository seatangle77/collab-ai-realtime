<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listQuestionnaireEntries,
  deleteQuestionnaireEntry,
  type QuestionnaireEntryAdmin,
} from '../../api/admin/questionnaire-entries'
import { listAdminGroups } from '../../api/admin/groups'
import { fetchScaleMeta, type ScaleMeta } from '../../api/appQuestionnaire'
import type { AdminGroup } from '../../types/admin'

const CONDITION_LABELS: Record<string, string> = {
  no_assistance: '无辅助',
  glasses: '智能眼镜',
  app_notification: 'APP 通知',
}

const loading = ref(false)
const rows = ref<QuestionnaireEntryAdmin[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const meta = ref<ScaleMeta | null>(null)
const groups = ref<AdminGroup[]>([])

const drawerVisible = ref(false)
const drawerEntry = ref<QuestionnaireEntryAdmin | null>(null)
const drawerTab = ref<'srcc' | 'pcs'>('srcc')

const filters = reactive({
  group_id: '',
  condition: '',
  updatedRange: [] as Date[],
})

async function fetchData() {
  loading.value = true
  try {
    const [from, to] = filters.updatedRange.length === 2 ? filters.updatedRange : [undefined, undefined]
    const res = await listQuestionnaireEntries({
      page: page.value,
      page_size: pageSize.value,
      group_id: filters.group_id || undefined,
      condition: filters.condition || undefined,
      updated_from: from ? from.toISOString() : undefined,
      updated_to: to ? to.toISOString() : undefined,
    })
    rows.value = res.items
    total.value = res.meta.total
    page.value = res.meta.page
    pageSize.value = res.meta.page_size
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadGroups() {
  try {
    const res = await listAdminGroups({ page_size: 200 })
    groups.value = res.items
  } catch {
    // ignore
  }
}

function handleSearch() { page.value = 1; fetchData() }
function handleReset() {
  filters.group_id = ''
  filters.condition = ''
  filters.updatedRange = []
  page.value = 1
  fetchData()
}
function handlePageChange(p: number) { page.value = p; fetchData() }
function handlePageSizeChange(s: number) { pageSize.value = s; page.value = 1; fetchData() }

async function handleDelete(row: QuestionnaireEntryAdmin) {
  try {
    await ElMessageBox.confirm(
      `确定删除用户「${row.user_name || row.user_id}」的问卷记录？`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
  } catch { return }
  try {
    await deleteQuestionnaireEntry(row.user_id)
    ElMessage.success('已删除')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    fetchData()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

function openDrawer(row: QuestionnaireEntryAdmin) {
  drawerEntry.value = row
  drawerTab.value = 'srcc'
  drawerVisible.value = true
}

function srccItemsByDimension() {
  if (!meta.value) return []
  return Object.keys(meta.value.srcc_dimensions).map((dim) => ({
    dim,
    label: meta.value!.srcc_dimensions[dim],
    items: meta.value!.srcc_items.filter((i) => i.dimension === dim),
  }))
}

function statusTag(row: QuestionnaireEntryAdmin, scale: 'srcc' | 'pcs') {
  const responses = scale === 'srcc' ? row.srcc_responses : row.pcs_responses
  if (!responses) return { label: '未填写', type: 'info' }
  const items = scale === 'srcc' ? meta.value?.srcc_items : meta.value?.pcs_items
  if (!items) return { label: '已填写', type: 'success' }
  const filled = items.filter((i) => responses[i.id] != null).length
  if (filled === items.length) return { label: `完成 ${items.length}/${items.length}`, type: 'success' }
  return { label: `${filled}/${items.length} 题`, type: 'warning' }
}

function formatTime(ts: string | null) {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN', { hour12: false })
}

function avg(val: number | null | undefined) {
  if (val == null) return '-'
  return val.toFixed(2)
}

onMounted(() => {
  Promise.all([fetchData(), fetchScaleMeta().then((m) => { meta.value = m }), loadGroups()])
})
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">量表填写记录</h2>
    </div>

    <el-card shadow="never">
      <el-form :model="filters" label-width="80px">
        <el-row :gutter="12">
          <el-col :span="6">
            <el-form-item label="群组">
              <el-select v-model="filters.group_id" placeholder="全部群组" clearable style="width: 100%">
                <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="5">
            <el-form-item label="实验条件">
              <el-select v-model="filters.condition" placeholder="全部" clearable style="width: 100%">
                <el-option v-for="(label, val) in CONDITION_LABELS" :key="val" :label="label" :value="val" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="9">
            <el-form-item label="更新时间">
              <el-date-picker
                v-model="filters.updatedRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始"
                end-placeholder="结束"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="4">
            <el-form-item label=" ">
              <el-button type="primary" @click="handleSearch">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading" border style="width: 100%" empty-text="暂无数据">
        <el-table-column label="用户" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="cell-name">{{ row.user_name || '-' }}</div>
            <div class="cell-sub">{{ row.user_id }}</div>
          </template>
        </el-table-column>
        <el-table-column label="群组" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="cell-name">{{ row.group_name || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="实验条件" width="120">
          <template #default="{ row }">
            <el-tag size="small" type="info">
              {{ CONDITION_LABELS[row.condition] || row.condition || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="SRCC" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTag(row, 'srcc').type as any">
              {{ statusTag(row, 'srcc').label }}
            </el-tag>
            <div v-if="row.srcc_result?.total_avg != null" class="cell-avg">
              均分 {{ avg(row.srcc_result.total_avg) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="PCS" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTag(row, 'pcs').type as any">
              {{ statusTag(row, 'pcs').label }}
            </el-tag>
            <div v-if="row.pcs_result?.total_avg != null" class="cell-avg">
              均分 {{ avg(row.pcs_result.total_avg) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="最后更新" width="170">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openDrawer(row)">详情</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
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

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="问卷详情" size="520px" destroy-on-close>
      <template v-if="drawerEntry && meta">
        <div class="drawer-user-info">
          <span class="drawer-user-name">{{ drawerEntry.user_name || drawerEntry.user_id }}</span>
          <el-tag size="small" type="info" style="margin-left: 8px">
            {{ CONDITION_LABELS[drawerEntry.condition || ''] || drawerEntry.condition || '-' }}
          </el-tag>
          <span class="drawer-group">{{ drawerEntry.group_name || '-' }}</span>
        </div>

        <el-tabs v-model="drawerTab">
          <el-tab-pane name="srcc" label="SRCC（协作调节）">
            <div v-if="!drawerEntry.srcc_responses" class="drawer-empty">用户未填写此量表</div>
            <template v-else>
              <div class="drawer-result-row">
                <span class="drawer-result-label">总均分</span>
                <span class="drawer-result-val">{{ avg(drawerEntry.srcc_result?.total_avg) }}</span>
              </div>
              <div v-for="group in srccItemsByDimension()" :key="group.dim" class="drawer-dimension">
                <div class="drawer-dim-header">
                  <span class="drawer-dim-label">{{ group.label }}</span>
                  <span class="drawer-dim-avg">均分 {{ avg(drawerEntry.srcc_result?.[`${group.dim}_avg`]) }}</span>
                </div>
                <div v-for="item in group.items" :key="item.id" class="drawer-item">
                  <div class="drawer-item-text">{{ item.zh }}</div>
                  <div class="drawer-rating">
                    <span
                      v-for="n in 7"
                      :key="n"
                      class="drawer-rating-dot"
                      :class="{ 'drawer-rating-dot--active': drawerEntry.srcc_responses?.[item.id] === n }"
                    >{{ n }}</span>
                  </div>
                </div>
              </div>
            </template>
          </el-tab-pane>

          <el-tab-pane name="pcs" label="PCS（凝聚感）">
            <div v-if="!drawerEntry.pcs_responses" class="drawer-empty">用户未填写此量表</div>
            <template v-else>
              <div class="drawer-result-row">
                <span class="drawer-result-label">总均分</span>
                <span class="drawer-result-val">{{ avg(drawerEntry.pcs_result?.total_avg) }}</span>
              </div>
              <div v-for="dimKey in ['belonging', 'morale']" :key="dimKey" class="drawer-dimension">
                <div class="drawer-dim-header">
                  <span class="drawer-dim-label">{{ meta.pcs_dimensions[dimKey] }}</span>
                  <span class="drawer-dim-avg">均分 {{ avg(drawerEntry.pcs_result?.[`${dimKey}_avg`]) }}</span>
                </div>
                <div v-for="item in meta.pcs_items.filter((i) => i.dimension === dimKey)" :key="item.id" class="drawer-item">
                  <div class="drawer-item-text">{{ item.zh }}</div>
                  <div class="drawer-rating">
                    <span
                      v-for="n in 7"
                      :key="n"
                      class="drawer-rating-dot"
                      :class="{ 'drawer-rating-dot--active': drawerEntry.pcs_responses?.[item.id] === n }"
                    >{{ n }}</span>
                  </div>
                </div>
              </div>
            </template>
          </el-tab-pane>
        </el-tabs>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.pagination { display: flex; justify-content: flex-end; margin-top: 12px; }

.cell-name { font-weight: 500; font-size: 14px; }
.cell-sub { font-size: 11px; color: #999; margin-top: 2px; }
.cell-avg { font-size: 11px; color: #666; margin-top: 3px; }

.drawer-user-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding-bottom: 16px;
  border-bottom: 1px solid #eee;
  margin-bottom: 16px;
}
.drawer-user-name { font-size: 16px; font-weight: 700; }
.drawer-group { font-size: 13px; color: #666; }
.drawer-empty { padding: 32px 0; text-align: center; color: #aaa; font-size: 14px; }
.drawer-result-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0 14px;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 12px;
}
.drawer-result-label { font-size: 13px; color: #666; }
.drawer-result-val { font-size: 18px; font-weight: 700; color: #409eff; }
.drawer-dimension { margin-bottom: 16px; }
.drawer-dim-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0 8px;
  border-bottom: 1px solid #f5f5f5;
  margin-bottom: 8px;
}
.drawer-dim-label { font-size: 13px; font-weight: 700; color: #409eff; }
.drawer-dim-avg { font-size: 12px; color: #666; }
.drawer-item { padding: 8px 0; border-bottom: 1px solid #fafafa; }
.drawer-item-text { font-size: 13px; color: #333; margin-bottom: 6px; line-height: 1.5; }
.drawer-rating { display: flex; gap: 5px; }
.drawer-rating-dot {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid #e0e0e0;
  background: #f8f8f8;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #999;
  font-weight: 500;
}
.drawer-rating-dot--active {
  background: #409eff;
  border-color: #409eff;
  color: #fff;
}
</style>
