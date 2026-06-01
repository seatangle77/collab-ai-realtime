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

export const CONDITION_LABELS: Record<string, string> = {
  no_assistance: '无辅助',
  glasses: '智能眼镜',
  app_notification: 'APP 通知',
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
  { key: 'gs', label: 'GS 小组最终分数', note: '任务分数越低表示小组最终表现越好。' },
  { key: 'weak_synergy', label: '弱协同值（AIS - GS）', note: '正值表示小组表现优于成员平均个人水平。' },
  { key: 'strong_synergy', label: '强协同值（Best IS - GS）', note: '正值表示小组表现优于组内最佳个人水平。' },
]

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
    return `<div class="chart-card"><h3>${escapeHtml(metric.label)}</h3><p class="note">暂无可绘制数据。</p></div>`
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
      <text x="${cx}" y="218" text-anchor="middle" class="condition-label">${escapeHtml(conditionLabel(box.condition))}</text>
      <text x="${cx}" y="236" text-anchor="middle" class="tick-label">n=${box.stats.n}</text>
    `
  }).join('')
  return `
    <div class="chart-card">
      <h3>${escapeHtml(metric.label)}</h3>
      <svg class="boxplot-svg" viewBox="0 0 720 250" role="img" aria-label="${escapeHtml(metric.label)}">
        <line x1="72" y1="40" x2="72" y2="190" class="axis-line" />
        <line x1="72" y1="190" x2="660" y2="190" class="axis-line" />
        ${ticks}
        ${boxShapes}
      </svg>
      <p class="note">${escapeHtml(metric.note)}</p>
    </div>
  `
}

function taskScoreBoxPlotsHtml(report: TaskScoreAnalysisResult, conditionColumns: string[]): string {
  return `
    <div class="chart-grid">
      ${TASK_SCORE_PLOT_METRICS.map((metric) => taskScoreBoxPlotSvg(report.observations, conditionColumns, metric)).join('')}
    </div>
  `
}

interface BuildReportHtmlParams {
  report: TaskScoreAnalysisResult
  mode: TaskScoreAnalysisMode
  taskId: TaskScoreAnalysisTaskId
  conditionColumns: string[]
  selectedGroupIdsByCondition: Record<string, string[]>
  groupOptionsByCondition: Record<string, AdminGroup[]>
}

export function buildTaskScoreReportHtml(params: BuildReportHtmlParams): string {
  const { report, mode, taskId, conditionColumns, selectedGroupIdsByCondition, groupOptionsByCondition } = params
  const primaryNormality = report.normality.filter((item) => item.role === 'primary')
  const baselineNormality = report.normality.filter((item) => item.role === 'baseline')
  const primaryTests = report.statistical_tests.filter((item) => item.role === 'primary')
  const baselineTests = report.statistical_tests.filter((item) => item.role === 'baseline')
  const generatedAt = new Date().toLocaleString()
  const taskLabel = TASK_OPTIONS.find((task) => task.value === taskId)?.label ?? taskId

  const descriptiveHeader = () => {
    const conditionHeaders = conditionColumns.map((condition) => `
      <th colspan="6">${escapeHtml(conditionLabel(condition))}</th>
    `).join('')
    const subHeaders = conditionColumns.map(() => `
      <th>n</th><th>M</th><th>SD</th><th>Median</th><th>Min</th><th>Max</th>
    `).join('')
    return `
      <tr>
        <th rowspan="2">指标</th>
        <th rowspan="2">角色</th>
        ${conditionHeaders}
        ${mode === 'two_conditions' ? '<th rowspan="2">均值差</th>' : ''}
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
        <th>${escapeHtml(metric.label)}</th>
        <td>${escapeHtml(roleLabel(metric))}</td>
        ${conditionCells}
        ${mode === 'two_conditions' ? `<td>${escapeHtml(meanDiffText(metric))}</td>` : ''}
      </tr>
    `
  }).join('')

  const normalityRows = (items: NormalityConditionResult[]) => items.map((item) => `
    <tr>
      <th>${escapeHtml(item.label)}</th>
      <td>${escapeHtml(conditionLabel(item.condition))}</td>
      <td>${item.n}</td>
      <td>${escapeHtml(formatNumber(item.statistic))}</td>
      <td>${escapeHtml(pValueText(item.p_value))}</td>
      <td>${escapeHtml(normalityStatusLabel(item))}</td>
      <td>${escapeHtml(item.note)}</td>
    </tr>
  `).join('')

  const inferentialRows = (items: StatisticalTestResult[]) => items.map((item) => `
    <tr>
      <th>${escapeHtml(item.label)}</th>
      <td>${escapeHtml(testLabel(item.test))}</td>
      <td>${escapeHtml(item.statistic_name || '—')}</td>
      <td>${escapeHtml(formatNumber(item.statistic))}</td>
      <td>${escapeHtml(pValueText(item.p_value))}</td>
      <td>${escapeHtml(item.effect_size_name || '—')}</td>
      <td>${escapeHtml(formatNumber(item.effect_size))}</td>
      <td>${escapeHtml(testStatusLabel(item.status))}</td>
      <td>${escapeHtml(item.note)}</td>
    </tr>
  `).join('')

  const postHocMethodLabel = (method: PostHocResult['method']) =>
    method === 'tukey_hsd' ? 'Tukey HSD' : method === 'dunn_bonferroni' ? 'Dunn + Bonferroni' : '—'

  const postHocSection = (items: PostHocResult[]) => items.map((item) => {
    if (item.status !== 'ok' || item.pairs.length === 0) {
      return `<p class="note"><strong>${escapeHtml(item.label)}</strong>：${escapeHtml(item.note)}</p>`
    }
    const pairRows = item.pairs.map((pair) => `
      <tr>
        <td>${escapeHtml(conditionLabel(pair.condition_a))}</td>
        <td>${escapeHtml(conditionLabel(pair.condition_b))}</td>
        <td style="text-align:right">${escapeHtml(formatNumber(pair.mean_diff))}</td>
        <td style="text-align:right">${escapeHtml(pValueText(pair.p_value_adjusted))}</td>
        <td style="text-align:center">${pair.significant === true ? '*' : pair.significant === false ? 'ns' : '—'}</td>
      </tr>
    `).join('')
    return `
      <h3>${escapeHtml(item.label)}（${escapeHtml(postHocMethodLabel(item.method))}）</h3>
      <table><thead><tr><th>条件 A</th><th>条件 B</th><th>均值差 (B−A)</th><th>p (校正后)</th><th>显著</th></tr></thead><tbody>${pairRows}</tbody></table>
    `
  }).join('')

  const sampleRows = conditionColumns.map((condition) => `
    <tr>
      <th>${escapeHtml(conditionLabel(condition))}</th>
      <td>${selectedGroupIdsByCondition[condition]?.length ?? 0}</td>
      <td>${escapeHtml(selectedGroupNames(condition, selectedGroupIdsByCondition, groupOptionsByCondition))}</td>
    </tr>
  `).join('')

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>任务分数统计分析报告</title>
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
    .chart-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 10px 0 18px; }
    .chart-card { padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; background: #f8fafc; page-break-inside: avoid; }
    .chart-card h3 { margin-top: 0; }
    .boxplot-svg { width: 100%; height: auto; }
    .axis-line, .whisker { stroke: #64748b; stroke-width: 1.4; }
    .grid-line { stroke: #d9e2ef; stroke-width: 1; }
    .median-line { stroke: #111827; stroke-width: 2; }
    .tick-label, .condition-label { fill: #64748b; font-size: 11px; }
    .condition-label { fill: #172033; font-weight: 700; }
    @media (max-width: 900px) { .chart-grid { grid-template-columns: 1fr; } }
    @media print { body { margin: 18mm; } h2 { page-break-after: avoid; } }
  </style>
</head>
<body>
  <h1>任务分数统计分析报告</h1>
  <div class="meta">生成时间：${escapeHtml(generatedAt)}</div>
  <div class="meta">分析模式：${escapeHtml(modeDescription(mode))}；任务：${escapeHtml(taskLabel)}；纳入记录数：${report.total_entries}</div>
  <h2>1. 分析方法</h2>
  <p class="note">任务分数越低表示表现越好。弱协同值 = AIS - GS；强协同值 = Best IS - GS。协同值为正表示小组最终表现优于对应个人基线，协同值为负表示可能存在过程损失。</p>
  <p class="note">主要结果指标为 GS、弱协同值、强协同值；AIS 和 Best IS 用于检查不同条件下讨论前个人基线是否接近。正态性使用 Shapiro-Wilk test；两条件根据正态性使用 Welch independent-samples t-test 或 Mann-Whitney U test；三条件使用 one-way ANOVA 或 Kruskal-Wallis。</p>
  <h2>2. 样本选择</h2>
  <table><thead><tr><th>条件</th><th>小组数</th><th>小组</th></tr></thead><tbody>${sampleRows}</tbody></table>
  <h2>3. 描述性统计</h2>
  <p class="section-note">M = mean；SD = standard deviation。</p>
  <table class="numeric"><thead>${descriptiveHeader()}</thead><tbody>${descriptiveRows}</tbody></table>
  <h2>4. 正态性检查</h2>
  <h3>主要结果指标</h3>
  <table><thead><tr><th>指标</th><th>条件</th><th>n</th><th>W</th><th>p</th><th>判断</th><th>说明</th></tr></thead><tbody>${normalityRows(primaryNormality)}</tbody></table>
  <h3>基线检查指标</h3>
  <table><thead><tr><th>指标</th><th>条件</th><th>n</th><th>W</th><th>p</th><th>判断</th><th>说明</th></tr></thead><tbody>${normalityRows(baselineNormality)}</tbody></table>
  <h2>5. 报告结果与可视化</h2>
  <p class="section-note">箱线图展示主要结果指标在各条件下的分布；p 值与 effect size 见下方推断统计表。</p>
  ${taskScoreBoxPlotsHtml(report, conditionColumns)}
  <h2>6. 推断统计</h2>
  <h3>主要结果指标</h3>
  <table><thead><tr><th>指标</th><th>检验</th><th>统计量</th><th>值</th><th>p</th><th>Effect size</th><th>值</th><th>状态</th><th>说明</th></tr></thead><tbody>${inferentialRows(primaryTests)}</tbody></table>
  <h3>基线检查指标</h3>
  <table><thead><tr><th>指标</th><th>检验</th><th>统计量</th><th>值</th><th>p</th><th>Effect size</th><th>值</th><th>状态</th><th>说明</th></tr></thead><tbody>${inferentialRows(baselineTests)}</tbody></table>
  <h2>7. 事后检验（Post-hoc）</h2>
  <p class="section-note">仅三条件且全局检验 p &lt; 0.05 时执行；Tukey HSD 用于 ANOVA，Dunn + Bonferroni 用于 Kruskal-Wallis。均值差 = 条件 B 均值 − 条件 A 均值。</p>
  ${postHocSection(report.post_hoc_tests.filter(t => t.role === 'primary'))}
  <h2>8. 备注</h2>
  <p class="note">本报告为即时计算结果，未自动入库。若用于正式论文或归档，建议保存本报告 HTML/PDF，并记录所选小组样本。</p>
</body>
</html>`
}
