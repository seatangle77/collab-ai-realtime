<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import {
  createCoiRateAnalysis,
  type CoiRateAnalysisResult,
  type CoiRateMetricSummary,
} from '../../api/admin/coi-rate-analysis'
import type { CoiAnalysisCoderRole, MetricConditionStats } from '../../api/admin/coi-analysis'
import type { AdminGroup } from '../../types/admin'
import { exportRowsToCsv } from '../../utils/csv'
import SampleSelector from './task-score/SampleSelector.vue'
import { coderRoleLabel, conditionLabel, formatNumber, pValueText } from './coi/reportHelpers'
import CoiRateCharts from './coi-rate/CoiRateCharts.vue'
import { buildCoiRateReportHtml, type CoiRateReportLanguage } from './coi-rate/reportHelpers'

const conditions = ['no_assistance', 'glasses', 'app_notification']
const coderRole = ref<CoiAnalysisCoderRole>('final')
const groups = ref<AdminGroup[]>([])
const loadingGroups = ref(false)
const loading = ref(false)
const report = ref<CoiRateAnalysisResult | null>(null)
const selectedGroupIdsByCondition = reactive<Record<string, string[]>>({
  no_assistance: [],
  glasses: [],
  app_notification: [],
})

const groupOptionsByCondition = computed(() => {
  const grouped: Record<string, AdminGroup[]> = { no_assistance: [], glasses: [], app_notification: [] }
  for (const group of groups.value) grouped[group.condition]?.push(group)
  return grouped
})

const primaryMetrics = computed(() => report.value?.metrics.filter(item => item.metric !== 'other_rate') ?? [])
const otherMetric = computed(() => report.value?.metrics.find(item => item.metric === 'other_rate'))

function statsFor(metric: CoiRateMetricSummary | undefined, condition: string): MetricConditionStats | undefined {
  return metric?.conditions.find(item => item.condition === condition)
}

function rate(value: number | null | undefined): string {
  return value == null ? '—' : `${value.toFixed(2)}/min`
}

function fixed(value: number | null | undefined, digits = 2): string {
  return value == null ? '—' : value.toFixed(digits)
}

function dateTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(value))
}

