import type { TaskScoreIndividualAnalysisResult } from '../../../api/admin/task-score-individual-analysis'
import { conditionLabel, conditionLabelEn, formatNumber, taskLabel } from '../task-score/reportHelpers'
import {
  buildCsv,
  chartModalHtml,
  interactiveChartHtml,
  INTERACTIVE_CHART_CSS,
  INTERACTIVE_CHART_SCRIPT,
  type ReportLanguage,
} from '../task-score/analysisExport'

function esc(value: unknown): string {
  return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

const TASK_LABELS_EN: Record<string, string> = {
  all: 'All Tasks',
  moon_survival: 'NASA Moon Survival',
  lost_at_sea: 'Lost at Sea',
  winter_survival: 'Winter Survival',
}

const POSITION_LABELS = {
  zh: { best: '原最佳成员', middle: '原中间成员', weakest: '原最弱成员' },
  en: { best: 'Initially Best Member', middle: 'Initially Middle Member', weakest: 'Initially Weakest Member' },
} as const

function conditionName(condition: string, language: ReportLanguage): string {
  return language === 'zh' ? conditionLabel(condition) : conditionLabelEn(condition)
}

function taskName(taskId: string, language: ReportLanguage): string {
  return language === 'zh' ? taskLabel(taskId) : (TASK_LABELS_EN[taskId] ?? taskId)
}

function positionName(position: string, language: ReportLanguage): string {
  return (POSITION_LABELS[language] as Record<string, string>)[position] ?? position
}

function pairedScoreSvg(report: TaskScoreIndividualAnalysisResult): string {
  const width = 1200
  const height = 500
  const margin = { top: 56, right: 34, bottom: 78, left: 78 }
  const plotHeight = height - margin.top - margin.bottom
  const panelWidth = (width - margin.left - margin.right) / Math.max(1, report.conditions.length)
  const values = report.observations.flatMap((item) => [item.individual_score, item.group_score])
  const maxScore = Math.max(10, Math.ceil((Math.max(...values, 0) + 5) / 10) * 10)
  const y = (score: number) => margin.top + (score / maxScore) * plotHeight
  const ticks = Array.from({ length: 6 }, (_, index) => Math.round((maxScore * index) / 5))
  const grid = ticks.map((tick) => `<line x1="${margin.left}" x2="${width - margin.right}" y1="${y(tick)}" y2="${y(tick)}" class="grid-line"/><text x="${margin.left - 12}" y="${y(tick) + 4}" text-anchor="end" class="tick-label">${tick}</text>`).join('')
  const panels = report.conditions.map((condition, index) => {
    const panelLeft = margin.left + panelWidth * index
    const divider = index ? `<line x1="${panelLeft}" x2="${panelLeft}" y1="${margin.top - 22}" y2="${height - margin.bottom + 14}" class="divider"/>` : ''
    return `${divider}<text x="${panelLeft + panelWidth * .5}" y="28" text-anchor="middle" class="condition-label">${esc(conditionLabelEn(condition))}</text><text x="${panelLeft + panelWidth * .28}" y="${height - 35}" text-anchor="middle" class="phase-label">Individual IS</text><text x="${panelLeft + panelWidth * .72}" y="${height - 35}" text-anchor="middle" class="phase-label">Group GS</text>`
  }).join('')
  const lines = report.conditions.flatMap((condition, conditionIndex) => {
    const rows = report.observations.filter((item) => item.condition === condition)
    const panelLeft = margin.left + panelWidth * conditionIndex
    return rows.map((item, index) => {
      const jitter = ((index * 13) % 31) - 15
      const x1 = panelLeft + panelWidth * .28 + jitter
      const x2 = panelLeft + panelWidth * .72 + jitter
      const color = item.improvement > 0 ? '#16a34a' : item.improvement < 0 ? '#dc2626' : '#64748b'
      return `<g><line x1="${x1}" y1="${y(item.individual_score)}" x2="${x2}" y2="${y(item.group_score)}" stroke="${color}" stroke-width="2.5" stroke-opacity=".64"/><circle cx="${x1}" cy="${y(item.individual_score)}" r="4.8" fill="${color}" stroke="#fff" stroke-width="1"><title>${esc(item.participant_id)}: IS ${item.individual_score}</title></circle><circle cx="${x2}" cy="${y(item.group_score)}" r="4.8" fill="${color}" stroke="#fff" stroke-width="1"><title>${esc(item.group_id)}: GS ${item.group_score}; improvement ${item.improvement}</title></circle></g>`
    })
  }).join('')
  return `<svg class="paired-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Paired individual and group final scores"><defs><style>text{font-family:Arial,Helvetica,sans-serif;text-rendering:geometricPrecision}.grid-line{stroke:#d4dde9;stroke-width:1.25}.axis{stroke:#64748b;stroke-width:1.8}.divider{stroke:#94a3b8;stroke-width:1.25;stroke-dasharray:4 5}.tick-label{fill:#334155;font-size:15px;font-weight:650}.axis-label{fill:#1e293b;font-size:16px;font-weight:700}.phase-label{fill:#334155;font-size:15px;font-weight:700}.condition-label{fill:#0f172a;font-size:19px;font-weight:800}.legend text{font-size:15px;font-weight:700}</style></defs>${grid}<line x1="${margin.left}" x2="${margin.left}" y1="${margin.top}" y2="${height - margin.bottom}" class="axis"/>${panels}${lines}<text x="22" y="250" transform="rotate(-90 22 250)" text-anchor="middle" class="axis-label">Task Score (lower = better)</text><g class="legend"><text x="350" y="488" fill="#16a34a">● Group better</text><text x="535" y="488" fill="#dc2626">● Group worse</text><text x="720" y="488" fill="#64748b">● Unchanged</text></g></svg>`
}

export function buildIndividualTaskScoreCsv(report: TaskScoreIndividualAnalysisResult): string {
  return buildCsv([
    ['condition', 'task', 'group_id', 'participant_id', 'individual_is', 'group_gs', 'improvement_is_minus_gs', 'initial_member_position'],
    ...report.observations.map((item) => [
      conditionLabelEn(item.condition), TASK_LABELS_EN[item.task_id] ?? item.task_id, item.group_id,
      item.participant_id, item.individual_score, item.group_score, item.improvement, positionName(item.member_position, 'en'),
    ]),
  ])
}

export function buildIndividualTaskScoreReportHtml(report: TaskScoreIndividualAnalysisResult, language: ReportLanguage = 'zh'): string {
  const zh = language === 'zh'
  const conditionHeaders = report.conditions.map((condition) => `<th>${esc(conditionName(condition, language))}</th>`).join('')
  const improvementRows = report.improvement_summaries.map((item) => `<tr><th>${esc(conditionName(item.condition, language))}</th><td>${item.individual_count}/${item.group_count}</td><td>${formatNumber(item.mean)}</td><td>${formatNumber(item.sd)}</td><td>${formatNumber(item.median)}</td><td>${item.improved_count}</td><td>${item.unchanged_count}</td><td>${item.worsened_count}</td><td>${formatNumber(item.improved_percentage)}%</td></tr>`).join('')
  const taskRows = report.task_summaries.map((task) => `<tr><th>${esc(taskName(task.task_id, language))}</th>${report.conditions.map((condition) => {
    const item = task.conditions.find((row) => row.condition === condition)
    return `<td>n=${item?.n ?? 0}; ${zh ? '平均改善' : 'mean improvement'}=${formatNumber(item?.mean ?? null)}; SD=${formatNumber(item?.sd ?? null)}</td>`
  }).join('')}</tr>`).join('')
  const positionRows = report.member_position_summaries.map((position) => `<tr><th>${esc(positionName(position.position, language))}</th>${report.conditions.map((condition) => {
    const item = position.conditions.find((row) => row.condition === condition)
    return `<td>n=${item?.n ?? 0}; ${zh ? '平均改善' : 'mean improvement'}=${formatNumber(item?.mean ?? null)}</td>`
  }).join('')}</tr>`).join('')
  const baselineCells = report.conditions.map((condition) => {
    const item = report.baseline_stats.find((row) => row.condition === condition)
    return `<td>n=${item?.n ?? 0}; M=${formatNumber(item?.mean ?? null)}; SD=${formatNumber(item?.sd ?? null)}; Median=${formatNumber(item?.median ?? null)}</td>`
  }).join('')
  const withinRows = report.within_condition_tests.map((item) => {
    const conclusion = item.status !== 'ok'
      ? (zh ? '数据不足' : 'Insufficient data')
      : item.significant
        ? (Number(item.mean_group_improvement) > 0 ? (zh ? '显著改善' : 'Significant improvement') : (zh ? '显著变差' : 'Significant worsening'))
        : (zh ? '未检出显著变化' : 'No significant change')
    return `<tr><th>${esc(conditionName(item.condition, language))}</th><td>${item.group_count}</td><td>${formatNumber(item.mean_group_improvement)}</td><td>${formatNumber(item.p_value)}</td><td>${formatNumber(item.p_value_adjusted)}</td><td>${formatNumber(item.effect_size)}</td><td>${conclusion}</td></tr>`
  }).join('')
  const pairRows = report.pairwise_tests.length
    ? report.pairwise_tests.map((item) => `<tr><td>${esc(conditionName(item.condition_a, language))}</td><td>${esc(conditionName(item.condition_b, language))}</td><td>${formatNumber(item.mean_difference)}</td><td>${formatNumber(item.p_value)}</td><td>${formatNumber(item.p_value_adjusted)}</td><td>${item.significant ? (zh ? '是' : 'Yes') : (zh ? '否' : 'No')}</td></tr>`).join('')
    : `<tr><td colspan="6">${report.conditions.length < 3 ? (zh ? '当前模式无需三条件事后比较' : 'Post-hoc comparison is not required in this mode.') : (zh ? '总体检验未达到显著水平，不执行事后比较' : 'The omnibus test was not significant; no post-hoc comparison was run.')}</td></tr>`
  const details = report.observations.map((item) => `<tr><td>${esc(conditionName(item.condition, language))}</td><td>${esc(taskName(item.task_id, language))}</td><td>${esc(item.group_id)}</td><td>${esc(item.participant_id)}</td><td>${formatNumber(item.individual_score)}</td><td>${formatNumber(item.group_score)}</td><td>${formatNumber(item.improvement)}</td><td>${esc(positionName(item.member_position, language))}</td></tr>`).join('')
  const chart = interactiveChartHtml(pairedScoreSvg(report), 'Individual Score → Group Final Score', 'individual-to-group-paired-scores.svg', language)

  return `<!doctype html><html lang="${zh ? 'zh-CN' : 'en'}"><head><meta charset="utf-8"><title>${zh ? '个人到小组成绩变化分析报告' : 'Individual-to-Group Score Change Report'}</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#172033;margin:32px;line-height:1.55}h1{margin-bottom:4px}h2{margin-top:28px;padding-bottom:6px;border-bottom:1px solid #dbe3ee}p.note{color:#526071;background:#f8fafc;padding:12px 14px;border-left:4px solid #2563eb}table{width:100%;border-collapse:collapse;margin:12px 0}th,td{border:1px solid #dbe3ee;padding:8px 10px;text-align:left;vertical-align:top}th{background:#f4f7fb}.ok{color:#047857}.warning{color:#b45309}.paired-svg{font-family:Arial,"Helvetica Neue",sans-serif;text-rendering:geometricPrecision}.paired-svg .grid-line{stroke:#d4dde9;stroke-width:1.25}.paired-svg .axis{stroke:#64748b;stroke-width:1.8}.paired-svg .divider{stroke:#94a3b8;stroke-width:1.25;stroke-dasharray:4 5}.paired-svg .tick-label{fill:#334155;font-size:15px;font-weight:650}.paired-svg .axis-label{fill:#1e293b;font-size:16px;font-weight:700}.paired-svg .phase-label{fill:#334155;font-size:15px;font-weight:700}.paired-svg .condition-label{fill:#0f172a;font-size:19px;font-weight:800}.paired-svg .legend text{font-size:15px;font-weight:700}${INTERACTIVE_CHART_CSS}@media print{body{margin:12mm}}
</style></head><body><h1>${zh ? '个人到小组成绩变化分析报告' : 'Individual-to-Group Score Change Report'}</h1><p>${zh ? '生成时间' : 'Generated'}: ${esc(new Date().toLocaleString(zh ? 'zh-CN' : 'en-US'))}</p>
<p class="note"><strong>${zh ? '口径' : 'Definition'}:</strong> ${zh ? '改善值 = 个人独立分 IS − 小组最终分 GS。分数越低越好，因此正值表示小组答案更好。这不是个人前测—个人后测；同组三人共享一个 GS，推断统计以小组为单位。' : 'Improvement = individual score (IS) − group final score (GS). Lower scores are better, so a positive value indicates a better group answer. This is not an individual pretest–posttest; three members share one GS, and inference uses the group as the independent unit.'}</p>
<h2>${zh ? '样本' : 'Sample'}</h2><table><tr><th>${zh ? '总个人数' : 'Total individuals'}</th><td>${report.total_individuals}</td><th>${zh ? '总小组数' : 'Total groups'}</th><td>${report.total_groups}</td></tr>${report.conditions.map((condition) => `<tr><th>${esc(conditionName(condition, language))}</th><td>${report.individuals_by_condition[condition] ?? 0}</td><th>${zh ? '独立小组' : 'Independent groups'}</th><td>${report.groups_by_condition[condition] ?? 0}</td></tr>`).join('')}</table>
<h2>${zh ? '个人到小组改善' : 'Individual-to-Group Improvement'}</h2><table><tr><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '个人/小组 n' : 'Individuals/Groups n'}</th><th>${zh ? '平均改善' : 'Mean Improvement'}</th><th>SD</th><th>Median</th><th>${zh ? '改善' : 'Improved'}</th><th>${zh ? '不变' : 'Unchanged'}</th><th>${zh ? '变差' : 'Worsened'}</th><th>${zh ? '改善比例' : 'Improved %'}</th></tr>${improvementRows}</table>
<h2>${zh ? '各条件内是否整体改善' : 'Within-Condition Improvement Tests'}</h2><table><tr><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '独立小组 n' : 'Independent Groups n'}</th><th>${zh ? '小组平均改善' : 'Mean Group Improvement'}</th><th>${zh ? '原始 p' : 'Raw p'}</th><th>${zh ? 'Holm 校正后 p' : 'Holm-adjusted p'}</th><th>Cohen's dz</th><th>${zh ? '结论' : 'Conclusion'}</th></tr>${withinRows}</table>
<h2>${zh ? '个人—小组配对变化图' : 'Paired Individual-to-Group Change Chart'}</h2><p class="note">${zh ? '图内文字统一为英文；点击图表可大幅放大，也可下载 SVG。' : 'All chart text is in English. Click to enlarge or download the SVG.'}</p>${chart}
<h2>${zh ? '按任务分层的改善值' : 'Improvement by Task'}</h2><table><tr><th>${zh ? '任务' : 'Task'}</th>${conditionHeaders}</tr>${taskRows}</table>
<h2>${zh ? '不同起点成员的改善' : 'Improvement by Initial Member Position'}</h2><table><tr><th>${zh ? '组内位置' : 'Initial Position'}</th>${conditionHeaders}</tr>${positionRows}</table>
<h2>${zh ? '个人独立分基线' : 'Individual Score Baseline'}</h2><table><tr><th>${zh ? '指标' : 'Metric'}</th>${conditionHeaders}</tr><tr><th>Individual IS</th>${baselineCells}</tr></table>
<h2>${zh ? 'AIS 一致性校验' : 'AIS Consistency Check'}</h2><p class="${report.ais_consistency.status}">${zh ? esc(report.ais_consistency.note) : `Checked ${report.ais_consistency.checked_groups} groups; maximum absolute difference ${formatNumber(report.ais_consistency.max_absolute_difference)}.`}</p>
<h2>${zh ? '平均改善值的条件检验' : 'Condition Test of Mean Improvement'}</h2><table><tr><th>${zh ? '方法' : 'Method'}</th><th>${zh ? '统计量' : 'Statistic'}</th><th>p</th><th>${zh ? '效应量' : 'Effect Size'}</th><th>${zh ? '状态' : 'Status'}</th></tr><tr><td>${zh ? '小组聚类、任务内分层置换检验' : 'Group-clustered, task-stratified permutation test'}</td><td>${esc(report.statistical_test.statistic_name)}=${formatNumber(report.statistical_test.statistic)}</td><td>${formatNumber(report.statistical_test.p_value)}</td><td>${esc(report.statistical_test.effect_size_name)}=${formatNumber(report.statistical_test.effect_size)}</td><td>${esc(report.statistical_test.status)}</td></tr></table>
<h2>${zh ? '条件两两比较' : 'Pairwise Condition Comparisons'}</h2><table><tr><th>${zh ? '条件 A' : 'Condition A'}</th><th>${zh ? '条件 B' : 'Condition B'}</th><th>${zh ? '平均改善差 (B−A)' : 'Mean Improvement Difference (B−A)'}</th><th>${zh ? '原始 p' : 'Raw p'}</th><th>${zh ? 'Holm 校正后 p' : 'Holm-adjusted p'}</th><th>${zh ? '显著' : 'Significant'}</th></tr>${pairRows}</table>
<h2>${zh ? '匿名配对明细' : 'Anonymous Paired Records'}</h2><table><tr><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '任务' : 'Task'}</th><th>${zh ? '小组' : 'Group'}</th><th>${zh ? '参与者编码' : 'Participant ID'}</th><th>Individual IS</th><th>Group GS</th><th>IS−GS</th><th>${zh ? '原组内位置' : 'Initial Position'}</th></tr>${details}</table>
${chartModalHtml(language)}${INTERACTIVE_CHART_SCRIPT}</body></html>`
}
