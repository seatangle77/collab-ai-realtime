<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Printer, Refresh } from '@element-plus/icons-vue'
import {
  createQuestionnaireAnalysis,
  type QuestionnaireAnalysisMode,
  type QuestionnaireAnalysisResult,
  type QuestionnaireScaleKind,
} from '../../api/admin/questionnaire-analysis'
import { listAdminGroups } from '../../api/admin/groups'
import type { AdminGroup } from '../../types/admin'
import SampleSelector from './task-score/SampleSelector.vue'
import QDescriptiveStatsTable from './questionnaire/QDescriptiveStatsTable.vue'
import QReliabilityTable from './questionnaire/QReliabilityTable.vue'
import QNormalityTable from './questionnaire/QNormalityTable.vue'
import QInferentialStatsTable from './questionnaire/QInferentialStatsTable.vue'
import QPostHocTable from './questionnaire/QPostHocTable.vue'
import { buildQuestionnaireReportHtml, conditionLabel, modeDescription, scaleLabel } from './questionnaire/reportHelpers'

const scale = ref<QuestionnaireScaleKind>('srcc')
const mode = ref<QuestionnaireAnalysisMode>('two_conditions')
const loading = ref(false)
const loadingGroups = ref(false)
const groups = ref<AdminGroup[]>([])
const report = ref<QuestionnaireAnalysisResult | null>(null)

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
    report.value = await createQuestionnaireAnalysis({
      scale: scale.value,
      mode: mode.value,
      group_ids_by_condition: Object.fromEntries(
        conditionColumns.value.map((c) => [c, selectedGroupIdsByCondition[c] ?? []]),
      ),
    })
  } catch (e: any) {
    ElMessage.error(e?.message || '加载量表分析失败')
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
  const html = buildQuestionnaireReportHtml(report.value!, mode.value, scale.value)
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `questionnaire-${scale.value}-report-${new Date().toISOString().slice(0, 10)}.html`
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
  const html = buildQuestionnaireReportHtml(report.value!, mode.value, scale.value)
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
        <h1>量表分析报告</h1>
        <p>选择量表、分析模式和纳入小组，按所选样本汇总 SRCC 或 PCS 量表数据。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!report" @click="downloadHtmlReport">下载 HTML 报告</el-button>
        <el-button :icon="Printer" :disabled="!report" @click="printReportAsPdf">打印 / PDF</el-button>
        <el-button :icon="Refresh" :loading="loading" type="primary" @click="fetchReport">生成分析</el-button>
      </div>
    </div>

    <el-card class="control-card" shadow="never">
      <el-form label-width="86px" class="control-form">
        <el-form-item label="量表">
          <el-segmented
            v-model="scale"
            :options="[
              { label: 'SRCC', value: 'srcc' },
              { label: 'PCS', value: 'pcs' },
            ]"
          />
        </el-form-item>
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
          <el-tag size="large">{{ scaleLabel(scale) }} · {{ modeDescription(mode) }}</el-tag>
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

    <QDescriptiveStatsTable
      :loading="loading"
      :metrics="report?.metrics ?? []"
      :condition-columns="conditionColumns"
      :mode="mode"
    />

    <QReliabilityTable
      :loading="loading"
      :reliability="report?.reliability ?? []"
    />

    <QNormalityTable
      :loading="loading"
      :items="report?.normality ?? []"
    />

    <QInferentialStatsTable
      :loading="loading"
      :tests="report?.statistical_tests ?? []"
    />

    <QPostHocTable
      :loading="loading"
      :post-hoc-tests="report?.post_hoc_tests ?? []"
    />
  </div>
</template>

<style>
@import './admin-analysis.css';
</style>

<style scoped>
.control-form {
  grid-template-columns: minmax(200px, 0.8fr) minmax(260px, 1fr) minmax(280px, 1.2fr);
}
</style>
