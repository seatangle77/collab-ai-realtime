<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Printer, Refresh } from '@element-plus/icons-vue'
import {
  createQuestionnaireHierarchicalAnalysis,
  individualTestFor,
  type QuestionnaireHierarchicalAnalysisResult,
} from '../../api/admin/questionnaire-hierarchical-analysis'
import type { QuestionnaireAnalysisMode, QuestionnaireScaleKind } from '../../api/admin/questionnaire-analysis'
import { listAdminGroups } from '../../api/admin/groups'
import type { AdminGroup } from '../../types/admin'
import SampleSelector from './task-score/SampleSelector.vue'
import QHierarchicalMetricChart from './questionnaire-hierarchical/QHierarchicalMetricChart.vue'
import { conditionLabel, formatNumber, pValueText, scaleLabel } from './questionnaire/reportHelpers'

const scale = ref<QuestionnaireScaleKind>('srcc')
const mode = ref<QuestionnaireAnalysisMode>('two_conditions')
const loading = ref(false)
const loadingGroups = ref(false)
const groups = ref<AdminGroup[]>([])
const report = ref<QuestionnaireHierarchicalAnalysisResult | null>(null)
const activeTab = ref('overview')
const selectedGroupIdsByCondition = reactive<Record<string, string[]>>({
  no_assistance: [],
  glasses: [],
  app_notification: [],
})

const conditionColumns = computed(() => mode.value === 'two_conditions'
  ? ['no_assistance', 'glasses']
  : ['no_assistance', 'glasses', 'app_notification'])
const groupOptionsByCondition = computed(() => {
  const grouped: Record<string, AdminGroup[]> = { no_assistance: [], glasses: [], app_notification: [] }
  for (const group of groups.value) grouped[group.condition]?.push(group)
  return grouped
})
const missingConditions = computed(() => conditionColumns.value.filter(
  (condition) => (selectedGroupIdsByCondition[condition]?.length ?? 0) === 0,
))

const metricRows = computed(() => (report.value?.group_mean_metrics ?? []).map((groupMetric) => {
  const mixedMetric = report.value!.mixed_model_metrics.find((item) => item.metric === groupMetric.metric)
  const individualTest = individualTestFor(report.value!, groupMetric.metric)
  const individualP = report.value!.individual_p_values_adjusted[groupMetric.metric] ?? individualTest?.p_value ?? null
  const groupP = groupMetric.test.p_value_adjusted ?? groupMetric.test.p_value
  const mixedP = mixedMetric?.fixed_effect_test.p_value_adjusted ?? mixedMetric?.fixed_effect_test.p_value ?? null
  const individualMetric = report.value!.individual_analysis.metrics.find((item) => item.metric === groupMetric.metric)
  const first = conditionColumns.value[0]
  const second = conditionColumns.value[1]
  const aMean = individualMetric?.conditions.find((item) => item.condition === first)?.mean
  const bMean = individualMetric?.conditions.find((item) => item.condition === second)?.mean
  const individualDirection = aMean != null && bMean != null ? Math.sign(bMean - aMean) : null
  const groupDirection = groupMetric.test.pairwise[0]?.estimate != null ? Math.sign(groupMetric.test.pairwise[0].estimate!) : null
  const mixedDirection = mixedMetric?.fixed_effect_test.pairwise[0]?.estimate != null
    ? Math.sign(mixedMetric.fixed_effect_test.pairwise[0].estimate!) : null
  const directions = [individualDirection, groupDirection, mixedDirection].filter((value) => value !== null)
  const directionStable = directions.length === 3 && new Set(directions).size === 1
  const significance = [individualP, groupP, mixedP].map((p) => p != null && p < 0.05)
  let conclusion = '数据不足'
  if (directions.length === 3 && !directionStable) conclusion = '效果方向变化'
  else if (directionStable && new Set(significance).size === 1) conclusion = '结论稳定'
  else if (directionStable) conclusion = '方向一致，显著性变化'
  return {
    metric: groupMetric.metric,
    label: groupMetric.label,
    individualTest: individualTest?.test ?? '—',
    individualP,
    groupMethod: groupMetric.test.method,
    groupP,
    mixedP,
    icc: mixedMetric?.icc ?? null,
    conclusion,
  }
}))

