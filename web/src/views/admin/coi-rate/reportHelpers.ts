import type {
  CoiRateAnalysisResult,
  CoiRateMetricSummary,
} from '../../../api/admin/coi-rate-analysis'
import type { CoiAnalysisCoderRole, MetricConditionStats } from '../../../api/admin/coi-analysis'
import type { AdminGroup } from '../../../types/admin'
import { coderRoleLabel, conditionLabel } from '../coi/reportHelpers'
import { STATIC_BOXPLOT_CSS, staticSessionBoxplotHtml } from '../coi/staticBoxplotHtml'
import { chartModalHtml, INTERACTIVE_CHART_CSS, INTERACTIVE_CHART_SCRIPT } from '../task-score/analysisExport'
import { academicConditionColor, academicNiceMaximum, academicNumber, academicPValue, academicTicks } from '../task-score/academicChartStyle'

export type CoiRateReportLanguage = 'zh' | 'en'

const EN_CONDITIONS: Record<string, string> = {
  no_assistance: 'No Assistance',
  glasses: 'Smart Glasses',
  app_notification: 'App Notification',
}
const EN_METRICS: Record<string, string> = {
  total_rate: 'All four-phase rate (codes/min)',
  te_rate: 'TE rate (codes/min)',
  ex_rate: 'EX rate (codes/min)',
  in_rate: 'IN rate (codes/min)',
  re_rate: 'RE rate (codes/min)',
  other_rate: 'OTHER rate (codes/min)',
}
const EN_EXCLUSION_REASONS: Record<string, string> = {
  incomplete_coding: 'The session contains units without the selected coding source.',
  missing_start_time: 'The session has no persisted started_at value.',
  missing_end_time: 'The session has no persisted ended_at value.',
  invalid_duration: 'The session end time is not later than its start time.',
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function number(value: number | null | undefined, digits = 3): string {
  return value == null || !Number.isFinite(value) ? '—' : value.toFixed(digits)
}

function dateTime(value: string, language: CoiRateReportLanguage): string {
  return new Intl.DateTimeFormat(language === 'zh' ? 'zh-CN' : 'en-GB', {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(new Date(value))
}

function conditionName(condition: string, language: CoiRateReportLanguage): string {
  return language === 'zh' ? conditionLabel(condition) : (EN_CONDITIONS[condition] ?? condition)
}

function metricName(metric: CoiRateMetricSummary, language: CoiRateReportLanguage): string {
  return language === 'zh' ? metric.label : (EN_METRICS[metric.metric] ?? metric.metric)
}

function statsFor(metric: CoiRateMetricSummary, condition: string): MetricConditionStats | undefined {
  return metric.conditions.find(item => item.condition === condition)
}

function selectedGroupNames(
  condition: string,
  selected: Record<string, string[]>,
  options: Record<string, AdminGroup[]>,
): string {
  const selectedIds = new Set(selected[condition] ?? [])
  return (options[condition] ?? []).filter(group => selectedIds.has(group.id)).map(group => group.name).join(', ')
}

export function buildCoiRateReportHtml(
  report: CoiRateAnalysisResult,
  coderRole: CoiAnalysisCoderRole,
  conditions: string[],
  selected: Record<string, string[]>,
  options: Record<string, AdminGroup[]>,
  language: CoiRateReportLanguage,
): string {
  const zh = language === 'zh'
  const title = zh ? 'CoI 观点产生率分析报告' : 'CoI Idea-Generation Rate Analysis Report'
  const generatedAt = new Intl.DateTimeFormat(zh ? 'zh-CN' : 'en-GB', { dateStyle: 'long', timeStyle: 'medium' }).format(new Date())
  const conditionRows = conditions.map(condition => `
    <tr><th>${escapeHtml(conditionName(condition, language))}</th><td>${selected[condition]?.length ?? 0}</td><td>${escapeHtml(selectedGroupNames(condition, selected, options))}</td><td>${report.sessions_by_condition[condition] ?? 0}</td></tr>
  `).join('')
  const durationRows = report.duration_stats.map(item => `
    <tr><th>${escapeHtml(conditionName(item.condition, language))}</th><td>${item.n}</td><td>${number(item.mean, 2)}</td><td>${number(item.sd, 2)}</td><td>${number(item.median, 2)}</td><td>${number(item.min, 2)}</td><td>${number(item.max, 2)}</td></tr>
  `).join('')
  const metricRows = report.metrics.map(metric => `
    <tr><th>${escapeHtml(metricName(metric, language))}</th>${conditions.map(condition => {
      const stats = statsFor(metric, condition)
      return `<td>${number(stats?.mean)}</td><td>${number(stats?.sd)}</td><td>${number(stats?.median)}</td>`
    }).join('')}</tr>
  `).join('')
  const metricHead = conditions.map(condition => `<th colspan="3">${escapeHtml(conditionName(condition, language))}</th>`).join('')
  const metricSubhead = conditions.map(() => `<th>M</th><th>SD</th><th>Median</th>`).join('')
  const labels = Object.fromEntries(conditions.map(condition => [condition, EN_CONDITIONS[condition] ?? condition]))
  const panels = [
    { key: 'total_rate', title: 'All Four CoI Phases', subtitle: 'TE + EX + IN + RE rate (codes/min)', wide: true },
    { key: 'te_rate', title: 'TE · Triggering Event', subtitle: 'Rate (codes/min)', wide: false },
    { key: 'ex_rate', title: 'EX · Exploration', subtitle: 'Rate (codes/min)', wide: false },
    { key: 'in_rate', title: 'IN · Integration', subtitle: 'Rate (codes/min)', wide: false },
    { key: 're_rate', title: 'RE · Resolution', subtitle: 'Rate (codes/min)', wide: false },
  ] as const
  const meanPanels = panels.map((panel, panelIndex) => ({
    ...panel,
    panelLabel: `(${String.fromCharCode(97 + panelIndex)})`,
    values: conditions.map(condition => ({
      condition,
      value: report.metrics.find(metric => metric.metric === panel.key)?.conditions.find(item => item.condition === condition)?.mean ?? 0,
      n: report.metrics.find(metric => metric.metric === panel.key)?.conditions.find(item => item.condition === condition)?.n ?? 0,
    })),
  }))
  const totalMeanMaximum = academicNiceMaximum(Math.max(...(meanPanels[0]?.values.map(item => item.value) ?? []), 1) * 1.03)
  const phaseMeanMaximum = academicNiceMaximum(Math.max(...meanPanels.slice(1).flatMap(panel => panel.values.map(item => item.value)), 0.1) * 1.03)
  const testLabel = (metric: string) => {
    const test = report.statistical_tests.find(item => item.metric === metric)
    return test ? `BH-adjusted ${academicPValue(test.p_value_adjusted)} · η² = ${academicNumber(test.effect_size, 2)}` : ''
  }
  const totalAxis = academicTicks(totalMeanMaximum).map(tick => `<line x1="${225 + tick / totalMeanMaximum * 800}" x2="${225 + tick / totalMeanMaximum * 800}" y1="48" y2="205" class="grid-line"/><text x="${225 + tick / totalMeanMaximum * 800}" y="225" text-anchor="middle">${tick.toFixed(2)}</text>`).join('')
  const meanTotalRows = meanPanels[0]!.values.map((item, index) => `<text x="205" y="${76 + index * 48}" text-anchor="end" class="condition">${escapeHtml(EN_CONDITIONS[item.condition] ?? item.condition)}</text><rect x="225" y="${57 + index * 48}" width="${Math.max(0, Math.min(800, item.value / totalMeanMaximum * 800))}" height="24" fill="${academicConditionColor(item.condition)}"/><text x="${Math.min(1100, 235 + item.value / totalMeanMaximum * 800)}" y="${76 + index * 48}" class="value">${number(item.value)} (n=${item.n})</text>`).join('')
  const meanPhasePanels = meanPanels.slice(1).map((panel, panelIndex) => {
    const left = 24 + (panelIndex % 2) * 590
    const top = 286 + Math.floor(panelIndex / 2) * 244
    const phaseAxis = academicTicks(phaseMeanMaximum).map(tick => `<line x1="${left + 165 + tick / phaseMeanMaximum * 340}" x2="${left + 165 + tick / phaseMeanMaximum * 340}" y1="${top + 18}" y2="${top + 172}" class="grid-line"/><text x="${left + 165 + tick / phaseMeanMaximum * 340}" y="${top + 191}" text-anchor="middle">${tick.toFixed(2)}</text>`).join('')
    const rows = panel.values.map((item, index) => `<text x="${left + 145}" y="${top + 44 + index * 46}" text-anchor="end" class="condition">${escapeHtml(EN_CONDITIONS[item.condition] ?? item.condition)}</text><rect x="${left + 165}" y="${top + 26 + index * 46}" width="${Math.max(0, Math.min(340, item.value / phaseMeanMaximum * 340))}" height="23" fill="${academicConditionColor(item.condition)}"/><text x="${left + 515}" y="${top + 44 + index * 46}" class="value">${number(item.value)}</text>`).join('')
    return `<text x="${left}" y="${top}" class="chart-title">${panel.panelLabel} ${escapeHtml(panel.title.replace(' · ', ' '))}</text><text x="${left + 550}" y="${top}" text-anchor="end" class="stat-label">${escapeHtml(testLabel(panel.key))}</text>${phaseAxis}<line x1="${left + 165}" x2="${left + 505}" y1="${top + 172}" y2="${top + 172}" class="axis-line"/>${rows}<text x="${left + 335}" y="${top + 216}" text-anchor="middle" class="axis-title">Rate (codes/min)</text>`
  }).join('')
  const meanRateSvg = `<svg class="mean-rate-svg" viewBox="0 0 1200 790" role="img" aria-label="Mean CoI idea-generation rates by condition"><defs><style>text{font-family:Arial,Helvetica,sans-serif;text-rendering:geometricPrecision}.chart-title{fill:#0f172a;font-size:18px;font-weight:800}.condition{fill:#1e293b;font-size:14px;font-weight:700}.value{fill:#1e293b;font-size:13px;font-weight:750}.stat-label{fill:#334155;font-size:11px;font-weight:700}.grid-line{stroke:#dfe6ee;stroke-width:1;stroke-dasharray:3 3}.axis-line{stroke:#64748b;stroke-width:1.5}.axis-title{fill:#1e293b;font-size:14px;font-weight:750}.numeric-axis text{fill:#475569;font-size:12px;font-weight:650}</style></defs><text x="24" y="30" class="chart-title">(a) All Four CoI Phases</text><text x="1170" y="30" text-anchor="end" class="stat-label">${escapeHtml(testLabel('total_rate'))}</text><g class="numeric-axis">${totalAxis}<line x1="225" x2="1025" y1="205" y2="205" class="axis-line"/><text x="625" y="250" text-anchor="middle" class="axis-title">Rate (codes/min)</text></g>${meanTotalRows}<line x1="24" x2="1176" y1="270" y2="270" stroke="#cbd5e1" stroke-width="1.5"/>${meanPhasePanels}</svg>`
  const rateFigures = panels.map((panel, panelIndex) => {
    const test = report.statistical_tests.find(item => item.metric === panel.key)
    const valuesByCondition = Object.fromEntries(conditions.map(condition => [condition, report.observations.filter(item => item.condition === condition).map(item => item[panel.key])]))
    const maximum = academicNiceMaximum(Math.max(...Object.values(valuesByCondition).flat(), 0) * 1.03)
    return staticSessionBoxplotHtml({
    title: panel.title,
    subtitle: panel.subtitle,
    conditions,
    valuesByCondition,
    conditionLabels: labels,
    maximum,
    unitLabel: 'Rate (codes/min)',
    language: 'en',
    wide: panel.wide,
    panelLabel: `(${String.fromCharCode(97 + panelIndex)})`,
    statisticLabel: test ? `BH-adjusted ${academicPValue(test.p_value_adjusted)} · η² = ${academicNumber(test.effect_size, 2)}` : '',
  })}).join('')
  const tests = report.statistical_tests.map(test => {
    const rawNominal = test.p_value != null && test.p_value < 0.05
    const adjustedSignificant = test.p_value_adjusted != null && test.p_value_adjusted < 0.05
    const rawStatus = rawNominal && !adjustedSignificant
      ? `<small class="p-status">${zh ? '未经 BH 校正' : 'Unadjusted'}</small>`
      : ''
    return `
      <tr><th>${escapeHtml(zh ? test.label : (EN_METRICS[test.metric] ?? test.metric))}</th><td>${escapeHtml(test.method)}</td><td>${escapeHtml(test.statistic_name)}=${number(test.statistic)}</td><td><span class="${rawNominal ? 'p-raw-nominal' : ''}">${number(test.p_value, 4)}</span>${rawStatus}</td><td><strong class="${adjustedSignificant ? 'p-adjusted-significant' : ''}">${number(test.p_value_adjusted, 4)}</strong></td><td>${number(test.effect_size, 4)}</td><td>${escapeHtml(zh ? test.note : 'Each session was one observation. Code counts were divided by persisted session minutes, and condition labels were permuted 4,999 times.')}</td></tr>
    `
  }).join('')
  const contrasts = report.contrasts.map(item => `
    <tr><th>${escapeHtml(zh ? item.label : (EN_METRICS[item.metric] ?? item.metric))}</th><td>${escapeHtml(conditionName(item.comparison_condition, language))}</td><td>${number(item.reference_mean)}</td><td>${number(item.comparison_mean)}</td><td>${item.mean_difference > 0 ? '+' : ''}${number(item.mean_difference)}</td><td>${number(item.rate_ratio)}</td><td>[${number(item.ci_low)}, ${number(item.ci_high)}]</td></tr>
  `).join('')
  const forestItems = report.contrasts
  const contrastMaximum = Math.max(0.1, Math.ceil(Math.max(...forestItems.flatMap(item => [item.mean_difference, item.ci_low ?? 0, item.ci_high ?? 0].map(Math.abs)), 0.1) * 10) / 10)
  const contrastX = (value: number) => 390 + Math.min(1, Math.max(0, (value + contrastMaximum) / (contrastMaximum * 2))) * 500
  const forestHeight = 126 + forestItems.length * 64
  const forestRows = forestItems.map((item, index) => {
    const y = 78 + index * 64
    const color = academicConditionColor(item.comparison_condition)
    const metric = EN_METRICS[item.metric]?.replace(' codes per minute', '') ?? item.metric
    const interval = item.ci_low != null && item.ci_high != null
      ? `<line x1="${contrastX(item.ci_low)}" x2="${contrastX(item.ci_high)}" y1="${y}" y2="${y}" stroke="${color}" stroke-width="4"/><line x1="${contrastX(item.ci_low)}" x2="${contrastX(item.ci_low)}" y1="${y - 8}" y2="${y + 8}" stroke="${color}" stroke-width="3"/><line x1="${contrastX(item.ci_high)}" x2="${contrastX(item.ci_high)}" y1="${y - 8}" y2="${y + 8}" stroke="${color}" stroke-width="3"/>`
      : ''
    return `<line x1="25" x2="1175" y1="${50 + index * 64}" y2="${50 + index * 64}" stroke="#e2e8f0"/><text x="350" y="${y - 5}" text-anchor="end" class="metric">${escapeHtml(metric)}</text><text x="350" y="${y + 13}" text-anchor="end" class="comparison">${escapeHtml(EN_CONDITIONS[item.comparison_condition] ?? item.comparison_condition)} − No Assistance · ${escapeHtml(testLabel(item.metric))}</text>${interval}<rect x="${contrastX(item.mean_difference) - 6}" y="${y - 6}" width="12" height="12" fill="${color}"/><text x="925" y="${y + 5}" class="effect">${item.mean_difference > 0 ? '+' : ''}${number(item.mean_difference, 2)} [${number(item.ci_low, 2)}, ${number(item.ci_high, 2)}]</text>`
  }).join('')
  const forestTicks = Array.from({ length: 5 }, (_, index) => -contrastMaximum + contrastMaximum * 2 * index / 4).map(tick => `<line x1="${contrastX(tick)}" x2="${contrastX(tick)}" y1="34" y2="${forestHeight - 58}" class="${Math.abs(tick) < 1e-10 ? 'zero' : 'grid'}"/><text x="${contrastX(tick)}" y="${forestHeight - 35}" text-anchor="middle" class="tick">${tick > 0 ? '+' : ''}${tick.toFixed(2)}</text>`).join('')
  const forestSvg = `<svg viewBox="0 0 1200 ${forestHeight}" role="img" aria-label="Rate differences relative to No Assistance"><defs><style>text{font-family:Arial,Helvetica,sans-serif;text-rendering:geometricPrecision}.metric{fill:#0f172a;font-size:15px;font-weight:750}.comparison{fill:#526071;font-size:11px;font-weight:600}.effect{fill:#1e293b;font-size:14px;font-weight:700}.tick{fill:#526071;font-size:12px;font-weight:650}.grid{stroke:#dfe6ee;stroke-width:1;stroke-dasharray:3 3}.zero{stroke:#334155;stroke-width:2}.axis{stroke:#64748b;stroke-width:1.5}.axis-title{fill:#1e293b;font-size:14px;font-weight:750}</style></defs>${forestTicks}<line x1="390" x2="890" y1="${forestHeight - 58}" y2="${forestHeight - 58}" class="axis"/>${forestRows}<text x="640" y="${forestHeight - 8}" text-anchor="middle" class="axis-title">Mean Difference in Rate (codes/min)</text></svg>`
  const observations = report.observations.map(item => `
    <tr><td>${escapeHtml(item.group_name ?? item.group_id)}</td><td>${escapeHtml(item.session_id)}</td><td>${escapeHtml(conditionName(item.condition, language))}</td><td>${dateTime(item.started_at, language)}</td><td>${dateTime(item.ended_at, language)}</td><td>${number(item.duration_minutes, 2)}</td><td>${item.phase_code_count}</td><td>${item.te_count}</td><td>${item.ex_count}</td><td>${item.in_count}</td><td>${item.re_count}</td><td>${number(item.total_rate)}</td><td>${number(item.te_rate)}</td><td>${number(item.ex_rate)}</td><td>${number(item.in_rate)}</td><td>${number(item.re_rate)}</td><td>${item.other_count}</td></tr>
  `).join('')
  const exclusions = report.excluded_sessions.length
    ? report.excluded_sessions.map(item => `<tr><td>${escapeHtml(item.group_name ?? item.group_id)}</td><td>${escapeHtml(item.session_id)}</td><td>${escapeHtml(conditionName(item.condition, language))}</td><td>${escapeHtml(zh ? item.note : (EN_EXCLUSION_REASONS[item.reason] ?? item.reason))}</td></tr>`).join('')
    : `<tr><td colspan="4">${zh ? '没有会话因时间或编码问题被排除。' : 'No sessions were excluded because of timing or coding problems.'}</td></tr>`

  return `<!doctype html>
<html lang="${zh ? 'zh-CN' : 'en'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>
<style>
body{margin:0;background:#f4f6f9;color:#253247;font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1180px;margin:28px auto;padding:30px 36px;background:#fff;box-shadow:0 8px 30px #26364b15}h1{margin:0 0 4px;font-size:25px}h2{margin:30px 0 10px;padding-bottom:7px;border-bottom:2px solid #e7edf4;font-size:17px}.meta,.note{color:#68778c}.note{padding:12px 14px;background:#f6f9fc;border-left:3px solid #3b82f6}table{width:100%;border-collapse:collapse;margin:10px 0 18px;font-size:12px}th,td{padding:7px 8px;border:1px solid #dce3eb;text-align:left;vertical-align:top}thead th{background:#eef3f8}.method{padding:16px;border:1px solid #dce7e1;background:#f7fbf8}.figure{margin:14px 0 22px;padding:18px 20px;border:1px solid #dfe6ee;border-radius:8px}.caption{margin-top:12px;padding-top:9px;border-top:1px solid #e8edf3;color:#64748b;font-size:11px}.nowrap{white-space:nowrap}.p-raw-nominal{display:inline-block;padding:1px 5px;border:1px solid #fed7aa;border-radius:4px;color:#b45309;background:#fff7ed;font-weight:700}.p-adjusted-significant{display:inline-block;padding:1px 5px;border:1px solid #fecaca;border-radius:4px;color:#b91c1c;background:#fef2f2}.p-status{display:block;margin-top:2px;color:#b45309;font-size:9px}.mean-rate-svg{display:block;width:100%;height:auto}${STATIC_BOXPLOT_CSS}${INTERACTIVE_CHART_CSS}@media print{body{background:white}main{max-width:none;margin:0;box-shadow:none}table{page-break-inside:auto}tr,.figure{page-break-inside:avoid}}
</style></head><body><main>
<h1>${title}</h1><div class="meta">${zh ? '生成时间' : 'Generated'}：${generatedAt}；${zh ? '编码来源' : 'Coding source'}：${escapeHtml(zh ? coderRoleLabel(coderRole) : coderRole)}；${zh ? '时长来源' : 'Duration source'}：${escapeHtml(report.duration_source)}</div>
<p class="note">${zh ? '本报告衡量每场会话每分钟产生的CoI编码数量，不计算任何单条观点的持续时间。会话时长只使用系统保存的started_at与ended_at；缺少有效起止时间或编码不完整的会话整体排除。' : 'This report measures the number of CoI codes generated per session minute. It does not estimate the duration of individual ideas. Session exposure uses only persisted started_at and ended_at values; sessions with invalid timing or incomplete coding are excluded in full.'}</p>
<h2>1. ${zh ? '样本范围' : 'Sample'}</h2><table><thead><tr><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '选中群组' : 'Selected groups'}</th><th>${zh ? '群组名称' : 'Group names'}</th><th>${zh ? '纳入会话' : 'Included sessions'}</th></tr></thead><tbody>${conditionRows}</tbody></table>
<h2>2. ${zh ? '分析方法' : 'Method'}</h2><div class="method">${zh ? '每场会话作为一个独立观测值。全部四阶段观点产生率=(TE+EX+IN+RE编码次数)/会话分钟数；各阶段产生率=该阶段编码次数/会话分钟数。条件总体差异使用4,999次标签置换检验，五个主指标（总产生率及四阶段产生率）使用Benjamini–Hochberg方法控制错误发现率。相对无辅助条件的均值差使用4,999次会话级Bootstrap计算95%置信区间。OTHER仅作补充描述，不进入五项主检验。' : 'Each session is one independent observation. The total four-phase rate equals (TE+EX+IN+RE code assignments) divided by session minutes; phase rates use the corresponding phase count. Omnibus condition differences use 4,999 label permutations. Benjamini–Hochberg correction is applied across the five primary outcomes. Mean differences from No Assistance use 4,999 session-level bootstrap samples for 95% confidence intervals. OTHER is descriptive and is not included in the primary test family.'}</div>
<h2>3. ${zh ? '会话时长检查（分钟）' : 'Session duration check (minutes)'}</h2><table><thead><tr><th>${zh ? '条件' : 'Condition'}</th><th>n</th><th>M</th><th>SD</th><th>Median</th><th>Min</th><th>Max</th></tr></thead><tbody>${durationRows}</tbody></table>
<h2>4. ${zh ? '产生率可视化' : 'Rate visualizations'}</h2><div class="figure">${meanRateSvg}<div class="caption">${zh ? '图1　三种实验条件的平均CoI观点产生率。图内文字统一为英文。' : 'Figure 1. Mean CoI idea-generation rates across the three conditions.'}</div></div><div class="figure"><div class="boxplot-grid">${rateFigures}</div><div class="caption">${zh ? '图2　三种实验条件下CoI观点产生率的会话级分布。图内文字统一为英文。' : 'Figure 2. Session-level CoI rate distributions across the three conditions.'}</div></div>
<h2>5. ${zh ? '产生率描述性统计（每分钟）' : 'Descriptive rates (per minute)'}</h2><table><thead><tr><th rowspan="2">${zh ? '指标' : 'Outcome'}</th>${metricHead}</tr><tr>${metricSubhead}</tr></thead><tbody>${metricRows}</tbody></table>
<h2>6. ${zh ? '条件总体置换检验' : 'Omnibus permutation tests'}</h2><p class="note">${zh ? '颜色说明：橙色表示原始 p < 0.05；红色表示 BH 校正后 p < 0.05。' : 'Color key: orange indicates an unadjusted p < .05; red indicates a BH-adjusted p < .05.'}</p><table><thead><tr><th>${zh ? '指标' : 'Outcome'}</th><th>${zh ? '方法' : 'Method'}</th><th>${zh ? '统计量' : 'Statistic'}</th><th>${zh ? '原始 p' : 'Unadjusted p'}</th><th>${zh ? 'BH 校正后 p' : 'BH-adjusted p'}</th><th>η²</th><th>${zh ? '说明' : 'Note'}</th></tr></thead><tbody>${tests}</tbody></table>
<h2>7. ${zh ? '相对无辅助条件的差异' : 'Differences from No Assistance'}</h2><div class="figure">${forestSvg}<div class="caption">${zh ? '图3　智能眼镜与 APP 通知相对无辅助条件的总产生率及四阶段产生率均值差；菱形为均值差，横线为 Bootstrap 95% 置信区间。图内文字统一为英文。' : 'Figure 3. Total and phase-rate differences for Smart Glasses and App Notification relative to No Assistance. Diamonds show mean differences and horizontal lines show bootstrap 95% confidence intervals.'}</div></div><table><thead><tr><th>${zh ? '指标' : 'Outcome'}</th><th>${zh ? '比较条件' : 'Comparison'}</th><th>${zh ? '无辅助均值' : 'Reference mean'}</th><th>${zh ? '比较组均值' : 'Comparison mean'}</th><th>${zh ? '均值差' : 'Mean difference'}</th><th>${zh ? '产生率比' : 'Rate ratio'}</th><th>95% CI</th></tr></thead><tbody>${contrasts}</tbody></table>
<h2>8. ${zh ? '会话级分析数据' : 'Session-level analysis data'}</h2><table><thead><tr><th>${zh ? '群组' : 'Group'}</th><th>${zh ? '会话' : 'Session'}</th><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '开始' : 'Started'}</th><th>${zh ? '结束' : 'Ended'}</th><th>${zh ? '分钟' : 'Minutes'}</th><th>${zh ? '四阶段编码' : 'Four-phase codes'}</th><th>TE</th><th>EX</th><th>IN</th><th>RE</th><th>Total/min</th><th>TE/min</th><th>EX/min</th><th>IN/min</th><th>RE/min</th><th>OTHER</th></tr></thead><tbody>${observations}</tbody></table>
<h2>9. ${zh ? `被排除会话（${report.excluded_sessions.length}）` : `Excluded sessions (${report.excluded_sessions.length})`}</h2><table><thead><tr><th>${zh ? '群组' : 'Group'}</th><th>${zh ? '会话' : 'Session'}</th><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '原因' : 'Reason'}</th></tr></thead><tbody>${exclusions}</tbody></table>
${chartModalHtml(language)}${INTERACTIVE_CHART_SCRIPT}</main></body></html>`
}
