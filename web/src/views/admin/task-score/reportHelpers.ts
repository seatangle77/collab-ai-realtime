import type {
  MetricSummary,
  NormalityConditionResult,
  PostHocResult,
  StatisticalTestRecommendation,
  StatisticalTestResult,
  TaskScoreAnalysisMode,
  TaskScoreAnalysisResult,
  TaskScoreObservation,
  TaskScoreAnalysisTaskId,
} from '../../../api/admin/task-score-analysis'
import type { AdminGroup } from '../../../types/admin'
import {
  buildCsv,
  chartModalHtml,
  interactiveChartHtml,
  INTERACTIVE_CHART_CSS,
  INTERACTIVE_CHART_SCRIPT,
  type ReportLanguage,
} from './analysisExport'

export const CONDITION_LABELS: Record<string, string> = {
  no_assistance: '无辅助',
  glasses: '智能眼镜',
  app_notification: 'APP 通知',
}

export const CONDITION_LABELS_EN: Record<string, string> = {
  no_assistance: 'No Assistance',
  glasses: 'Smart Glasses',
  app_notification: 'App Notification',
}

export const TASK_OPTIONS: Array<{ label: string; value: TaskScoreAnalysisTaskId }> = [
  { label: '全部任务', value: 'all' },
  { label: 'NASA Moon Survival（月球求生）', value: 'moon_survival' },
  { label: 'Lost at Sea（海上求生）', value: 'lost_at_sea' },
  { label: 'Winter Survival（冬季求生）', value: 'winter_survival' },
]

export function conditionLabel(condition: string): string {
  return CONDITION_LABELS[condition] ?? condition
}

export function conditionLabelEn(condition: string): string {
  return CONDITION_LABELS_EN[condition] ?? condition
}

export function taskLabel(taskId: string): string {
  return TASK_OPTIONS.find((item) => item.value === taskId)?.label ?? taskId
}

export function modeDescription(mode: TaskScoreAnalysisMode): string {
  return mode === 'two_conditions'
    ? 'no_assistance vs glasses'
    : 'no_assistance / glasses / app_notification'
}

export function formatNumber(value: number | null): string {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
}

export function roleLabel(metric: Pick<MetricSummary, 'role'>): string {
  return metric.role === 'primary' ? '主要结果' : '基线检查'
}

export function normalityStatusLabel(item: NormalityConditionResult): string {
  if (item.status === 'ok') return item.is_normal ? '近似正态' : '偏离正态'
  if (item.status === 'insufficient_n') return '样本不足'
  if (item.status === 'constant_values') return '数值恒定'
  return '缺少依赖'
}

export function normalityTagType(item: NormalityConditionResult): 'success' | 'warning' | 'info' | 'danger' {
  if (item.status === 'ok') return item.is_normal ? 'success' : 'warning'
  if (item.status === 'dependency_missing') return 'danger'
  return 'info'
}

export function testLabel(test: StatisticalTestRecommendation['recommended_test']): string {
  const labels: Record<StatisticalTestRecommendation['recommended_test'], string> = {
    independent_samples_t_test: 'Independent-samples t-test',
    mann_whitney_u: 'Mann-Whitney U',
    one_way_anova: 'One-way ANOVA',
    kruskal_wallis: 'Kruskal-Wallis',
    insufficient_data: '样本不足',
  }
  return labels[test]
}

export function testStatusLabel(status: StatisticalTestResult['status']): string {
  const labels: Record<StatisticalTestResult['status'], string> = {
    ok: '已计算',
    insufficient_data: '样本不足',
    dependency_missing: '缺少依赖',
    calculation_error: '无法计算',
  }
  return labels[status]
}

export function pValueText(value: number | null): string {
  if (value === null || value === undefined) return '—'
  if (value < 0.001) return '< .001'
  return formatNumber(value)
}

export function statFor(metric: MetricSummary, condition: string) {
  return metric.conditions.find((entry) => entry.condition === condition)
}

export function meanDiffText(metric: MetricSummary): string {
  const baseline = statFor(metric, 'no_assistance')
  const comparison = statFor(metric, 'glasses')
  if (!baseline?.n || !comparison?.n || baseline.mean === null || comparison.mean === null) return '—'
  const diff = comparison.mean - baseline.mean
  return `${diff > 0 ? '+' : ''}${formatNumber(diff)}`
}