async function loadGroups() {
  loadingGroups.value = true
  try {
    const response = await listAdminGroups({ page: 1, page_size: 200 })
    groups.value = response.items
    for (const condition of conditions) {
      selectedGroupIdsByCondition[condition] = response.items
        .filter(group => group.condition === condition)
        .map(group => group.id)
    }
    if (conditions.every(condition => (selectedGroupIdsByCondition[condition]?.length ?? 0) > 0)) await generateReport()
  } catch (error: any) {
    ElMessage.error(error?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
}

async function generateReport() {
  const missing = conditions.filter(condition => !selectedGroupIdsByCondition[condition]?.length)
  if (missing.length) {
    ElMessage.warning(`请为 ${missing.map(conditionLabel).join('、')} 选择群组`)
    return
  }
  loading.value = true
  try {
    report.value = await createCoiRateAnalysis({
      mode: 'three_conditions',
      coder_role: coderRole.value,
      group_ids_by_condition: Object.fromEntries(
        conditions.map(condition => [condition, selectedGroupIdsByCondition[condition] ?? []]),
      ),
    })
  } catch (error: any) {
    ElMessage.error(error?.message || '生成CoI观点产生率分析失败')
  } finally {
    loading.value = false
  }
}

function downloadReport(language: CoiRateReportLanguage) {
  if (!report.value) return
  const html = buildCoiRateReportHtml(
    report.value,
    coderRole.value,
    conditions,
    selectedGroupIdsByCondition,
    groupOptionsByCondition.value,
    language,
  )
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `coi-rate-analysis-${language}-${new Date().toISOString().slice(0, 10)}.html`
  link.click()
  URL.revokeObjectURL(url)
}

function downloadCsv() {
  if (!report.value) return
  exportRowsToCsv({
    filename: `coi-rate-analysis-${new Date().toISOString().slice(0, 10)}.csv`,
    rows: report.value.observations,
    columns: [
      { key: 'group_name', title: '群组名称', format: row => row.group_name ?? '' },
      { key: 'group_id', title: '群组ID' },
      { key: 'session_id', title: '会话ID' },
      { key: 'session_title', title: '会话名称', format: row => row.session_title ?? '' },
      { key: 'condition', title: '实验条件', format: row => conditionLabel(row.condition) },
      { key: 'started_at', title: '开始时间' },
      { key: 'ended_at', title: '结束时间' },
      { key: 'duration_minutes', title: '会话时长_分钟' },
      { key: 'coded_unit_count', title: '已编码观点数' },
      { key: 'phase_code_count', title: '四阶段编码总数' },
      { key: 'te_count', title: 'TE编码数' },
      { key: 'ex_count', title: 'EX编码数' },
      { key: 'in_count', title: 'IN编码数' },
      { key: 're_count', title: 'RE编码数' },
      { key: 'other_count', title: 'OTHER编码数' },
      { key: 'total_rate', title: '四阶段总产生率_每分钟' },
      { key: 'te_rate', title: 'TE产生率_每分钟' },
      { key: 'ex_rate', title: 'EX产生率_每分钟' },
      { key: 'in_rate', title: 'IN产生率_每分钟' },
      { key: 're_rate', title: 'RE产生率_每分钟' },
      { key: 'other_rate', title: 'OTHER产生率_每分钟' },
    ],
  })
}

onMounted(loadGroups)
</script>

<template>
  <div class="analysis-page rate-page">
    <div class="page-header">
      <div><div class="title-line"><h1>CoI 观点产生率分析</h1><el-tag type="success" effect="plain">真实会话时长</el-tag></div><p>比较三种实验条件下每分钟产生的TE、EX、IN与RE编码数量。</p></div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!report" @click="downloadCsv">下载 CSV</el-button>
        <el-button :icon="Download" :disabled="!report" @click="downloadReport('zh')">下载中文 HTML</el-button>
        <el-button :icon="Download" :disabled="!report" @click="downloadReport('en')">Download English HTML</el-button>
        <el-button :icon="Refresh" :loading="loading" type="primary" @click="generateReport">重新生成</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon>
      <template #title>本页面不推算单条观点的结束时间</template>
      每场会话的产生率使用系统保存的 started_at 与 ended_at 计算。相同时间的拆分观点仍按最终观点单元分别计数；沉默保留在整场讨论时长中。
    </el-alert>

    <el-card class="control-card" shadow="never">
      <el-form label-width="86px" class="control-form">
        <el-form-item label="比较条件"><el-tag size="large">无辅助 / 智能眼镜 / APP 通知</el-tag></el-form-item>
        <el-form-item label="编码来源">
          <el-select v-model="coderRole" style="width:210px" @change="report = null">
            <el-option label="最终协商编码" value="final" />
            <el-option label="研究员 A 独立编码" value="coder_a" />
            <el-option label="研究员 B 独立编码" value="coder_b" />
            <el-option label="AI 编码员 C" value="coder_c" />
          </el-select>
          <el-tag size="large" type="info" style="margin-left:8px">{{ coderRoleLabel(coderRole) }}</el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <SampleSelector v-model="selectedGroupIdsByCondition" :condition-columns="conditions" :group-options-by-condition="groupOptionsByCondition" :loading-groups="loadingGroups" />

    <el-row :gutter="16">
      <el-col :xs="24" :md="6"><el-card class="summary-card" shadow="never"><div class="summary-label">纳入会话</div><div class="summary-value">{{ report?.total_sessions ?? 0 }}</div></el-card></el-col>
      <el-col v-for="condition in conditions" :key="condition" :xs="24" :md="6"><el-card class="summary-card" shadow="never"><div class="summary-label">{{ conditionLabel(condition) }}</div><div class="summary-value">{{ report?.sessions_by_condition[condition] ?? 0 }}</div></el-card></el-col>
    </el-row>

    <el-card class="analysis-card duration-card" shadow="never">
      <template #header><div class="card-title"><strong>会话时长质量检查</strong><span>单位：分钟；时长异常会话不进入分析</span></div></template>
      <el-table v-loading="loading" :data="report?.duration_stats ?? []" border>
        <el-table-column label="条件" min-width="140"><template #default="{ row }">{{ conditionLabel(row.condition) }}</template></el-table-column>
        <el-table-column prop="n" label="n" width="70" align="center" />
        <el-table-column label="平均" width="100" align="center"><template #default="{ row }">{{ fixed(row.mean) }}</template></el-table-column>
        <el-table-column label="SD" width="100" align="center"><template #default="{ row }">{{ fixed(row.sd) }}</template></el-table-column>
        <el-table-column label="中位数" width="100" align="center"><template #default="{ row }">{{ fixed(row.median) }}</template></el-table-column>
        <el-table-column label="范围" min-width="140"><template #default="{ row }">{{ fixed(row.min) }}–{{ fixed(row.max) }}</template></el-table-column>
      </el-table>
      <el-alert v-if="report?.excluded_sessions.length" type="warning" :closable="false" show-icon style="margin-top:12px" :title="`${report.excluded_sessions.length}场会话因时间或编码问题被排除，请查看页面底部明细。`" />
    </el-card>

    <CoiRateCharts v-if="report" :metrics="report.metrics" :observations="report.observations" :contrasts="report.contrasts" :conditions="conditions" />

    <el-card class="analysis-card" shadow="never">
      <template #header><div class="card-title"><strong>产生率描述性统计</strong><span>每场会话等权；单位为编码次数/分钟</span></div></template>
      <el-table v-loading="loading" :data="primaryMetrics" border>
        <el-table-column prop="label" label="指标" min-width="180" />
        <el-table-column v-for="condition in conditions" :key="condition" :label="conditionLabel(condition)" min-width="180">
          <template #default="{ row }"><div class="metric-summary"><strong>{{ rate(statsFor(row, condition)?.mean) }}</strong><span>SD {{ rate(statsFor(row, condition)?.sd) }} · Med {{ rate(statsFor(row, condition)?.median) }}</span></div></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="analysis-card" shadow="never">
      <template #header><div class="card-title"><strong>条件总体置换检验</strong><span>总产生率与四阶段共5项，p值使用BH校正</span></div></template>
      <el-table v-loading="loading" :data="report?.statistical_tests ?? []" border>
        <el-table-column prop="label" label="指标" min-width="180" />
        <el-table-column prop="method" label="检验" min-width="170" />
        <el-table-column label="统计量" width="130"><template #default="{ row }">{{ row.statistic_name }}={{ formatNumber(row.statistic) }}</template></el-table-column>
        <el-table-column label="p" width="90"><template #default="{ row }">{{ pValueText(row.p_value) }}</template></el-table-column>
        <el-table-column label="p_adj (BH)" width="120"><template #default="{ row }"><strong>{{ pValueText(row.p_value_adjusted) }}</strong></template></el-table-column>
        <el-table-column label="η²" width="90"><template #default="{ row }">{{ formatNumber(row.effect_size) }}</template></el-table-column>
        <el-table-column prop="note" label="说明" min-width="300" />
      </el-table>
    </el-card>

    <el-card class="analysis-card" shadow="never">
      <template #header><div class="card-title"><strong>相对无辅助条件的差异</strong><span>均值差与会话级Bootstrap 95%置信区间</span></div></template>
      <el-table v-loading="loading" :data="report?.contrasts ?? []" border>
        <el-table-column prop="label" label="指标" min-width="170" />
        <el-table-column label="比较条件" min-width="130"><template #default="{ row }">{{ conditionLabel(row.comparison_condition) }}</template></el-table-column>
        <el-table-column label="无辅助均值" width="120"><template #default="{ row }">{{ rate(row.reference_mean) }}</template></el-table-column>
        <el-table-column label="比较组均值" width="120"><template #default="{ row }">{{ rate(row.comparison_mean) }}</template></el-table-column>
        <el-table-column label="均值差" width="110"><template #default="{ row }">{{ row.mean_difference > 0 ? '+' : '' }}{{ row.mean_difference.toFixed(3) }}</template></el-table-column>
        <el-table-column label="产生率比" width="100"><template #default="{ row }">{{ formatNumber(row.rate_ratio) }}</template></el-table-column>
        <el-table-column label="95% CI" min-width="160"><template #default="{ row }">[{{ formatNumber(row.ci_low) }}, {{ formatNumber(row.ci_high) }}]</template></el-table-column>
      </el-table>
    </el-card>

    <el-card class="analysis-card" shadow="never">
      <template #header><div class="card-title"><strong>OTHER补充描述</strong><span>OTHER不进入五项主检验</span></div></template>
      <div class="other-grid">
        <div v-for="condition in conditions" :key="condition"><span>{{ conditionLabel(condition) }}</span><strong>{{ rate(statsFor(otherMetric, condition)?.mean) }}</strong></div>
      </div>
    </el-card>

    <el-collapse class="detail-collapse">
      <el-collapse-item name="sessions">
        <template #title><div class="collapse-title"><strong>查看会话级真实分析数据</strong><span>{{ report?.observations.length ?? 0 }}场会话；不包含任何生成数据</span></div></template>
        <el-table :data="report?.observations ?? []" border max-height="620">
          <el-table-column label="群组" min-width="100"><template #default="{ row }">{{ row.group_name || row.group_id }}</template></el-table-column>
          <el-table-column prop="session_id" label="会话ID" min-width="120" />
          <el-table-column label="条件" min-width="110"><template #default="{ row }">{{ conditionLabel(row.condition) }}</template></el-table-column>
          <el-table-column label="开始" min-width="170"><template #default="{ row }">{{ dateTime(row.started_at) }}</template></el-table-column>
          <el-table-column label="结束" min-width="170"><template #default="{ row }">{{ dateTime(row.ended_at) }}</template></el-table-column>
          <el-table-column label="分钟" width="85"><template #default="{ row }">{{ row.duration_minutes.toFixed(2) }}</template></el-table-column>
          <el-table-column prop="phase_code_count" label="四阶段编码" width="100" />
          <el-table-column prop="te_count" label="TE" width="65" /><el-table-column prop="ex_count" label="EX" width="65" /><el-table-column prop="in_count" label="IN" width="65" /><el-table-column prop="re_count" label="RE" width="65" />
          <el-table-column label="Total/min" width="100"><template #default="{ row }">{{ row.total_rate.toFixed(3) }}</template></el-table-column>
          <el-table-column label="TE/min" width="90"><template #default="{ row }">{{ row.te_rate.toFixed(3) }}</template></el-table-column>
          <el-table-column label="EX/min" width="90"><template #default="{ row }">{{ row.ex_rate.toFixed(3) }}</template></el-table-column>
          <el-table-column label="IN/min" width="90"><template #default="{ row }">{{ row.in_rate.toFixed(3) }}</template></el-table-column>
          <el-table-column label="RE/min" width="90"><template #default="{ row }">{{ row.re_rate.toFixed(3) }}</template></el-table-column>
        </el-table>
      </el-collapse-item>
      <el-collapse-item name="excluded">
        <template #title><div class="collapse-title"><strong>被排除会话</strong><span>{{ report?.excluded_sessions.length ?? 0 }}场</span></div></template>
        <el-table :data="report?.excluded_sessions ?? []" border>
          <el-table-column label="群组" min-width="110"><template #default="{ row }">{{ row.group_name || row.group_id }}</template></el-table-column>
          <el-table-column prop="session_id" label="会话ID" min-width="130" />
          <el-table-column label="条件" min-width="110"><template #default="{ row }">{{ conditionLabel(row.condition) }}</template></el-table-column>
          <el-table-column prop="note" label="排除原因" min-width="280" />
        </el-table>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style>
@import './admin-analysis.css';
</style>

<style scoped>
.title-line { display:flex; align-items:center; gap:9px; }
.title-line h1 { margin:0; }
.analysis-card { border:1px solid #e3e9f2; border-radius:10px; }
.duration-card { border-color:#dce8e0; background:linear-gradient(135deg,#fff,#f8fbf9); }
.card-title { display:flex; align-items:baseline; justify-content:space-between; gap:12px; }
.card-title span { color:#748197; font-size:12px; }
.metric-summary { display:flex; flex-direction:column; gap:3px; }
.metric-summary strong { color:#1f2e43; }
.metric-summary span { color:#7b899d; font-size:11px; }
.other-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.other-grid div { display:flex; flex-direction:column; gap:4px; padding:14px 16px; border:1px solid #e3e9f2; border-radius:8px; }
.other-grid span { color:#748197; font-size:12px; }
.other-grid strong { color:#26364b; font-size:18px; }
.detail-collapse { overflow:hidden; border:1px solid #e3e9f2; border-radius:10px; background:#fff; }
.detail-collapse :deep(.el-collapse-item__header) { min-height:62px; height:auto; padding:0 20px; }
.detail-collapse :deep(.el-collapse-item__content) { padding:18px 20px 20px; }
.collapse-title { display:flex; flex-direction:column; align-items:flex-start; gap:3px; }
.collapse-title strong { color:#26364b; }
.collapse-title span { color:#7f8da1; font-size:12px; font-weight:400; }
@media(max-width:760px){.card-title{align-items:flex-start;flex-direction:column}.other-grid{grid-template-columns:1fr}}
</style>
