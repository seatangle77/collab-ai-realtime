<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Printer, Refresh } from '@element-plus/icons-vue'
import { listAdminGroups } from '../../api/admin/groups'
import {
  createTaskScoreIndividualAnalysis,
  type TaskScoreIndividualAnalysisResult,
} from '../../api/admin/task-score-individual-analysis'
import type { TaskScoreAnalysisMode, TaskScoreAnalysisTaskId } from '../../api/admin/task-score-analysis'
import type { AdminGroup } from '../../types/admin'
import SampleSelector from './task-score/SampleSelector.vue'
import {
  TASK_OPTIONS,
  conditionLabel,
  formatNumber,
  modeDescription,
  taskLabel,
} from './task-score/reportHelpers'
import IndividualScoreChart from './task-score-individual/IndividualScoreChart.vue'
import { buildIndividualTaskScoreCsv, buildIndividualTaskScoreReportHtml } from './task-score-individual/reportHelpers'
import { downloadTextFile, type ReportLanguage } from './task-score/analysisExport'

const filters = reactive({
  mode: 'three_conditions' as TaskScoreAnalysisMode,
  task_id: 'all' as TaskScoreAnalysisTaskId,
})
const loading = ref(false)
const loadingGroups = ref(false)
const groups = ref<AdminGroup[]>([])
const report = ref<TaskScoreIndividualAnalysisResult | null>(null)
const selectedGroupIdsByCondition = reactive<Record<string, string[]>>({
  no_assistance: [],
  glasses: [],
  app_notification: [],
})

const conditionColumns = computed(() => filters.mode === 'two_conditions'
  ? ['no_assistance', 'glasses']
  : ['no_assistance', 'glasses', 'app_notification'])
const groupOptionsByCondition = computed(() => {
  const grouped: Record<string, AdminGroup[]> = { no_assistance: [], glasses: [], app_notification: [] }
  for (const group of groups.value) (grouped[group.condition] ??= []).push(group)
  return grouped
})
const missingSelectedConditions = computed(() =>
  conditionColumns.value.filter((condition) => !selectedGroupIdsByCondition[condition]?.length),
)

function statFor(condition: string) {
  return report.value?.baseline_stats.find((item) => item.condition === condition)
}

function improvementFor(condition: string) {
  return report.value?.improvement_summaries.find((item) => item.condition === condition)
}

function positionLabel(position: string) {
  return ({ best: '原最佳成员', middle: '原中间成员', weakest: '原最弱成员' } as Record<string, string>)[position] ?? position
}

