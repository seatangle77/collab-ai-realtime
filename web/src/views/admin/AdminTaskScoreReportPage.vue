<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Printer, Refresh } from '@element-plus/icons-vue'
import { listAdminGroups } from '../../api/admin/groups'
import {
  createTaskScoreAnalysis,
  type TaskScoreAnalysisMode,
  type TaskScoreAnalysisResult,
  type TaskScoreAnalysisTaskId,
} from '../../api/admin/task-score-analysis'
import type { AdminGroup } from '../../types/admin'
import DescriptiveStatsTable from './task-score/DescriptiveStatsTable.vue'
import InferentialStatsTable from './task-score/InferentialStatsTable.vue'
import NormalityTable from './task-score/NormalityTable.vue'
import PostHocTable from './task-score/PostHocTable.vue'
import SampleSelector from './task-score/SampleSelector.vue'
import TaskScoreBoxPlots from './task-score/TaskScoreBoxPlots.vue'
import {
  TASK_OPTIONS,
  buildTaskScoreReportHtml,
  conditionLabel,
  modeDescription,
} from './task-score/reportHelpers'

const filters = reactive({
  mode: 'two_conditions' as TaskScoreAnalysisMode,
  task_id: 'all' as TaskScoreAnalysisTaskId,
})

const loading = ref(false)
const loadingGroups = ref(false)
const groups = ref<AdminGroup[]>([])
const report = ref<TaskScoreAnalysisResult | null>(null)
const selectedGroupIdsByCondition = reactive<Record<string, string[]>>({
  no_assistance: [],
  glasses: [],
  app_notification: [],
})

const descriptiveMetrics = computed(() => report.value?.metrics ?? [])
const primaryNormality = computed(() => report.value?.normality.filter((item) => item.role === 'primary') ?? [])
const baselineNormality = computed(() => report.value?.normality.filter((item) => item.role === 'baseline') ?? [])
const primaryStatisticalTests = computed(() =>
  report.value?.statistical_tests.filter((item) => item.role === 'primary') ?? [],
)
const baselineStatisticalTests = computed(() =>
  report.value?.statistical_tests.filter((item) => item.role === 'baseline') ?? [],
)
const postHocTests = computed(() => report.value?.post_hoc_tests ?? [])
const conditionColumns = computed(() =>
  filters.mode === 'two_conditions'
    ? ['no_assistance', 'glasses']
    : ['no_assistance', 'glasses', 'app_notification'],
)
const groupOptionsByCondition = computed(() => {
  const grouped: Record<string, AdminGroup[]> = {
    no_assistance: [],
    glasses: [],
    app_notification: [],
  }
  for (const group of groups.value) {
    if (!grouped[group.condition]) grouped[group.condition] = []
    grouped[group.condition]?.push(group)
  }
  return grouped
})
const missingSelectedConditions = computed(() =>
  conditionColumns.value.filter((condition) => (selectedGroupIdsByCondition[condition]?.length ?? 0) === 0),
)