function individualPairsFor(metric: string) {
  if (!report.value) return []
  const postHoc = report.value.individual_analysis.post_hoc_tests.find((item) => item.metric === metric)
  if (postHoc?.pairs?.length) {
    return postHoc.pairs.map((pair) => ({
      condition_a: pair.condition_a,
      condition_b: pair.condition_b,
      estimate: pair.mean_diff,
      standard_error: null,
      ci_low: null,
      ci_high: null,
      p_value: pair.p_value_adjusted,
      p_value_adjusted: pair.p_value_adjusted,
      significant: pair.significant,
    }))
  }
  const test = individualTestFor(report.value, metric)
  const conditionA = conditionColumns.value[0]
  const conditionB = conditionColumns.value[1]
  if (!conditionA || !conditionB || conditionColumns.value.length !== 2 || !test) return []
  const summary = report.value.individual_analysis.metrics.find((item) => item.metric === metric)
  const a = summary?.conditions.find((item) => item.condition === conditionA)?.mean
  const b = summary?.conditions.find((item) => item.condition === conditionB)?.mean
  const p = report.value.individual_p_values_adjusted[metric] ?? test.p_value
  return [{
    condition_a: conditionA, condition_b: conditionB,
    estimate: a != null && b != null ? b - a : null,
    standard_error: null, ci_low: null, ci_high: null,
    p_value: test.p_value, p_value_adjusted: p, significant: p != null ? p < 0.05 : null,
  }]
}