export function selectedGroupNames(
  condition: string,
  selectedGroupIdsByCondition: Record<string, string[]>,
  groupOptionsByCondition: Record<string, AdminGroup[]>,
): string {
  const selectedIds = new Set(selectedGroupIdsByCondition[condition] ?? [])
  const names = (groupOptionsByCondition[condition] ?? [])
    .filter((group) => selectedIds.has(group.id))
    .map((group) => group.name)
  if (names.length === 0) return '未选择'
  if (names.length <= 3) return names.join('、')
  return `${names.slice(0, 3).join('、')} 等 ${names.length} 组`
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

type PlotMetricKey = 'gs' | 'weak_synergy' | 'strong_synergy'

const TASK_SCORE_PLOT_METRICS: Array<{ key: PlotMetricKey; label: string; note: string }> = [
  { key: 'gs', label: 'GS Group Final Score', note: 'Lower scores indicate better group performance.' },
  { key: 'weak_synergy', label: 'Weak Synergy (AIS - GS)', note: 'Positive values indicate performance above the average individual.' },
  { key: 'strong_synergy', label: 'Strong Synergy (Best IS - GS)', note: 'Positive values indicate performance above the best individual.' },
]

const METRIC_LABELS_EN: Record<string, string> = {
  gs: 'GS Group Final Score',
  ais: 'AIS Mean Individual Score',
  best_is: 'Best IS',
  weak_synergy: 'Weak Synergy',
  strong_synergy: 'Strong Synergy',
}

const TASK_LABELS_EN: Record<string, string> = {
  all: 'All Tasks',
  moon_survival: 'NASA Moon Survival',
  lost_at_sea: 'Lost at Sea',
  winter_survival: 'Winter Survival',
}

interface ReportBoxStats {
  n: number
  min: number
  q1: number
  median: number
  q3: number
  max: number
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0
  if (sorted.length === 1) return sorted[0]!
  const pos = (sorted.length - 1) * p
  const lower = Math.floor(pos)
  const upper = Math.ceil(pos)
  if (lower === upper) return sorted[lower]!
  return sorted[lower]! + (sorted[upper]! - sorted[lower]!) * (pos - lower)
}

function boxStats(values: number[]): ReportBoxStats | null {
  const sorted = [...values].sort((a, b) => a - b)
  if (sorted.length === 0) return null
  return {
    n: sorted.length,
    min: sorted[0]!,
    q1: percentile(sorted, 0.25),
    median: percentile(sorted, 0.5),
    q3: percentile(sorted, 0.75),
    max: sorted[sorted.length - 1]!,
  }
}

function taskScoreBoxPlotSvg(
  observations: TaskScoreObservation[],
  conditionColumns: string[],
  metric: { key: PlotMetricKey; label: string; note: string },
): string {
  const boxes = conditionColumns.map((condition) => ({
    condition,
    stats: boxStats(observations.filter((obs) => obs.condition === condition).map((obs) => obs[metric.key])),
  }))
  const values = boxes.flatMap((box) => box.stats ? [box.stats.min, box.stats.q1, box.stats.median, box.stats.q3, box.stats.max] : [])
  if (values.length === 0) {
    return `<svg viewBox="0 0 720 250" role="img" aria-label="${escapeHtml(metric.label)}"><text x="360" y="125" text-anchor="middle">No data available</text></svg>`
  }
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const span = rawMax - rawMin || Math.max(1, Math.abs(rawMax) || 1)
  const min = rawMin - span * 0.12
  const max = rawMax + span * 0.12
  const y = (value: number) => 190 - ((value - min) / (max - min || 1)) * 150
  const x = (index: number) => boxes.length <= 1 ? 360 : 120 + index * (480 / (boxes.length - 1))
  const color = (condition: string) => condition === 'glasses' ? '#2563eb' : condition === 'app_notification' ? '#16a34a' : '#64748b'
  const tickValues = [max, (min + max) / 2, min]
  const ticks = tickValues.map((tick) => `
    <line x1="72" x2="660" y1="${y(tick)}" y2="${y(tick)}" class="grid-line" />
    <text x="62" y="${y(tick) + 4}" text-anchor="end" class="tick-label">${escapeHtml(formatNumber(tick))}</text>
  `).join('')
  const boxShapes = boxes.map((box, index) => {
    if (!box.stats) return ''
    const cx = x(index)
    const top = y(box.stats.q3)
    const height = Math.max(4, y(box.stats.q1) - y(box.stats.q3))
    return `
      <line x1="${cx}" x2="${cx}" y1="${y(box.stats.min)}" y2="${y(box.stats.max)}" class="whisker" />
      <line x1="${cx - 24}" x2="${cx + 24}" y1="${y(box.stats.min)}" y2="${y(box.stats.min)}" class="whisker" />
      <line x1="${cx - 24}" x2="${cx + 24}" y1="${y(box.stats.max)}" y2="${y(box.stats.max)}" class="whisker" />
      <rect x="${cx - 32}" y="${top}" width="64" height="${height}" rx="4" fill="${color(box.condition)}" fill-opacity="0.78" />
      <line x1="${cx - 32}" x2="${cx + 32}" y1="${y(box.stats.median)}" y2="${y(box.stats.median)}" class="median-line" />
      <text x="${cx}" y="218" text-anchor="middle" class="condition-label">${escapeHtml(conditionLabelEn(box.condition))}</text>
      <text x="${cx}" y="236" text-anchor="middle" class="tick-label">n=${box.stats.n}</text>
    `
  }).join('')
  return `
      <svg class="boxplot-svg" viewBox="0 0 720 250" role="img" aria-label="${escapeHtml(metric.label)}">
        <line x1="72" y1="40" x2="72" y2="190" class="axis-line" />
        <line x1="72" y1="190" x2="660" y2="190" class="axis-line" />
        ${ticks}
        ${boxShapes}
      <text x="18" y="125" transform="rotate(-90 18 125)" text-anchor="middle" class="axis-label">Score</text>
      </svg>
  `
}

function taskScoreBoxPlotsHtml(report: TaskScoreAnalysisResult, conditionColumns: string[], language: ReportLanguage): string {
  return TASK_SCORE_PLOT_METRICS.map((metric) => interactiveChartHtml(
    `${taskScoreBoxPlotSvg(report.observations, conditionColumns, metric)}<p class="note">${escapeHtml(metric.note)}</p>`,
    escapeHtml(metric.label),
    `task-score-${metric.key}.svg`,
    language,
  )).join('')
}

interface BuildReportHtmlParams {
  report: TaskScoreAnalysisResult
  mode: TaskScoreAnalysisMode
  taskId: TaskScoreAnalysisTaskId
  conditionColumns: string[]
  selectedGroupIdsByCondition: Record<string, string[]>
  groupOptionsByCondition: Record<string, AdminGroup[]>
}

function taskName(taskId: string, language: ReportLanguage): string {
  return language === 'en' ? (TASK_LABELS_EN[taskId] ?? taskId) : taskLabel(taskId)
}

function metricName(metric: Pick<MetricSummary, 'metric' | 'label'>, language: ReportLanguage): string {
  return language === 'en' ? (METRIC_LABELS_EN[metric.metric] ?? metric.metric) : metric.label
}

function conditionName(condition: string, language: ReportLanguage): string {
  return language === 'en' ? conditionLabelEn(condition) : conditionLabel(condition)
}

export function buildTaskScoreCsv(report: TaskScoreAnalysisResult): string {
  return buildCsv([
    ['entry_id', 'group_id', 'task', 'condition', 'gs', 'ais', 'best_is', 'weak_synergy', 'strong_synergy'],
    ...report.observations.map((item) => [
      item.entry_id, item.group_id, TASK_LABELS_EN[item.task_id] ?? item.task_id,
      conditionLabelEn(item.condition), item.gs, item.ais, item.best_is, item.weak_synergy, item.strong_synergy,
    ]),
  ])
}

export function buildTaskScoreReportHtml(params: BuildReportHtmlParams, language: ReportLanguage = 'zh'): string {
  const { report, mode, taskId, conditionColumns, selectedGroupIdsByCondition, groupOptionsByCondition } = params
  const zh = language === 'zh'
  const primaryNormality = report.normality.filter((item) => item.role === 'primary')
  const baselineNormality = report.normality.filter((item) => item.role === 'baseline')
  const primaryTests = report.statistical_tests.filter((item) => item.role === 'primary')
  const baselineTests = report.statistical_tests.filter((item) => item.role === 'baseline')
  const generatedAt = new Date().toLocaleString(zh ? 'zh-CN' : 'en-US')

  const descriptiveHeader = () => {
    const conditionHeaders = conditionColumns.map((condition) => `
      <th colspan="6">${escapeHtml(conditionName(condition, language))}</th>
    `).join('')
    const subHeaders = conditionColumns.map(() => `
      <th>n</th><th>M</th><th>SD</th><th>Median</th><th>Min</th><th>Max</th>
    `).join('')
    return `
      <tr>
        <th rowspan="2">${zh ? '指标' : 'Metric'}</th>
        <th rowspan="2">${zh ? '角色' : 'Role'}</th>
        ${conditionHeaders}
        ${mode === 'two_conditions' ? `<th rowspan="2">${zh ? '均值差' : 'Mean Difference'}</th>` : ''}
      </tr>
      <tr>${subHeaders}</tr>
    `
  }

  const descriptiveRows = report.metrics.map((metric) => {
    const conditionCells = conditionColumns.map((condition) => {
      const stat = statFor(metric, condition)
      return `
        <td>${stat?.n ?? 0}</td>
        <td>${escapeHtml(formatNumber(stat?.mean ?? null))}</td>
        <td>${escapeHtml(formatNumber(stat?.sd ?? null))}</td>
        <td>${escapeHtml(formatNumber(stat?.median ?? null))}</td>
        <td>${escapeHtml(formatNumber(stat?.min ?? null))}</td>
        <td>${escapeHtml(formatNumber(stat?.max ?? null))}</td>
      `
    }).join('')
    return `
      <tr>
        <th>${escapeHtml(metricName(metric, language))}</th>
        <td>${zh ? escapeHtml(roleLabel(metric)) : metric.role === 'primary' ? 'Primary outcome' : 'Baseline check'}</td>
        ${conditionCells}
        ${mode === 'two_conditions' ? `<td>${escapeHtml(meanDiffText(metric))}</td>` : ''}
      </tr>
    `
  }).join('')

  const normalityRows = (items: NormalityConditionResult[]) => items.map((item) => `
    <tr>
      <th>${escapeHtml(metricName(item, language))}</th>
      <td>${escapeHtml(conditionName(item.condition, language))}</td>
      <td>${item.n}</td>
      <td>${escapeHtml(formatNumber(item.statistic))}</td>
      <td>${escapeHtml(pValueText(item.p_value))}</td>
      <td>${zh ? escapeHtml(normalityStatusLabel(item)) : item.status === 'ok' ? (item.is_normal ? 'Approximately normal' : 'Non-normal') : 'Unavailable'}</td>
      <td>${zh ? escapeHtml(item.note) : 'p >= .05 is treated as approximately normal.'}</td>
    </tr>
  `).join('')

  const inferentialRows = (items: StatisticalTestResult[]) => items.map((item) => `
    <tr>
      <th>${escapeHtml(metricName(item, language))}</th>
      <td>${escapeHtml(zh ? testLabel(item.test) : ({
        independent_samples_t_test: 'Independent-samples t-test',
        mann_whitney_u: 'Mann-Whitney U',
        one_way_anova: 'One-way ANOVA',
        kruskal_wallis: 'Kruskal-Wallis',
        insufficient_data: 'Insufficient data',
      } as Record<string, string>)[item.test] ?? item.test)}</td>
      <td>${escapeHtml(item.statistic_name || '—')}</td>
      <td>${escapeHtml(formatNumber(item.statistic))}</td>
      <td>${escapeHtml(pValueText(item.p_value))}</td>
      <td>${escapeHtml(item.effect_size_name || '—')}</td>
      <td>${escapeHtml(formatNumber(item.effect_size))}</td>
      <td>${zh ? escapeHtml(testStatusLabel(item.status)) : item.status === 'ok' ? 'Calculated' : 'Unavailable'}</td>
      <td>${zh ? escapeHtml(item.note) : 'Two-sided group comparison; see method and effect size columns.'}</td>
    </tr>
  `).join('')

  const postHocMethodLabel = (method: PostHocResult['method']) =>
    method === 'tukey_hsd' ? 'Tukey HSD' : method === 'dunn_bonferroni' ? 'Dunn + Bonferroni' : '—'

  const postHocSection = (items: PostHocResult[]) => items.map((item) => {
    if (item.status !== 'ok' || item.pairs.length === 0) {
      return `<p class="note"><strong>${escapeHtml(metricName(item as any, language))}</strong>: ${zh ? escapeHtml(item.note) : 'The omnibus test was not significant; no post-hoc comparison was run.'}</p>`
    }
    const pairRows = item.pairs.map((pair) => `
      <tr>
        <td>${escapeHtml(conditionName(pair.condition_a, language))}</td>
        <td>${escapeHtml(conditionName(pair.condition_b, language))}</td>
        <td style="text-align:right">${escapeHtml(formatNumber(pair.mean_diff))}</td>
        <td style="text-align:right">${escapeHtml(pValueText(pair.p_value_adjusted))}</td>
        <td style="text-align:center">${pair.significant === true ? '*' : pair.significant === false ? 'ns' : '—'}</td>
      </tr>
    `).join('')
    return `
      <h3>${escapeHtml(metricName(item as any, language))} (${escapeHtml(postHocMethodLabel(item.method))})</h3>
      <table><thead><tr><th>${zh ? '条件 A' : 'Condition A'}</th><th>${zh ? '条件 B' : 'Condition B'}</th><th>${zh ? '均值差 (B−A)' : 'Mean Difference (B−A)'}</th><th>${zh ? 'p (校正后)' : 'Adjusted p'}</th><th>${zh ? '显著' : 'Significant'}</th></tr></thead><tbody>${pairRows}</tbody></table>
    `
  }).join('')

  const sampleRows = conditionColumns.map((condition) => `
    <tr>
      <th>${escapeHtml(conditionName(condition, language))}</th>
      <td>${selectedGroupIdsByCondition[condition]?.length ?? 0}</td>
      <td>${zh ? escapeHtml(selectedGroupNames(condition, selectedGroupIdsByCondition, groupOptionsByCondition)) : escapeHtml((selectedGroupIdsByCondition[condition] ?? []).join(', '))}</td>
    </tr>
  `).join('')

  return `<!doctype html>
<html lang="${zh ? 'zh-CN' : 'en'}">
<head>
  <meta charset="utf-8" />
  <title>${zh ? '任务分数统计分析报告' : 'Task Score Statistical Analysis Report'}</title>
  <style>
    body { margin: 32px; color: #111827; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.5; }
    h1 { margin: 0 0 8px; font-size: 24px; }
    h2 { margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #d1d5db; font-size: 17px; }
    h3 { margin: 18px 0 8px; font-size: 14px; }
    .meta { color: #4b5563; font-size: 12px; }
    .note { margin: 10px 0; color: #374151; font-size: 12px; }
    table { width: 100%; margin: 10px 0 18px; border-collapse: collapse; font-size: 12px; page-break-inside: avoid; }
    th, td { padding: 7px 8px; border: 1px solid #d1d5db; text-align: left; vertical-align: top; }
    th { background: #f3f4f6; font-weight: 700; }
    .numeric td, .numeric th { text-align: right; }
    .numeric th:first-child, .numeric td:first-child, .numeric td:nth-child(2), .numeric th:nth-child(2) { text-align: left; }
    .section-note { color: #6b7280; font-size: 12px; }
    .boxplot-svg { width: 100%; height: auto; }
    .axis-line, .whisker { stroke: #64748b; stroke-width: 1.4; }
    .grid-line { stroke: #d9e2ef; stroke-width: 1; }
    .median-line { stroke: #111827; stroke-width: 2; }
    .tick-label, .condition-label, .axis-label { fill: #64748b; font-size: 11px; }
    .condition-label { fill: #172033; font-weight: 700; }
    ${INTERACTIVE_CHART_CSS}
    @media print { body { margin: 18mm; } h2 { page-break-after: avoid; } }
  </style>
</head>
<body>
  <h1>${zh ? '任务分数统计分析报告' : 'Task Score Statistical Analysis Report'}</h1>
  <div class="meta">${zh ? '生成时间' : 'Generated'}: ${escapeHtml(generatedAt)}</div>
  <div class="meta">${zh ? '分析模式' : 'Mode'}: ${escapeHtml(modeDescription(mode))}; ${zh ? '任务' : 'Task'}: ${escapeHtml(taskName(taskId, language))}; ${zh ? '纳入记录数' : 'Included records'}: ${report.total_entries}</div>
  <h2>1. ${zh ? '分析方法' : 'Analysis Method'}</h2>
  <p class="note">${zh ? '任务分数越低表示表现越好。弱协同值 = AIS − GS；强协同值 = Best IS − GS；正协同值表示小组超过相应个人基线。' : 'Lower task scores indicate better performance. Weak synergy = AIS − GS; strong synergy = Best IS − GS. Positive synergy indicates that the group outperformed the corresponding individual baseline.'}</p>
  <p class="note">${zh ? '主要结果为 GS、弱协同和强协同；AIS 与 Best IS 用于基线检查。根据正态性选择参数或非参数组间检验。' : 'Primary outcomes are GS, weak synergy, and strong synergy. AIS and Best IS are baseline checks. Parametric or non-parametric group comparisons are selected based on normality.'}</p>
  <h2>2. ${zh ? '样本选择' : 'Sample Selection'}</h2>
  <table><thead><tr><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '小组数' : 'Groups'}</th><th>${zh ? '小组' : 'Group IDs'}</th></tr></thead><tbody>${sampleRows}</tbody></table>
  <h2>3. ${zh ? '描述性统计' : 'Descriptive Statistics'}</h2>
  <p class="section-note">M = mean; SD = standard deviation.</p>
  <table class="numeric"><thead>${descriptiveHeader()}</thead><tbody>${descriptiveRows}</tbody></table>
  <h2>4. ${zh ? '正态性检查' : 'Normality Checks'}</h2>
  <h3>${zh ? '主要结果指标' : 'Primary Outcomes'}</h3>
  <table><thead><tr><th>${zh ? '指标' : 'Metric'}</th><th>${zh ? '条件' : 'Condition'}</th><th>n</th><th>W</th><th>p</th><th>${zh ? '判断' : 'Assessment'}</th><th>${zh ? '说明' : 'Note'}</th></tr></thead><tbody>${normalityRows(primaryNormality)}</tbody></table>
  <h3>${zh ? '基线检查指标' : 'Baseline Checks'}</h3>
  <table><thead><tr><th>${zh ? '指标' : 'Metric'}</th><th>${zh ? '条件' : 'Condition'}</th><th>n</th><th>W</th><th>p</th><th>${zh ? '判断' : 'Assessment'}</th><th>${zh ? '说明' : 'Note'}</th></tr></thead><tbody>${normalityRows(baselineNormality)}</tbody></table>
  <h2>5. ${zh ? '结果图表' : 'Result Charts'}</h2>
  <p class="section-note">${zh ? '所有图表统一使用英文；点击图表可大幅放大，也可下载为 SVG。' : 'All chart text is in English. Click a chart to enlarge it or download it as SVG.'}</p>
  ${taskScoreBoxPlotsHtml(report, conditionColumns, language)}
  <h2>6. ${zh ? '推断统计' : 'Inferential Statistics'}</h2>
  <h3>${zh ? '主要结果指标' : 'Primary Outcomes'}</h3>
  <table><thead><tr><th>${zh ? '指标' : 'Metric'}</th><th>${zh ? '检验' : 'Test'}</th><th>${zh ? '统计量' : 'Statistic'}</th><th>${zh ? '值' : 'Value'}</th><th>p</th><th>Effect size</th><th>${zh ? '值' : 'Value'}</th><th>${zh ? '状态' : 'Status'}</th><th>${zh ? '说明' : 'Note'}</th></tr></thead><tbody>${inferentialRows(primaryTests)}</tbody></table>
  <h3>${zh ? '基线检查指标' : 'Baseline Checks'}</h3>
  <table><thead><tr><th>${zh ? '指标' : 'Metric'}</th><th>${zh ? '检验' : 'Test'}</th><th>${zh ? '统计量' : 'Statistic'}</th><th>${zh ? '值' : 'Value'}</th><th>p</th><th>Effect size</th><th>${zh ? '值' : 'Value'}</th><th>${zh ? '状态' : 'Status'}</th><th>${zh ? '说明' : 'Note'}</th></tr></thead><tbody>${inferentialRows(baselineTests)}</tbody></table>
  ${mode !== 'two_conditions' ? `<h2>7. ${zh ? '事后检验' : 'Post-hoc Tests'}</h2>
  <p class="section-note">${zh ? '仅总体检验 p < .05 时执行。' : 'Run only when the omnibus test has p < .05.'}</p>
  ${postHocSection(report.post_hoc_tests.filter(t => t.role === 'primary'))}` : ''}
  <h2>8. ${zh ? '备注' : 'Notes'}</h2>
  <p class="note">${zh ? '本报告为即时计算结果，未自动入库。' : 'This report is generated from the current analysis and is not automatically stored as an immutable snapshot.'}</p>
  ${chartModalHtml(language)}
  ${INTERACTIVE_CHART_SCRIPT}
</body>
</html>`
}
