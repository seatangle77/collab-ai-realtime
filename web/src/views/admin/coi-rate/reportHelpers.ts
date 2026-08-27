import type {
  CoiRateAnalysisResult,
  CoiRateMetricSummary,
} from '../../../api/admin/coi-rate-analysis'
import type { CoiAnalysisCoderRole, MetricConditionStats } from '../../../api/admin/coi-analysis'
import type { AdminGroup } from '../../../types/admin'
import { coderRoleLabel, conditionLabel } from '../coi/reportHelpers'
import { STATIC_BOXPLOT_CSS, staticSessionBoxplotHtml } from '../coi/staticBoxplotHtml'

export type CoiRateReportLanguage = 'zh' | 'en'

const EN_CONDITIONS: Record<string, string> = {
  no_assistance: 'No Assistance',
  glasses: 'Smart Glasses',
  app_notification: 'App Notification',
}
const EN_METRICS: Record<string, string> = {
  total_rate: 'All four-phase codes per minute',
  te_rate: 'TE codes per minute',
  ex_rate: 'EX codes per minute',
  in_rate: 'IN codes per minute',
  re_rate: 'RE codes per minute',
  other_rate: 'OTHER codes per minute',
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

function niceMaximum(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const steps = [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9, 10]
  return (steps.find(step => normalized <= step) ?? 10) * magnitude
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
  const labels = Object.fromEntries(conditions.map(condition => [condition, conditionName(condition, language)]))
  const panels = [
    { key: 'total_rate', title: zh ? '全部四阶段观点' : 'All four-phase codes', subtitle: zh ? 'TE＋EX＋IN＋RE编码次数／会话分钟数' : 'TE + EX + IN + RE assignments per session minute', wide: true },
    { key: 'te_rate', title: zh ? 'TE · 触发事件' : 'TE · Triggering Event', subtitle: zh ? '每分钟触发事件编码数' : 'Triggering Event codes per minute', wide: false },
    { key: 'ex_rate', title: zh ? 'EX · 探索' : 'EX · Exploration', subtitle: zh ? '每分钟探索编码数' : 'Exploration codes per minute', wide: false },
    { key: 'in_rate', title: zh ? 'IN · 整合' : 'IN · Integration', subtitle: zh ? '每分钟整合编码数' : 'Integration codes per minute', wide: false },
    { key: 're_rate', title: zh ? 'RE · 解决' : 'RE · Resolution', subtitle: zh ? '每分钟解决编码数' : 'Resolution codes per minute', wide: false },
  ] as const
  const totalMaximum = niceMaximum(Math.max(...report.observations.map(item => item.total_rate), 0) * 1.08)
  const phaseMaximum = niceMaximum(Math.max(...report.observations.flatMap(item => [item.te_rate, item.ex_rate, item.in_rate, item.re_rate]), 0) * 1.08)
  const barColors: Record<string, string> = { no_assistance: '#374151', glasses: '#1d4ed8', app_notification: '#c2410c' }
  const meanPanels = panels.map(panel => ({
    ...panel,
    values: conditions.map(condition => ({
      condition,
      value: report.metrics.find(metric => metric.metric === panel.key)?.conditions.find(item => item.condition === condition)?.mean ?? 0,
    })),
  }))
  const totalMeanMaximum = Math.max(...(meanPanels[0]?.values.map(item => item.value) ?? []), 1) * 1.08
  const phaseMeanMaximum = Math.max(...meanPanels.slice(1).flatMap(panel => panel.values.map(item => item.value)), 0.1) * 1.08
  const meanBarPanels = meanPanels.map((panel, index) => `<section class="mean-panel${panel.wide ? ' wide' : ''}"><h3>${escapeHtml(panel.title)}</h3>${panel.values.map(item => `<div class="mean-row"><span>${escapeHtml(conditionName(item.condition, language))}</span><div class="mean-track"><i style="width:${Math.min(100, item.value / (index === 0 ? totalMeanMaximum : phaseMeanMaximum) * 100)}%;background:${barColors[item.condition] ?? '#374151'}"></i></div><strong>${number(item.value)}${index === 0 ? '/min' : ''}</strong></div>`).join('')}</section>`).join('')
  const rateFigures = panels.map(panel => staticSessionBoxplotHtml({
    title: panel.title,
    subtitle: panel.subtitle,
    conditions,
    valuesByCondition: Object.fromEntries(conditions.map(condition => [condition, report.observations.filter(item => item.condition === condition).map(item => item[panel.key])])),
    conditionLabels: labels,
    maximum: panel.key === 'total_rate' ? totalMaximum : phaseMaximum,
    unitLabel: zh ? '编码次数／分钟' : 'Codes per minute',
    language,
    wide: panel.wide,
  })).join('')
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
  const observations = report.observations.map(item => `
    <tr><td>${escapeHtml(item.group_name ?? item.group_id)}</td><td>${escapeHtml(item.session_id)}</td><td>${escapeHtml(conditionName(item.condition, language))}</td><td>${dateTime(item.started_at, language)}</td><td>${dateTime(item.ended_at, language)}</td><td>${number(item.duration_minutes, 2)}</td><td>${item.phase_code_count}</td><td>${item.te_count}</td><td>${item.ex_count}</td><td>${item.in_count}</td><td>${item.re_count}</td><td>${number(item.total_rate)}</td><td>${number(item.te_rate)}</td><td>${number(item.ex_rate)}</td><td>${number(item.in_rate)}</td><td>${number(item.re_rate)}</td><td>${item.other_count}</td></tr>
  `).join('')
  const exclusions = report.excluded_sessions.length
    ? report.excluded_sessions.map(item => `<tr><td>${escapeHtml(item.group_name ?? item.group_id)}</td><td>${escapeHtml(item.session_id)}</td><td>${escapeHtml(conditionName(item.condition, language))}</td><td>${escapeHtml(zh ? item.note : (EN_EXCLUSION_REASONS[item.reason] ?? item.reason))}</td></tr>`).join('')
    : `<tr><td colspan="4">${zh ? '没有会话因时间或编码问题被排除。' : 'No sessions were excluded because of timing or coding problems.'}</td></tr>`

  return `<!doctype html>
<html lang="${zh ? 'zh-CN' : 'en'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>
<style>
body{margin:0;background:#f4f6f9;color:#253247;font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1180px;margin:28px auto;padding:30px 36px;background:#fff;box-shadow:0 8px 30px #26364b15}h1{margin:0 0 4px;font-size:25px}h2{margin:30px 0 10px;padding-bottom:7px;border-bottom:2px solid #e7edf4;font-size:17px}.meta,.note{color:#68778c}.note{padding:12px 14px;background:#f6f9fc;border-left:3px solid #3b82f6}table{width:100%;border-collapse:collapse;margin:10px 0 18px;font-size:12px}th,td{padding:7px 8px;border:1px solid #dce3eb;text-align:left;vertical-align:top}thead th{background:#eef3f8}.method{padding:16px;border:1px solid #dce7e1;background:#f7fbf8}.figure{margin:14px 0 22px;padding:18px 20px;border:1px solid #dfe6ee;border-radius:8px}.caption{margin-top:12px;padding-top:9px;border-top:1px solid #e8edf3;color:#64748b;font-size:11px}.nowrap{white-space:nowrap}.p-raw-nominal{display:inline-block;padding:1px 5px;border:1px solid #fed7aa;border-radius:4px;color:#b45309;background:#fff7ed;font-weight:700}.p-adjusted-significant{display:inline-block;padding:1px 5px;border:1px solid #fecaca;border-radius:4px;color:#b91c1c;background:#fef2f2}.p-status{display:block;margin-top:2px;color:#b45309;font-size:9px}.mean-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 28px}.mean-panel.wide{grid-column:1/-1;padding-bottom:14px;border-bottom:1px solid #e1e7ee}.mean-panel h3{margin:0 0 8px;font-size:13px}.mean-row{display:grid;grid-template-columns:110px minmax(0,1fr) 72px;align-items:center;gap:9px;min-height:28px;font-size:10px}.mean-track{height:13px;background:#f0f3f7}.mean-track i{display:block;height:13px;border-radius:2px}.mean-row strong{font-variant-numeric:tabular-nums}${STATIC_BOXPLOT_CSS}@media(max-width:760px){.mean-grid{grid-template-columns:1fr}.mean-panel.wide{grid-column:auto}}@media print{body{background:white}main{max-width:none;margin:0;box-shadow:none}table{page-break-inside:auto}tr,.figure{page-break-inside:avoid}}
</style></head><body><main>
<h1>${title}</h1><div class="meta">${zh ? '生成时间' : 'Generated'}：${generatedAt}；${zh ? '编码来源' : 'Coding source'}：${escapeHtml(zh ? coderRoleLabel(coderRole) : coderRole)}；${zh ? '时长来源' : 'Duration source'}：${escapeHtml(report.duration_source)}</div>
<p class="note">${zh ? '本报告衡量每场会话每分钟产生的CoI编码数量，不计算任何单条观点的持续时间。会话时长只使用系统保存的started_at与ended_at；缺少有效起止时间或编码不完整的会话整体排除。' : 'This report measures the number of CoI codes generated per session minute. It does not estimate the duration of individual ideas. Session exposure uses only persisted started_at and ended_at values; sessions with invalid timing or incomplete coding are excluded in full.'}</p>
<h2>1. ${zh ? '样本范围' : 'Sample'}</h2><table><thead><tr><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '选中群组' : 'Selected groups'}</th><th>${zh ? '群组名称' : 'Group names'}</th><th>${zh ? '纳入会话' : 'Included sessions'}</th></tr></thead><tbody>${conditionRows}</tbody></table>
<h2>2. ${zh ? '分析方法' : 'Method'}</h2><div class="method">${zh ? '每场会话作为一个独立观测值。全部四阶段观点产生率=(TE+EX+IN+RE编码次数)/会话分钟数；各阶段产生率=该阶段编码次数/会话分钟数。条件总体差异使用4,999次标签置换检验，五个主指标（总产生率及四阶段产生率）使用Benjamini–Hochberg方法控制错误发现率。相对无辅助条件的均值差使用4,999次会话级Bootstrap计算95%置信区间。OTHER仅作补充描述，不进入五项主检验。' : 'Each session is one independent observation. The total four-phase rate equals (TE+EX+IN+RE code assignments) divided by session minutes; phase rates use the corresponding phase count. Omnibus condition differences use 4,999 label permutations. Benjamini–Hochberg correction is applied across the five primary outcomes. Mean differences from No Assistance use 4,999 session-level bootstrap samples for 95% confidence intervals. OTHER is descriptive and is not included in the primary test family.'}</div>
<h2>3. ${zh ? '会话时长检查（分钟）' : 'Session duration check (minutes)'}</h2><table><thead><tr><th>${zh ? '条件' : 'Condition'}</th><th>n</th><th>M</th><th>SD</th><th>Median</th><th>Min</th><th>Max</th></tr></thead><tbody>${durationRows}</tbody></table>
<h2>4. ${zh ? '产生率可视化' : 'Rate visualizations'}</h2><div class="figure"><div class="mean-grid">${meanBarPanels}</div><div class="caption">${zh ? '图1　三种实验条件的平均CoI观点产生率。条形图用于快速比较条件均值。' : 'Figure 1. Mean CoI idea-generation rates across the three conditions. Bars provide a direct descriptive comparison of condition means.'}</div></div><div class="figure"><div class="boxplot-grid">${rateFigures}</div><div class="caption">${zh ? '图2　三种实验条件下CoI观点产生率的会话级分布。箱体表示中位数和四分位区间，须线为1.5倍四分位距范围，小型实心圆点为每场会话，菱形与误差线表示均值及95%置信区间。' : 'Figure 2. Session-level CoI rate distributions across the three conditions. Boxes show medians and interquartile ranges, whiskers extend to 1.5 IQR, small solid circles show sessions, and diamonds with error bars show means and 95% confidence intervals.'}</div></div>
<h2>5. ${zh ? '产生率描述性统计（每分钟）' : 'Descriptive rates (per minute)'}</h2><table><thead><tr><th rowspan="2">${zh ? '指标' : 'Outcome'}</th>${metricHead}</tr><tr>${metricSubhead}</tr></thead><tbody>${metricRows}</tbody></table>
<h2>6. ${zh ? '条件总体置换检验' : 'Omnibus permutation tests'}</h2><p class="note">${zh ? '颜色说明：橙色表示原始 p < 0.05；红色表示 BH 校正后 p < 0.05。' : 'Color key: orange indicates an unadjusted p < .05; red indicates a BH-adjusted p < .05.'}</p><table><thead><tr><th>${zh ? '指标' : 'Outcome'}</th><th>${zh ? '方法' : 'Method'}</th><th>${zh ? '统计量' : 'Statistic'}</th><th>${zh ? '原始 p' : 'Unadjusted p'}</th><th>${zh ? 'BH 校正后 p' : 'BH-adjusted p'}</th><th>η²</th><th>${zh ? '说明' : 'Note'}</th></tr></thead><tbody>${tests}</tbody></table>
<h2>7. ${zh ? '相对无辅助条件的差异' : 'Differences from No Assistance'}</h2><table><thead><tr><th>${zh ? '指标' : 'Outcome'}</th><th>${zh ? '比较条件' : 'Comparison'}</th><th>${zh ? '无辅助均值' : 'Reference mean'}</th><th>${zh ? '比较组均值' : 'Comparison mean'}</th><th>${zh ? '均值差' : 'Mean difference'}</th><th>${zh ? '产生率比' : 'Rate ratio'}</th><th>95% CI</th></tr></thead><tbody>${contrasts}</tbody></table>
<h2>8. ${zh ? '会话级分析数据' : 'Session-level analysis data'}</h2><table><thead><tr><th>${zh ? '群组' : 'Group'}</th><th>${zh ? '会话' : 'Session'}</th><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '开始' : 'Started'}</th><th>${zh ? '结束' : 'Ended'}</th><th>${zh ? '分钟' : 'Minutes'}</th><th>${zh ? '四阶段编码' : 'Four-phase codes'}</th><th>TE</th><th>EX</th><th>IN</th><th>RE</th><th>Total/min</th><th>TE/min</th><th>EX/min</th><th>IN/min</th><th>RE/min</th><th>OTHER</th></tr></thead><tbody>${observations}</tbody></table>
<h2>9. ${zh ? `被排除会话（${report.excluded_sessions.length}）` : `Excluded sessions (${report.excluded_sessions.length})`}</h2><table><thead><tr><th>${zh ? '群组' : 'Group'}</th><th>${zh ? '会话' : 'Session'}</th><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '原因' : 'Reason'}</th></tr></thead><tbody>${exclusions}</tbody></table>
</main></body></html>`
}