function significance(p: number | null | undefined) {
  if (p == null) return '—'
  if (p < 0.001) return '***'
  if (p < 0.01) return '**'
  if (p < 0.05) return '*'
  return 'n.s.'
}
function statusType(conclusion: string): 'success' | 'warning' | 'danger' | 'info' {
  if (conclusion === '结论稳定') return 'success'
  if (conclusion === '方向一致，显著性变化') return 'warning'
  if (conclusion === '效果方向变化') return 'danger'
  return 'info'
}
async function fetchGroups() {
  loadingGroups.value = true
  try {
    groups.value = (await listAdminGroups({ page: 1, page_size: 200 })).items
  } catch (error: any) {
    ElMessage.error(error?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
}
async function fetchReport() {
  if (missingConditions.value.length) {
    ElMessage.warning(`请为 ${missingConditions.value.map(conditionLabel).join('、')} 选择小组`)
    return
  }
  loading.value = true
  report.value = null
  try {
    report.value = await createQuestionnaireHierarchicalAnalysis({
      scale: scale.value,
      mode: mode.value,
      group_ids_by_condition: Object.fromEntries(
        conditionColumns.value.map((condition) => [condition, selectedGroupIdsByCondition[condition] ?? []]),
      ),
    })
  } catch (error: any) {
    ElMessage.error(error?.message || '生成层级分析失败')
  } finally {
    loading.value = false
  }
}

function reportDocument(): string {
  const content = document.querySelector('.hierarchical-report-content')?.innerHTML ?? ''
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${scaleLabel(scale.value)}层级分析</title><style>
  body{margin:28px;color:#172033;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}h1{font-size:24px}table{width:100%;border-collapse:collapse;margin:12px 0 24px;font-size:12px}th,td{border:1px solid #d7dee8;padding:7px;text-align:left}th{background:#f2f5f9}.el-card{margin:14px 0}.el-card__header{font-weight:700}.el-tag{display:inline-block;margin:2px;padding:2px 6px;border:1px solid #cbd5e1;border-radius:4px}.metric-chart{width:100%;max-width:900px}.el-tabs__header,.el-button,.chart-caption{display:none}.el-tab-pane{display:block!important}.summary-grid,.sample-summary-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.summary-card,.sample-summary-card{padding:10px;border:1px solid #d7dee8;border-radius:8px}.warning-list{color:#92400e}@media print{body{margin:15mm}.metric-chart-shell{page-break-inside:avoid}}
  </style></head><body><h1>${scaleLabel(scale.value)} · 量表层级与稳健性分析</h1><p>个人普通分析、小组均值分析与随机截距混合效应分析。</p>${content}</body></html>`
}
function downloadReport() {
  if (!report.value) return ElMessage.warning('请先生成分析结果')
  const blob = new Blob([reportDocument()], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `questionnaire-hierarchical-${scale.value}-${mode.value}-${new Date().toISOString().slice(0, 10)}.html`
  link.click()
  URL.revokeObjectURL(url)
}
function printReport() {
  if (!report.value) return ElMessage.warning('请先生成分析结果')
  const win = window.open('', '_blank')
  if (!win) return ElMessage.error('浏览器阻止了打印窗口')
  win.document.write(reportDocument())
  win.document.close()
  win.setTimeout(() => win.print(), 300)
}

onMounted(fetchGroups)
</script>

<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h1>量表层级与稳健性分析</h1>
        <p>在不改变原量表分析的前提下，对比个人、小组均值和混合效应三种统计口径。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!report" @click="downloadReport">下载 HTML</el-button>
        <el-button :icon="Printer" :disabled="!report" @click="printReport">打印 / PDF</el-button>
        <el-button :icon="Refresh" type="primary" :loading="loading" @click="fetchReport">生成层级分析</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon>
      <template #title>新页面独立分析，不会修改问卷记录，也不会改变原“量表分析”页面的结果。</template>
    </el-alert>

    <el-card class="control-card" shadow="never">
      <el-form label-width="86px" class="control-form hierarchical-controls">
        <el-form-item label="量表">
          <el-segmented v-model="scale" :options="[{ label: 'SRCC', value: 'srcc' }, { label: 'PCS', value: 'pcs' }]" />
        </el-form-item>
        <el-form-item label="分析模式">
          <el-segmented v-model="mode" :options="[{ label: '两条件', value: 'two_conditions' }, { label: '三条件', value: 'three_conditions' }]" />
        </el-form-item>
        <el-form-item label="分析模型">
          <el-tag size="large">个人基线 · 小组均值 · 随机截距混合模型</el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <SampleSelector
      v-model="selectedGroupIdsByCondition"
      :condition-columns="conditionColumns"
      :group-options-by-condition="groupOptionsByCondition"
      :loading-groups="loadingGroups"
    />

    <div v-if="report" class="hierarchical-report-content">
      <div v-if="report.warnings.length" class="warning-list">
        <el-alert v-for="warning in report.warnings" :key="warning" :title="warning" type="warning" :closable="false" show-icon />
      </div>

      <div class="summary-grid">
        <el-card class="summary-card" shadow="never"><span class="summary-label">参与者</span><strong class="summary-value">{{ report.participant_count }}</strong></el-card>
        <el-card class="summary-card" shadow="never"><span class="summary-label">小组</span><strong class="summary-value">{{ report.group_count }}</strong></el-card>
        <el-card class="summary-card" shadow="never"><span class="summary-label">量表</span><strong class="summary-value">{{ scale.toUpperCase() }}</strong></el-card>
      </div>

      <el-card shadow="never">
        <template #header><div class="card-title"><strong>样本层级结构</strong><span>柱高表示每个实验条件的人数，小组数单独标注</span></div></template>
        <div class="sample-summary-grid">
          <div v-for="item in report.sample_summary" :key="item.condition" class="sample-summary-card">
            <div class="sample-bar-wrap"><div class="sample-bar" :style="{ height: `${Math.max(8, item.participant_count * 4)}px` }"></div></div>
            <strong>{{ conditionLabel(item.condition) }}</strong>
            <span>{{ item.participant_count }} 人 · {{ item.group_count }} 组</span>
            <small>每组 {{ item.min_group_size ?? '—' }}–{{ item.max_group_size ?? '—' }} 人，平均 {{ item.mean_group_size ?? '—' }}</small>
          </div>
        </div>
      </el-card>

      <el-tabs v-model="activeTab" type="border-card">
        <el-tab-pane label="三种口径总览" name="overview">
          <el-table :data="metricRows" border class="compact-table">
            <el-table-column prop="label" label="量表维度" min-width="150" />
            <el-table-column label="普通个人分析" min-width="170">
              <template #default="{ row }"><div class="result-cell"><strong>{{ significance(row.individualP) }}</strong><span>{{ pValueText(row.individualP) }}</span><small>{{ row.individualTest }}</small></div></template>
            </el-table-column>
            <el-table-column label="小组均值分析" min-width="170">
              <template #default="{ row }"><div class="result-cell"><strong>{{ significance(row.groupP) }}</strong><span>{{ pValueText(row.groupP) }}</span><small>{{ row.groupMethod }}</small></div></template>
            </el-table-column>
            <el-table-column label="混合效应分析" min-width="170">
              <template #default="{ row }"><div class="result-cell"><strong>{{ significance(row.mixedP) }}</strong><span>{{ pValueText(row.mixedP) }}</span><small>ICC={{ formatNumber(row.icc) }}</small></div></template>
            </el-table-column>
            <el-table-column label="稳定性" min-width="160">
              <template #default="{ row }"><el-tag :type="statusType(row.conclusion)">{{ row.conclusion }}</el-tag></template>
            </el-table-column>
          </el-table>

          <div class="method-note baseline-note">普通个人分析图用于基线对照；显著性在新页面内同样使用跨维度 BH-FDR 校正。</div>
          <div class="chart-grid">
            <QHierarchicalMetricChart
              v-for="metric in report.individual_analysis.metrics" :key="metric.metric"
              kind="individual"
              :conditions="report.conditions"
              :individual-metric="metric"
              :individual-test="individualTestFor(report, metric.metric)"
              :individual-p-adjusted="report.individual_p_values_adjusted[metric.metric]"
              :individual-pairs="individualPairsFor(metric.metric)"
            />
          </div>

          <el-card class="icc-card" shadow="never">
            <template #header><strong>小组内相关（ICC）</strong></template>
            <div v-for="item in report.mixed_model_metrics" :key="item.metric" class="icc-row">
              <span>{{ item.label }}</span>
              <div class="icc-track"><div class="icc-fill" :style="{ width: `${Math.max(0, Math.min(100, (item.icc ?? 0) * 100))}%` }"></div></div>
              <strong>{{ item.icc == null ? '—' : `${(item.icc * 100).toFixed(1)}%` }}</strong>
            </div>
          </el-card>
        </el-tab-pane>

        <el-tab-pane label="小组均值分析" name="group">
          <div class="method-note">每个圆点代表一个小组；不同规模的小组等权。总体检验跨维度使用 BH-FDR 校正，两两比较使用 Holm 校正。</div>
          <div class="chart-grid">
            <QHierarchicalMetricChart
              v-for="metric in report.group_mean_metrics" :key="metric.metric"
              kind="group" :conditions="report.conditions" :group-metric="metric"
            />
          </div>
          <el-table :data="report.group_mean_metrics" border class="compact-table result-table">
            <el-table-column prop="label" label="维度" min-width="140" />
            <el-table-column label="检验" min-width="210"><template #default="{ row }">{{ row.test.method }}</template></el-table-column>
            <el-table-column label="统计量" min-width="120"><template #default="{ row }">{{ row.test.statistic_name ?? '—' }}={{ formatNumber(row.test.statistic) }}</template></el-table-column>
            <el-table-column label="原始 p" min-width="100"><template #default="{ row }">{{ pValueText(row.test.p_value) }}</template></el-table-column>
            <el-table-column label="FDR p" min-width="120"><template #default="{ row }"><strong>{{ significance(row.test.p_value_adjusted) }}</strong> {{ pValueText(row.test.p_value_adjusted) }}</template></el-table-column>
            <el-table-column label="效应量" min-width="150"><template #default="{ row }">{{ row.test.effect_size_name ?? '—' }}={{ formatNumber(row.test.effect_size) }}</template></el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="混合效应分析" name="mixed">
          <div class="method-note">随机截距模型：量表得分 ~ 实验条件 + (1 | 小组)。总体检验跨维度使用 BH-FDR 校正，两两比较使用 Holm 校正。</div>
          <div class="chart-grid">
            <QHierarchicalMetricChart
              v-for="metric in report.mixed_model_metrics" :key="metric.metric"
              kind="mixed" :conditions="report.conditions" :mixed-metric="metric"
            />
          </div>
          <el-table :data="report.mixed_model_metrics" border class="compact-table result-table">
            <el-table-column prop="label" label="维度" min-width="140" />
            <el-table-column label="人数 / 小组" min-width="120"><template #default="{ row }">{{ row.participant_count }} / {{ row.group_count }}</template></el-table-column>
            <el-table-column label="LR 检验" min-width="120"><template #default="{ row }">{{ formatNumber(row.fixed_effect_test.statistic) }}</template></el-table-column>
            <el-table-column label="FDR p" min-width="125"><template #default="{ row }"><strong>{{ significance(row.fixed_effect_test.p_value_adjusted) }}</strong> {{ pValueText(row.fixed_effect_test.p_value_adjusted) }}</template></el-table-column>
            <el-table-column label="ICC" min-width="90"><template #default="{ row }">{{ formatNumber(row.icc) }}</template></el-table-column>
            <el-table-column label="收敛" min-width="90"><template #default="{ row }"><el-tag :type="row.converged ? 'success' : 'warning'">{{ row.converged === true ? '是' : row.converged === false ? '否' : '—' }}</el-tag></template></el-table-column>
            <el-table-column prop="note" label="说明" min-width="260" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-empty v-else-if="!loading" description="选择样本后生成层级分析" />
  </div>
</template>

<style>
@import './admin-analysis.css';
</style>

<style scoped>
.hierarchical-controls { grid-template-columns: minmax(190px,.7fr) minmax(240px,.9fr) minmax(340px,1.4fr); }
.hierarchical-report-content { display: flex; flex-direction: column; gap: 16px; }
.warning-list { display: grid; gap: 8px; }
.summary-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; }
.summary-card :deep(.el-card__body) { justify-content: space-between; }
.card-title { display: flex; justify-content: space-between; gap: 12px; color: #64748b; font-size: 12px; }
.card-title strong { color: #172033; font-size: 14px; }
.sample-summary-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 14px; align-items: end; }
.sample-summary-card { display: flex; flex-direction: column; align-items: center; gap: 4px; min-height: 150px; padding: 12px; border: 1px solid #e2e8f0; border-radius: 9px; background: #f8fafc; }
.sample-bar-wrap { display: flex; align-items: end; justify-content: center; height: 88px; width: 100%; border-bottom: 1px solid #94a3b8; overflow: hidden; }
.sample-bar { width: 44px; max-height: 84px; border-radius: 6px 6px 0 0; background: linear-gradient(180deg,#3b82f6,#1d4ed8); }
.sample-summary-card span,.sample-summary-card small { color: #64748b; }
.result-cell { display: flex; flex-direction: column; gap: 2px; }
.result-cell strong { color: #b91c1c; font-size: 16px; }
.result-cell small { color: #64748b; }
.method-note { margin-bottom: 14px; padding: 10px 12px; border-left: 4px solid #2563eb; background: #eff6ff; color: #334155; font-size: 13px; }
.baseline-note { margin-top: 16px; }
.chart-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 14px; overflow-x: auto; }
.result-table { margin-top: 16px; }
.icc-card { margin-top: 16px; }
.icc-row { display: grid; grid-template-columns: 160px minmax(160px,1fr) 64px; align-items: center; gap: 12px; margin: 10px 0; }
.icc-track { height: 12px; overflow: hidden; border-radius: 999px; background: #e2e8f0; }
.icc-fill { height: 100%; border-radius: inherit; background: linear-gradient(90deg,#60a5fa,#1d4ed8); }
@media(max-width:1100px){.hierarchical-controls,.chart-grid{grid-template-columns:1fr}.sample-summary-grid,.summary-grid{grid-template-columns:1fr}.icc-row{grid-template-columns:130px 1fr 54px}}
</style>
