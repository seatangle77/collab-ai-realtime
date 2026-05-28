<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Printer, Refresh } from '@element-plus/icons-vue'
import { createCoiAnalysis, type CoiAnalysisMode, type CoiAnalysisResult } from '../../api/admin/coi-analysis'
import { listAdminGroups } from '../../api/admin/groups'
import type { AdminGroup } from '../../types/admin'
import SampleSelector from './task-score/SampleSelector.vue'
import CoiDescriptiveStatsTable from './coi/CoiDescriptiveStatsTable.vue'
import CoiNormalityTable from './coi/CoiNormalityTable.vue'
import CoiInferentialStatsTable from './coi/CoiInferentialStatsTable.vue'
import CoiPostHocTable from './coi/CoiPostHocTable.vue'
import CoiMeanComparisonCharts from './coi/CoiMeanComparisonCharts.vue'
import { buildCoiReportHtml, conditionLabel, modeDescription } from './coi/reportHelpers'

const mode = ref<CoiAnalysisMode>('two_conditions')
const loading = ref(false)
const loadingGroups = ref(false)
const groups = ref<AdminGroup[]>([])
const report = ref<CoiAnalysisResult | null>(null)

const selectedGroupIdsByCondition = reactive<Record<string, string[]>>({
  no_assistance: [],
  glasses: [],
  app_notification: [],
})

const conditionColumns = computed(() =>
  mode.value === 'two_conditions'
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
    if (grouped[group.condition]) grouped[group.condition].push(group)
  }
  return grouped
})

const missingSelectedConditions = computed(() =>
  conditionColumns.value.filter((c) => (selectedGroupIdsByCondition[c]?.length ?? 0) === 0),
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
    report.value = await createCoiAnalysis({
      mode: mode.value,
      group_ids_by_condition: Object.fromEntries(
        conditionColumns.value.map((c) => [c, selectedGroupIdsByCondition[c] ?? []]),
      ),
    })
  } catch (e: any) {
    ElMessage.error(e?.message || '生成 CoI 分析失败')
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

function downloadHtmlReport() {
  if (!ensureReportReady()) return
  const html = buildCoiReportHtml(
    report.value!,
    mode.value,
    conditionColumns.value,
    selectedGroupIdsByCondition,
    groupOptionsByCondition.value,
  )
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `coi-analysis-report-${new Date().toISOString().slice(0, 10)}.html`
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
  const html = buildCoiReportHtml(
    report.value!,
    mode.value,
    conditionColumns.value,
    selectedGroupIdsByCondition,
    groupOptionsByCondition.value,
  )
  printWindow.document.open()
  printWindow.document.write(html)
  printWindow.document.close()
  printWindow.focus()
  printWindow.setTimeout(() => { printWindow.print() }, 300)
}

onMounted(fetchGroups)
</script>

<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h1>CoI 认知参与度分析</h1>
        <p>基于已编码的 CoI 发言单元，计算各组认知参与度指标并进行组间统计检验。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!report" @click="downloadHtmlReport">下载 HTML 报告</el-button>
        <el-button :icon="Printer" :disabled="!report" @click="printReportAsPdf">打印 / PDF</el-button>
        <el-button :icon="Refresh" :loading="loading" type="primary" @click="fetchReport">生成分析</el-button>
      </div>
    </div>

    <el-card class="control-card" shadow="never">
      <el-form label-width="86px" class="control-form">
        <el-form-item label="分析模式">
          <el-segmented
            v-model="mode"
            :options="[
              { label: '两条件', value: 'two_conditions' },
              { label: '三条件', value: 'three_conditions' },
            ]"
          />
        </el-form-item>
        <el-form-item label="当前口径">
          <el-tag size="large">{{ modeDescription(mode) }}</el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <SampleSelector
      v-model="selectedGroupIdsByCondition"
      :condition-columns="conditionColumns"
      :group-options-by-condition="groupOptionsByCondition"
      :loading-groups="loadingGroups"
    />

    <!-- 统计概览 -->
    <el-row :gutter="16">
      <el-col :xs="24" :md="8">
        <el-card class="summary-card" shadow="never">
          <div class="summary-label">纳入会话数</div>
          <div class="summary-value">{{ report?.total_sessions ?? 0 }}</div>
        </el-card>
      </el-col>
      <el-col v-for="condition in conditionColumns" :key="condition" :xs="24" :md="8">
        <el-card class="summary-card" shadow="never">
          <div class="summary-label">{{ conditionLabel(condition) }}</div>
          <div class="summary-value">{{ report?.sessions_by_condition[condition] ?? 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 排除会话警告 -->
    <el-alert
      v-if="report && report.excluded_sessions.length > 0"
      type="warning"
      show-icon
      :closable="false"
      class="excluded-alert"
    >
      <template #title>
        有 {{ report.excluded_sessions.length }} 个会话因存在未编码发言被排除出分析
      </template>
      <div class="excluded-list">
        <div v-for="s in report.excluded_sessions" :key="s.session_id" class="excluded-item">
          <span>{{ s.group_name ?? s.group_id }}</span>
          <el-tag size="small" type="info">{{ conditionLabel(s.condition) }}</el-tag>
          <span class="excluded-count">{{ s.uncoded_count }} 条未编码 / 共 {{ s.total_count }} 条</span>
        </div>
      </div>
    </el-alert>

    <CoiDescriptiveStatsTable
      :loading="loading"
      :metrics="report?.metrics ?? []"
      :condition-columns="conditionColumns"
      :mode="mode"
    />

    <CoiNormalityTable
      :loading="loading"
      :items="report?.normality ?? []"
    />

    <CoiInferentialStatsTable
      :loading="loading"
      :tests="report?.statistical_tests ?? []"
    />

    <CoiPostHocTable
      v-if="mode === 'three_conditions'"
      :loading="loading"
      :post-hoc-tests="report?.post_hoc_tests ?? []"
    />

    <CoiMeanComparisonCharts
      v-if="report && report.metrics.length > 0"
      :metrics="report.metrics"
      :condition-columns="conditionColumns"
    />
  </div>
</template>

<style>
@import './admin-analysis.css';
</style>

<style scoped>
.control-form {
  grid-template-columns: minmax(260px, 1fr) minmax(260px, 1fr);
}

.excluded-alert :deep(.el-alert__content) {
  width: 100%;
}

.excluded-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.excluded-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.excluded-count {
  color: #8a7a5a;
  font-size: 12px;
}
</style>
