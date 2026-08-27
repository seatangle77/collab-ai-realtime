import type {
  CoiRateAnalysisResult,
  CoiRateMetricSummary,
} from '../../../api/admin/coi-rate-analysis'
import type { CoiAnalysisCoderRole, MetricConditionStats } from '../../../api/admin/coi-analysis'
import type { AdminGroup } from '../../../types/admin'
import { coderRoleLabel, conditionLabel } from '../coi/reportHelpers'

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
const CONDITION_COLORS: Record<string, string> = {
  no_assistance: '#64748b',
  glasses: '#3b82f6',
  app_notification: '#f97316',
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
  const primaryMetrics = report.metrics.filter(metric => metric.metric !== 'other_rate')
  const maximumMean = Math.max(...primaryMetrics.flatMap(metric => metric.conditions.map(item => item.mean ?? 0)), 1)
  const totalMetric = primaryMetrics.find(metric => metric.metric === 'total_rate')
  const phaseMetrics = primaryMetrics.filter(metric => metric.metric !== 'total_rate')
  const totalFigure = conditions.map(condition => {
    const value = statsFor(totalMetric!, condition)?.mean ?? 0
    return `<div class="bar-row"><span>${escapeHtml(conditionName(condition, language))}</span><div class="bar-track"><i style="width:${value / maximumMean * 100}%;background:${CONDITION_COLORS[condition] ?? '#64748b'}"></i></div><strong>${number(value)}/min</strong></div>`
  }).join('')
  const phaseFigure = phaseMetrics.map(metric => `<section class="phase-panel"><h3>${escapeHtml(metricName(metric, language))}</h3>${conditions.map(condition => {
    const value = statsFor(metric, condition)?.mean ?? 0
    return `<div class="bar-row"><span>${escapeHtml(conditionName(condition, language))}</span><div class="bar-track"><i style="width:${value / maximumMean * 100}%;background:${CONDITION_COLORS[condition] ?? '#64748b'}"></i></div><strong>${number(value)}</strong></div>`
  }).join('')}</section>`).join('')
  const tests = report.statistical_tests.map(test => `
    <tr><th>${escapeHtml(zh ? test.label : (EN_METRICS[test.metric] ?? test.metric))}</th><td>${escapeHtml(test.method)}</td><td>${escapeHtml(test.statistic_name)}=${number(test.statistic)}</td><td>${number(test.p_value, 4)}</td><td>${number(test.p_value_adjusted, 4)}</td><td>${number(test.effect_size, 4)}</td><td>${escapeHtml(zh ? test.note : 'Each session was one observation. Code counts were divided by persisted session minutes, and condition labels were permuted 4,999 times.')}</td></tr>
  `).join('')
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
body{margin:0;background:#f4f6f9;color:#253247;font:14px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1180px;margin:28px auto;padding:30px 36px;background:#fff;box-shadow:0 8px 30px #26364b15}h1{margin:0 0 4px;font-size:25px}h2{margin:30px 0 10px;padding-bottom:7px;border-bottom:2px solid #e7edf4;font-size:17px}.meta,.note{color:#68778c}.note{padding:12px 14px;background:#f6f9fc;border-left:3px solid #3b82f6}table{width:100%;border-collapse:collapse;margin:10px 0 18px;font-size:12px}th,td{padding:7px 8px;border:1px solid #dce3eb;text-align:left;vertical-align:top}thead th{background:#eef3f8}.method{padding:16px;border:1px solid #dce7e1;background:#f7fbf8}.figure{margin:14px 0 22px;padding:18px 20px;border:1px solid #dfe6ee;border-radius:8px}.figure h3{margin:0 0 8px;font-size:13px}.bar-row{display:grid;grid-template-columns:130px minmax(0,1fr) 76px;align-items:center;gap:10px;min-height:30px;font-size:11px}.bar-track{height:14px;background:repeating-linear-gradient(to right,#f5f7fa 0,#f5f7fa 24.7%,#e2e8f0 25%,#f5f7fa 25.3%)}.bar-track i{display:block;height:14px;border-radius:2px}.phase-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 28px}.caption{margin-top:12px;padding-top:9px;border-top:1px solid #e8edf3;color:#64748b;font-size:11px}.nowrap{white-space:nowrap}@media(max-width:760px){.phase-grid{grid-template-columns:1fr}}@media print{body{background:white}main{max-width:none;margin:0;box-shadow:none}table{page-break-inside:auto}tr,.figure{page-break-inside:avoid}}
</style></head><body><main>
<h1>${title}</h1><div class="meta">${zh ? '生成时间' : 'Generated'}：${generatedAt}；${zh ? '编码来源' : 'Coding source'}：${escapeHtml(zh ? coderRoleLabel(coderRole) : coderRole)}；${zh ? '时长来源' : 'Duration source'}：${escapeHtml(report.duration_source)}</div>
<p class="note">${zh ? '本报告衡量每场会话每分钟产生的CoI编码数量，不计算任何单条观点的持续时间。会话时长只使用系统保存的started_at与ended_at；缺少有效起止时间或编码不完整的会话整体排除。' : 'This report measures the number of CoI codes generated per session minute. It does not estimate the duration of individual ideas. Session exposure uses only persisted started_at and ended_at values; sessions with invalid timing or incomplete coding are excluded in full.'}</p>
<h2>1. ${zh ? '样本范围' : 'Sample'}</h2><table><thead><tr><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '选中群组' : 'Selected groups'}</th><th>${zh ? '群组名称' : 'Group names'}</th><th>${zh ? '纳入会话' : 'Included sessions'}</th></tr></thead><tbody>${conditionRows}</tbody></table>
<h2>2. ${zh ? '分析方法' : 'Method'}</h2><div class="method">${zh ? '每场会话作为一个独立观测值。全部四阶段观点产生率=(TE+EX+IN+RE编码次数)/会话分钟数；各阶段产生率=该阶段编码次数/会话分钟数。条件总体差异使用4,999次标签置换检验，五个主指标（总产生率及四阶段产生率）使用Benjamini–Hochberg方法控制错误发现率。相对无辅助条件的均值差使用4,999次会话级Bootstrap计算95%置信区间。OTHER仅作补充描述，不进入五项主检验。' : 'Each session is one independent observation. The total four-phase rate equals (TE+EX+IN+RE code assignments) divided by session minutes; phase rates use the corresponding phase count. Omnibus condition differences use 4,999 label permutations. Benjamini–Hochberg correction is applied across the five primary outcomes. Mean differences from No Assistance use 4,999 session-level bootstrap samples for 95% confidence intervals. OTHER is descriptive and is not included in the primary test family.'}</div>
<h2>3. ${zh ? '会话时长检查（分钟）' : 'Session duration check (minutes)'}</h2><table><thead><tr><th>${zh ? '条件' : 'Condition'}</th><th>n</th><th>M</th><th>SD</th><th>Median</th><th>Min</th><th>Max</th></tr></thead><tbody>${durationRows}</tbody></table>
<h2>4. ${zh ? '产生率可视化' : 'Rate visualizations'}</h2><div class="figure"><h3>${zh ? '全部四阶段观点产生率' : 'All four-phase codes per minute'}</h3>${totalFigure}<div class="caption">${zh ? '图1　各条件每场会话四阶段有效编码总数除以会话分钟数后的条件均值。' : 'Figure 1. Condition means for all four-phase code assignments per persisted session minute.'}</div></div><div class="figure"><div class="phase-grid">${phaseFigure}</div><div class="caption">${zh ? '图2　TE、EX、IN和RE的条件平均每分钟产生率；四个面板使用共同刻度。' : 'Figure 2. Mean TE, EX, IN, and RE rates by condition; all panels use a shared scale.'}</div></div>
<h2>5. ${zh ? '产生率描述性统计（每分钟）' : 'Descriptive rates (per minute)'}</h2><table><thead><tr><th rowspan="2">${zh ? '指标' : 'Outcome'}</th>${metricHead}</tr><tr>${metricSubhead}</tr></thead><tbody>${metricRows}</tbody></table>
<h2>6. ${zh ? '条件总体置换检验' : 'Omnibus permutation tests'}</h2><table><thead><tr><th>${zh ? '指标' : 'Outcome'}</th><th>${zh ? '方法' : 'Method'}</th><th>${zh ? '统计量' : 'Statistic'}</th><th>p</th><th>p_adj (BH)</th><th>η²</th><th>${zh ? '说明' : 'Note'}</th></tr></thead><tbody>${tests}</tbody></table>
<h2>7. ${zh ? '相对无辅助条件的差异' : 'Differences from No Assistance'}</h2><table><thead><tr><th>${zh ? '指标' : 'Outcome'}</th><th>${zh ? '比较条件' : 'Comparison'}</th><th>${zh ? '无辅助均值' : 'Reference mean'}</th><th>${zh ? '比较组均值' : 'Comparison mean'}</th><th>${zh ? '均值差' : 'Mean difference'}</th><th>${zh ? '产生率比' : 'Rate ratio'}</th><th>95% CI</th></tr></thead><tbody>${contrasts}</tbody></table>
<h2>8. ${zh ? '会话级分析数据' : 'Session-level analysis data'}</h2><table><thead><tr><th>${zh ? '群组' : 'Group'}</th><th>${zh ? '会话' : 'Session'}</th><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '开始' : 'Started'}</th><th>${zh ? '结束' : 'Ended'}</th><th>${zh ? '分钟' : 'Minutes'}</th><th>${zh ? '四阶段编码' : 'Four-phase codes'}</th><th>TE</th><th>EX</th><th>IN</th><th>RE</th><th>Total/min</th><th>TE/min</th><th>EX/min</th><th>IN/min</th><th>RE/min</th><th>OTHER</th></tr></thead><tbody>${observations}</tbody></table>
<h2>9. ${zh ? `被排除会话（${report.excluded_sessions.length}）` : `Excluded sessions (${report.excluded_sessions.length})`}</h2><table><thead><tr><th>${zh ? '群组' : 'Group'}</th><th>${zh ? '会话' : 'Session'}</th><th>${zh ? '条件' : 'Condition'}</th><th>${zh ? '原因' : 'Reason'}</th></tr></thead><tbody>${exclusions}</tbody></table>
</main></body></html>`
}