async function fetchGroups() {
  loadingGroups.value = true
  try {
    const res = await listAdminGroups({ page: 1, page_size: 200 })
    groups.value = res.items
  } catch (e: any) {
    ElMessage.error(e?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
}

async function fetchReport() {
  if (missingSelectedConditions.value.length > 0) {
    ElMessage.warning(`请为 ${missingSelectedConditions.value.map(conditionLabel).join('、')} 选择要纳入分析的小组`)
    return
  }
  loading.value = true
  try {
    report.value = await createTaskScoreAnalysis({
      mode: filters.mode,
      task_id: filters.task_id,
      group_ids_by_condition: Object.fromEntries(
        conditionColumns.value.map((condition) => [condition, selectedGroupIdsByCondition[condition] ?? []]),
      ),
    })
  } catch (e: any) {
    ElMessage.error(e?.message || '加载任务分数分析失败')
  } finally {
    loading.value = false
  }
}

function ensureReportReady(): boolean {
  if (!report.value) {
    ElMessage.warning('请先生成分析结果')
    return false
  }
  return true
}

function reportHtml(): string {
  if (!report.value) return ''
  return buildTaskScoreReportHtml({
    report: report.value,
    mode: filters.mode,
    taskId: filters.task_id,
    conditionColumns: conditionColumns.value,
    selectedGroupIdsByCondition,
    groupOptionsByCondition: groupOptionsByCondition.value,
  })
}

function downloadHtmlReport() {
  if (!ensureReportReady()) return
  const blob = new Blob([reportHtml()], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `task-score-report-${new Date().toISOString().slice(0, 10)}.html`
  link.click()
  URL.revokeObjectURL(url)
}

function printReportAsPdf() {
  if (!ensureReportReady()) return
  const printWindow = window.open('', '_blank')
  if (!printWindow) {
    ElMessage.error('浏览器阻止了打印窗口，请允许弹窗后重试')
    return
  }
  printWindow.document.open()
  printWindow.document.write(reportHtml())
  printWindow.document.close()
  printWindow.focus()
  printWindow.setTimeout(() => {
    printWindow.print()
  }, 300)
}

onMounted(fetchGroups)
</script>

<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h1>任务分数分析</h1>
        <p>手动选择每个实验条件纳入的小组，再汇总 GS、AIS、Best IS、弱协同值和强协同值。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!report" @click="downloadHtmlReport">下载 HTML 报告</el-button>
        <el-button :icon="Printer" :disabled="!report" @click="printReportAsPdf">打印/PDF</el-button>
        <el-button :icon="Refresh" :loading="loading" type="primary" @click="fetchReport">生成分析</el-button>
      </div>
    </div>

    <el-card class="control-card" shadow="never">
      <el-form label-width="86px" class="control-form">
        <el-form-item label="分析模式">
          <el-segmented
            v-model="filters.mode"
            :options="[
              { label: '两条件', value: 'two_conditions' },
              { label: '三条件', value: 'three_conditions' },
            ]"
          />
        </el-form-item>
        <el-form-item label="任务">
          <el-select v-model="filters.task_id">
            <el-option
              v-for="task in TASK_OPTIONS"
              :key="task.value"
              :label="task.label"
              :value="task.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="当前口径">
          <el-tag size="large">{{ modeDescription(filters.mode) }}</el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <SampleSelector
      v-model="selectedGroupIdsByCondition"
      :condition-columns="conditionColumns"
      :group-options-by-condition="groupOptionsByCondition"
      :loading-groups="loadingGroups"
    />

    <el-row :gutter="16">
      <el-col :xs="24" :md="8">
        <el-card class="summary-card" shadow="never">
          <div class="summary-label">纳入记录数</div>
          <div class="summary-value">{{ report?.total_entries ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col v-for="condition in conditionColumns" :key="condition" :xs="24" :md="8">
        <el-card class="summary-card" shadow="never">
          <div class="summary-label">{{ conditionLabel(condition) }}</div>
          <div class="summary-value">{{ report?.entries_by_condition[condition] ?? 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <DescriptiveStatsTable
      :loading="loading"
      :metrics="descriptiveMetrics"
      :condition-columns="conditionColumns"
      :mode="filters.mode"
    />

    <TaskScoreBoxPlots
      :observations="report?.observations ?? []"
      :condition-columns="conditionColumns"
    />

    <NormalityTable
      :loading="loading"
      :items="primaryNormality"
    />

    <InferentialStatsTable
      :loading="loading"
      :primary-tests="primaryStatisticalTests"
      :baseline-tests="baselineStatisticalTests"
      :baseline-normality="baselineNormality"
    />

    <PostHocTable
      :loading="loading"
      :post-hoc-tests="postHocTests"
    />
  </div>
</template>

<style>
@import './admin-analysis.css';
</style>

<style scoped>
.control-form {
  grid-template-columns: minmax(220px, 0.8fr) minmax(280px, 1.1fr) minmax(260px, 1fr);
}
</style>