async function fetchGroups() {
  loadingGroups.value = true
  try {
    const res = await listAdminGroups({ page: 1, page_size: 200 })
    groups.value = res.items
  } catch (error: any) {
    ElMessage.error(error?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
}

async function fetchReport() {
  if (missingSelectedConditions.value.length) {
    ElMessage.warning(`请为 ${missingSelectedConditions.value.map(conditionLabel).join('、')} 选择要纳入分析的小组`)
    return
  }
  loading.value = true
  try {
    report.value = await createTaskScoreIndividualAnalysis({
      mode: filters.mode,
      task_id: filters.task_id,
      group_ids_by_condition: Object.fromEntries(
        conditionColumns.value.map((condition) => [condition, selectedGroupIdsByCondition[condition] ?? []]),
      ),
    })
  } catch (error: any) {
    ElMessage.error(error?.message || '加载个人任务成绩分析失败')
  } finally {
    loading.value = false
  }
}

function reportHtml(language: ReportLanguage = 'zh') {
  return report.value ? buildIndividualTaskScoreReportHtml(report.value, language) : ''
}

function downloadHtmlReport(language: ReportLanguage) {
  if (!report.value) return ElMessage.warning('请先生成分析结果')
  downloadTextFile(
    reportHtml(language),
    `task-score-individual-report-${language}-${filters.mode}-${new Date().toISOString().slice(0, 10)}.html`,
    'text/html;charset=utf-8',
  )
}

function downloadCsv() {
  if (!report.value) return ElMessage.warning('请先生成分析结果')
  downloadTextFile(
    buildIndividualTaskScoreCsv(report.value),
    `task-score-individual-data-${filters.mode}-${new Date().toISOString().slice(0, 10)}.csv`,
    'text/csv;charset=utf-8',
  )
}

function printReportAsPdf() {
  if (!report.value) return ElMessage.warning('请先生成分析结果')
  const printWindow = window.open('', '_blank')
  if (!printWindow) return ElMessage.error('浏览器阻止了打印窗口，请允许弹窗后重试')
  printWindow.document.open()
  printWindow.document.write(reportHtml('zh'))
  printWindow.document.close()
  printWindow.focus()
  printWindow.setTimeout(() => printWindow.print(), 300)
}

onMounted(fetchGroups)
</script>

<template>
  <div class="analysis-page">
    <div class="page-header">
      <div>
        <h1>个人到小组成绩变化分析</h1>
        <p>比较每个人的独立分数 IS 与所在小组的最终分数 GS，正改善值表示小组结果更好。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!report" @click="downloadCsv">下载 CSV</el-button>
        <el-button :icon="Download" :disabled="!report" @click="downloadHtmlReport('zh')">下载中文 HTML</el-button>
        <el-button :icon="Download" :disabled="!report" @click="downloadHtmlReport('en')">Download English HTML</el-button>
        <el-button :icon="Printer" :disabled="!report" @click="printReportAsPdf">打印/PDF</el-button>
        <el-button :icon="Refresh" :loading="loading" type="primary" @click="fetchReport">生成分析</el-button>
      </div>
    </div>

    <el-alert
      title="这不是个人前测—个人后测：系统没有个人后测。本页比较个人独立答案 IS 与小组共同答案 GS；同组3人共享一个 GS，推断统计始终以小组为单位。"
      type="info"
      :closable="false"
      show-icon
    />

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
            <el-option v-for="task in TASK_OPTIONS" :key="task.value" :label="task.label" :value="task.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="统计口径">
          <el-tag size="large">{{ modeDescription(filters.mode) }} · 小组聚类置换</el-tag>
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
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="summary-card" shadow="never">
          <div class="summary-label">纳入个人</div>
          <div class="summary-value">{{ report?.total_individuals ?? 0 }}</div>
          <div class="summary-note">来自 {{ report?.total_groups ?? 0 }} 个独立小组</div>
        </el-card>
      </el-col>
      <el-col v-for="condition in conditionColumns" :key="condition" :xs="24" :sm="12" :md="6">
        <el-card class="summary-card" shadow="never">
          <div class="summary-label">{{ conditionLabel(condition) }}</div>
          <div class="summary-value">{{ report?.individuals_by_condition[condition] ?? 0 }}</div>
          <div class="summary-note">{{ report?.groups_by_condition[condition] ?? 0 }} 个小组</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="analysis-card" shadow="never">
      <template #header>
        <div class="card-title">
          <strong>AIS 数据一致性</strong>
          <el-tag
            :type="report?.ais_consistency.status === 'ok' ? 'success' : report?.ais_consistency.status === 'warning' ? 'warning' : 'info'"
          >
            {{ report?.ais_consistency.status === 'ok' ? '通过' : report?.ais_consistency.status === 'warning' ? '需要检查' : '等待分析' }}
          </el-tag>
        </div>
      </template>
      <p class="plain-note">{{ report?.ais_consistency.note ?? '生成分析后，系统会核对每组三人的个人均值是否等于已保存 AIS。' }}</p>
      <p v-if="report" class="plain-note">
        已核对 {{ report.ais_consistency.checked_groups }} 组；最大绝对差 {{ formatNumber(report.ais_consistency.max_absolute_difference) }}。
      </p>
    </el-card>

    <el-card class="analysis-card table-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>个人到小组改善</strong><span>改善值 = IS−GS；正数表示小组优于该成员原答案</span></div>
      </template>
      <el-table v-loading="loading" :data="conditionColumns" border>
        <el-table-column label="条件" min-width="150">
          <template #default="{ row }"><strong>{{ conditionLabel(row) }}</strong></template>
        </el-table-column>
        <el-table-column label="个人/小组 n" width="120"><template #default="{ row }">{{ improvementFor(row)?.individual_count ?? 0 }}/{{ improvementFor(row)?.group_count ?? 0 }}</template></el-table-column>
        <el-table-column label="平均改善" width="110"><template #default="{ row }"><strong>{{ formatNumber(improvementFor(row)?.mean ?? null) }}</strong></template></el-table-column>
        <el-table-column label="SD" width="100"><template #default="{ row }">{{ formatNumber(improvementFor(row)?.sd ?? null) }}</template></el-table-column>
        <el-table-column label="Median" width="100"><template #default="{ row }">{{ formatNumber(improvementFor(row)?.median ?? null) }}</template></el-table-column>
        <el-table-column label="改善人数" width="105"><template #default="{ row }">{{ improvementFor(row)?.improved_count ?? 0 }}</template></el-table-column>
        <el-table-column label="不变" width="80"><template #default="{ row }">{{ improvementFor(row)?.unchanged_count ?? 0 }}</template></el-table-column>
        <el-table-column label="变差人数" width="105"><template #default="{ row }">{{ improvementFor(row)?.worsened_count ?? 0 }}</template></el-table-column>
        <el-table-column label="改善比例" width="105"><template #default="{ row }">{{ formatNumber(improvementFor(row)?.improved_percentage ?? null) }}%</template></el-table-column>
      </el-table>
    </el-card>

    <el-card class="analysis-card table-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>各条件内是否整体改善</strong><span>检验每组 AIS−GS 是否偏离0；多个条件使用 Holm 校正</span></div>
      </template>
      <el-table :data="report?.within_condition_tests ?? []" border>
        <el-table-column label="条件" min-width="150"><template #default="{ row }"><strong>{{ conditionLabel(row.condition) }}</strong></template></el-table-column>
        <el-table-column prop="group_count" label="独立小组 n" width="115" />
        <el-table-column label="小组平均改善" width="130"><template #default="{ row }">{{ formatNumber(row.mean_group_improvement) }}</template></el-table-column>
        <el-table-column label="原始 p" width="105"><template #default="{ row }">{{ formatNumber(row.p_value) }}</template></el-table-column>
        <el-table-column label="Holm 校正后 p" width="145"><template #default="{ row }">{{ formatNumber(row.p_value_adjusted) }}</template></el-table-column>
        <el-table-column label="效应量 dz" width="110"><template #default="{ row }">{{ formatNumber(row.effect_size) }}</template></el-table-column>
        <el-table-column label="结论" min-width="150">
          <template #default="{ row }">
            <el-tag v-if="row.status !== 'ok'" type="info">数据不足</el-tag>
            <el-tag v-else-if="row.significant && row.mean_group_improvement > 0" type="success">显著改善</el-tag>
            <el-tag v-else-if="row.significant" type="danger">显著变差</el-tag>
            <el-tag v-else type="info">未检出显著变化</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <IndividualScoreChart :observations="report?.observations ?? []" :conditions="conditionColumns" />

    <el-card class="analysis-card table-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>按任务分层的改善值</strong><span>比较每种任务中个人答案到小组答案改善了多少</span></div>
      </template>
      <el-table :data="report?.task_summaries ?? []" border>
        <el-table-column label="任务" min-width="150"><template #default="{ row }"><strong>{{ taskLabel(row.task_id) }}</strong></template></el-table-column>
        <el-table-column v-for="condition in conditionColumns" :key="condition" :label="conditionLabel(condition)" min-width="180">
          <template #default="{ row }">
            <span v-if="row.conditions.find((item: any) => item.condition === condition)?.n">
              n={{ row.conditions.find((item: any) => item.condition === condition)?.n }}；
              M={{ formatNumber(row.conditions.find((item: any) => item.condition === condition)?.mean ?? null) }}；
              SD={{ formatNumber(row.conditions.find((item: any) => item.condition === condition)?.sd ?? null) }}
            </span>
            <span v-else>n=0</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="analysis-card table-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>不同起点成员的改善</strong><span>每组按个人独立分从低到高排列；并列时按参与者编码稳定排序</span></div>
      </template>
      <el-table :data="report?.member_position_summaries ?? []" border>
        <el-table-column label="成员位置" min-width="150"><template #default="{ row }"><strong>{{ positionLabel(row.position) }}</strong></template></el-table-column>
        <el-table-column v-for="condition in conditionColumns" :key="condition" :label="conditionLabel(condition)" min-width="180">
          <template #default="{ row }">
            <span>n={{ row.conditions.find((item: any) => item.condition === condition)?.n ?? 0 }}；平均改善={{ formatNumber(row.conditions.find((item: any) => item.condition === condition)?.mean ?? null) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="analysis-card table-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>个人独立分基线</strong><span>仅用于说明讨论前起点；分数越低越好</span></div>
      </template>
      <el-table :data="conditionColumns" border>
        <el-table-column label="条件" min-width="150"><template #default="{ row }"><strong>{{ conditionLabel(row) }}</strong></template></el-table-column>
        <el-table-column label="个人 n" width="100"><template #default="{ row }">{{ statFor(row)?.n ?? 0 }}</template></el-table-column>
        <el-table-column label="M" width="110"><template #default="{ row }">{{ formatNumber(statFor(row)?.mean ?? null) }}</template></el-table-column>
        <el-table-column label="SD" width="110"><template #default="{ row }">{{ formatNumber(statFor(row)?.sd ?? null) }}</template></el-table-column>
        <el-table-column label="Median" width="110"><template #default="{ row }">{{ formatNumber(statFor(row)?.median ?? null) }}</template></el-table-column>
        <el-table-column label="Min–Max" min-width="130"><template #default="{ row }">{{ formatNumber(statFor(row)?.min ?? null) }}–{{ formatNumber(statFor(row)?.max ?? null) }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-card class="analysis-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>平均改善值的条件检验</strong><span>每组一个平均改善值（等于 AIS−GS），并在任务内置换条件标签</span></div>
      </template>
      <el-descriptions :column="4" border>
        <el-descriptions-item label="方法">小组聚类、任务内分层置换</el-descriptions-item>
        <el-descriptions-item label="统计量">{{ report?.statistical_test.statistic_name ?? 'pseudo-F' }}={{ formatNumber(report?.statistical_test.statistic ?? null) }}</el-descriptions-item>
        <el-descriptions-item label="p">{{ formatNumber(report?.statistical_test.p_value ?? null) }}</el-descriptions-item>
        <el-descriptions-item label="效应量">η²={{ formatNumber(report?.statistical_test.effect_size ?? null) }}</el-descriptions-item>
      </el-descriptions>
      <p class="plain-note">{{ report?.statistical_test.note ?? '生成分析后显示结果。' }}</p>
    </el-card>

    <el-card v-if="filters.mode === 'three_conditions'" class="analysis-card table-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>条件两两比较</strong><span>仅总体 p&lt;.05 时执行；正均值差表示条件 B 改善更多</span></div>
      </template>
      <el-table :data="report?.pairwise_tests ?? []" border>
        <el-table-column label="条件 A" min-width="130"><template #default="{ row }">{{ conditionLabel(row.condition_a) }}</template></el-table-column>
        <el-table-column label="条件 B" min-width="130"><template #default="{ row }">{{ conditionLabel(row.condition_b) }}</template></el-table-column>
        <el-table-column label="均值差 (B−A)" min-width="130"><template #default="{ row }">{{ formatNumber(row.mean_difference) }}</template></el-table-column>
        <el-table-column label="原始 p" width="110"><template #default="{ row }">{{ formatNumber(row.p_value) }}</template></el-table-column>
        <el-table-column label="Holm 校正后 p" min-width="140"><template #default="{ row }">{{ formatNumber(row.p_value_adjusted) }}</template></el-table-column>
        <el-table-column label="显著" width="90"><template #default="{ row }"><el-tag :type="row.significant ? 'danger' : 'info'">{{ row.significant ? '是' : '否' }}</el-tag></template></el-table-column>
        <template #empty>
          <span>{{ report?.statistical_test.p_value != null && report.statistical_test.p_value >= 0.05 ? '总体检验未显著，不执行事后比较' : '暂无可比较结果' }}</span>
        </template>
      </el-table>
    </el-card>

    <el-card class="analysis-card table-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>个人明细</strong><span>管理员页面可核对姓名；下载报告仅导出参与者编码</span></div>
      </template>
      <el-table :data="report?.observations ?? []" border max-height="520">
        <el-table-column label="条件" min-width="120"><template #default="{ row }">{{ conditionLabel(row.condition) }}</template></el-table-column>
        <el-table-column label="任务" min-width="120"><template #default="{ row }">{{ taskLabel(row.task_id) }}</template></el-table-column>
        <el-table-column prop="group_id" label="小组" min-width="120" />
        <el-table-column prop="participant_id" label="参与者编码" min-width="160" />
        <el-table-column prop="participant_name" label="姓名" min-width="120" />
        <el-table-column prop="individual_score" label="个人 IS" width="100" sortable />
        <el-table-column prop="group_score" label="小组 GS" width="100" sortable />
        <el-table-column prop="improvement" label="改善 IS−GS" width="125" sortable />
        <el-table-column label="原组内位置" width="120"><template #default="{ row }">{{ positionLabel(row.member_position) }}</template></el-table-column>
      </el-table>
    </el-card>

    <el-alert
      v-if="report?.excluded_entries.length"
      :title="`${report.excluded_entries.length} 条小组记录未纳入个人分析`"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #default>
        <ul class="excluded-list">
          <li v-for="item in report.excluded_entries" :key="item.entry_id">{{ item.group_id }}：{{ item.note }}</li>
        </ul>
      </template>
    </el-alert>
  </div>
</template>

<style>
@import './admin-analysis.css';
</style>

<style scoped>
.analysis-page { gap: 16px; }
.control-form { grid-template-columns: minmax(220px, .8fr) minmax(280px, 1.1fr) minmax(300px, 1fr); }
.analysis-card { border: 1px solid #e3e9f2; border-radius: 8px; }
.table-card :deep(.el-card__body) { padding: 0; }
.card-title { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.card-title strong { color: #1e2d40; font-size: 14px; }
.card-title span, .plain-note, .summary-note { color: #64748b; font-size: 12px; }
.plain-note { margin: 8px 0 0; }
.summary-note { margin-top: 4px; }
.excluded-list { margin: 6px 0 0; padding-left: 20px; }
@media (max-width: 900px) { .control-form { grid-template-columns: 1fr; } }
</style>
