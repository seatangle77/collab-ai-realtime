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
import { buildIndividualTaskScoreReportHtml } from './task-score-individual/reportHelpers'

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
  return report.value?.individual_stats.find((item) => item.condition === condition)
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

function reportHtml() {
  return report.value ? buildIndividualTaskScoreReportHtml(report.value) : ''
}

function downloadHtmlReport() {
  if (!report.value) return ElMessage.warning('请先生成分析结果')
  const blob = new Blob([reportHtml()], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `task-score-individual-report-${filters.mode}-${new Date().toISOString().slice(0, 10)}.html`
  link.click()
  URL.revokeObjectURL(url)
}

function printReportAsPdf() {
  if (!report.value) return ElMessage.warning('请先生成分析结果')
  const printWindow = window.open('', '_blank')
  if (!printWindow) return ElMessage.error('浏览器阻止了打印窗口，请允许弹窗后重试')
  printWindow.document.open()
  printWindow.document.write(reportHtml())
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
        <h1>个人任务成绩分析</h1>
        <p>展示个人独立任务成绩，用于检查实验条件之间的个人能力基线。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!report" @click="downloadHtmlReport">下载匿名 HTML</el-button>
        <el-button :icon="Printer" :disabled="!report" @click="printReportAsPdf">打印/PDF</el-button>
        <el-button :icon="Refresh" :loading="loading" type="primary" @click="fetchReport">生成分析</el-button>
      </div>
    </div>

    <el-alert
      title="个人分数用于展示；实验条件按小组分配，因此推断统计以小组为聚类与置换单位，不会把同组3人当作独立实验单位。"
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
        <div class="card-title"><strong>个人分数描述统计</strong><span>分数越低表示越接近专家排序</span></div>
      </template>
      <el-table v-loading="loading" :data="conditionColumns" border>
        <el-table-column label="条件" min-width="150">
          <template #default="{ row }"><strong>{{ conditionLabel(row) }}</strong></template>
        </el-table-column>
        <el-table-column label="个人 n" width="100"><template #default="{ row }">{{ statFor(row)?.n ?? 0 }}</template></el-table-column>
        <el-table-column label="小组 n" width="100"><template #default="{ row }">{{ report?.groups_by_condition[row] ?? 0 }}</template></el-table-column>
        <el-table-column label="M" width="110"><template #default="{ row }">{{ formatNumber(statFor(row)?.mean ?? null) }}</template></el-table-column>
        <el-table-column label="SD" width="110"><template #default="{ row }">{{ formatNumber(statFor(row)?.sd ?? null) }}</template></el-table-column>
        <el-table-column label="Median" width="110"><template #default="{ row }">{{ formatNumber(statFor(row)?.median ?? null) }}</template></el-table-column>
        <el-table-column label="Min–Max" min-width="130"><template #default="{ row }">{{ formatNumber(statFor(row)?.min ?? null) }}–{{ formatNumber(statFor(row)?.max ?? null) }}</template></el-table-column>
      </el-table>
    </el-card>

    <IndividualScoreChart :observations="report?.observations ?? []" :conditions="conditionColumns" />

    <el-card class="analysis-card table-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>按任务分层</strong><span>检查条件差异是否可能来自任务难度</span></div>
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

    <el-card class="analysis-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>小组聚类置换检验</strong><span>同组3人始终作为一个整体</span></div>
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
        <div class="card-title"><strong>条件两两比较</strong><span>仅总体 p&lt;.05 时执行；负均值差表示条件 B 分数更低、表现更好</span></div>
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
        <el-table-column prop="score" label="个人分数" width="110" sortable />
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
