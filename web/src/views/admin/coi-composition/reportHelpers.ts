import type { CoiCompositionAnalysisResult } from '../../../api/admin/coi-composition-analysis'
import type { CoiAnalysisCoderRole, PostHocResult, StatisticalTestResult } from '../../../api/admin/coi-analysis'
import type { AdminGroup } from '../../../types/admin'
import { formatNumber, pValueText } from '../coi/reportHelpers'
import { STATIC_BOXPLOT_CSS, staticSessionBoxplotHtml } from '../coi/staticBoxplotHtml'
import { chartModalHtml, INTERACTIVE_CHART_CSS, INTERACTIVE_CHART_SCRIPT } from '../task-score/analysisExport'
import { academicNumber, academicPValue } from '../task-score/academicChartStyle'

export type CoiCompositionReportLanguage = 'zh' | 'en'

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function percent(value: number | null | undefined): string {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function conditionLabel(condition: string, language: CoiCompositionReportLanguage): string {
  const labels: Record<string, [string, string]> = {
    no_assistance: ['无辅助', 'No assistance'],
    glasses: ['智能眼镜', 'Smart glasses'],
    app_notification: ['APP 通知', 'App notification'],
  }
  const pair = labels[condition]
  return pair ? pair[language === 'zh' ? 0 : 1] : condition
}

function coderRoleLabel(role: CoiAnalysisCoderRole, language: CoiCompositionReportLanguage): string {
  const labels: Record<CoiAnalysisCoderRole, [string, string]> = {
    final: ['最终协商编码', 'Final consensus coding'],
    coder_a: ['研究员 A 独立编码', 'Researcher A independent coding'],
    coder_b: ['研究员 B 独立编码', 'Researcher B independent coding'],
    coder_c: ['AI 编码员 C', 'AI-assisted coder C'],
  }
  return labels[role][language === 'zh' ? 0 : 1]
}

function metricLabel(metric: string, fallback: string, language: CoiCompositionReportLanguage): string {
  const labels: Record<string, [string, string]> = {
    te_ratio: ['TE：触发事件', 'TE: Triggering Event'],
    ex_ratio: ['EX：探索', 'EX: Exploration'],
    in_ratio: ['IN：整合', 'IN: Integration'],
    re_ratio: ['RE：解决', 'RE: Resolution'],
  }
  const pair = labels[metric]
  return pair ? pair[language === 'zh' ? 0 : 1] : fallback
}

function testLabel(test: StatisticalTestResult['test'], language: CoiCompositionReportLanguage): string {
  const labels: Record<StatisticalTestResult['test'], [string, string]> = {
    independent_samples_t_test: ['独立样本 t 检验', 'Independent-samples t-test'],
    mann_whitney_u: ['Mann–Whitney U 检验', 'Mann–Whitney U test'],
    one_way_anova: ['单因素方差分析', 'One-way ANOVA'],
    kruskal_wallis: ['Kruskal–Wallis 检验', 'Kruskal–Wallis test'],
    insufficient_data: ['样本不足', 'Insufficient data'],
  }
  return labels[test][language === 'zh' ? 0 : 1]
}

function postHocMethodLabel(method: PostHocResult['method']): string {
  if (method === 'tukey_hsd') return 'Tukey HSD'
  if (method === 'dunn_bonferroni') return 'Dunn + Bonferroni'
  return '—'
}

function selectedGroupNames(
  condition: string,
  selectedGroupIdsByCondition: Record<string, string[]>,
  groupOptionsByCondition: Record<string, AdminGroup[]>,
  language: CoiCompositionReportLanguage,
): string {
  const selectedIds = new Set(selectedGroupIdsByCondition[condition] ?? [])
  const names = (groupOptionsByCondition[condition] ?? [])
    .filter(group => selectedIds.has(group.id))
    .map(group => group.name)
  if (names.length === 0) return language === 'zh' ? '未选择' : 'None selected'
  if (names.length <= 3) return names.join(language === 'zh' ? '、' : ', ')
  return language === 'zh'
    ? `${names.slice(0, 3).join('、')} 等 ${names.length} 组`
    : `${names.slice(0, 3).join(', ')}, and ${names.length - 3} more`
}

function statusNote(status: string, language: CoiCompositionReportLanguage): string {
  const labels: Record<string, [string, string]> = {
    ok: ['计算完成', 'Calculated successfully'],
    not_applicable: ['无需进行该检验', 'Not applicable'],
    insufficient_data: ['样本不足，无法计算', 'Insufficient data for calculation'],
    dependency_missing: ['缺少计算依赖', 'Required statistical dependency is unavailable'],
    calculation_error: ['计算失败', 'Calculation failed'],
  }
  const pair = labels[status] ?? [status, status]
  return pair[language === 'zh' ? 0 : 1]
}

function testNote(item: StatisticalTestResult, language: CoiCompositionReportLanguage): string {
  if (language === 'zh') return item.note || statusNote(item.status, language)
  if (item.status !== 'ok') return statusNote(item.status, language)
  if (item.p_value_adjusted == null) return 'The test was calculated, but an adjusted p value was unavailable.'
  return item.p_value_adjusted < 0.05
    ? 'The difference was statistically significant after Benjamini–Hochberg correction.'
    : 'The difference was not statistically significant after Benjamini–Hochberg correction.'
}

function globalNote(report: CoiCompositionAnalysisResult, language: CoiCompositionReportLanguage): string {
  if (language === 'zh') return report.global_test.note || statusNote(report.global_test.status, language)
  if (report.global_test.status !== 'ok' || report.global_test.p_value == null) {
    return statusNote(report.global_test.status, language)
  }
  return report.global_test.p_value < 0.05
    ? 'The overall CoI composition differed significantly across the three conditions.'
    : 'No statistically significant overall difference in CoI composition was detected across the three conditions.'
}

function figuresHtml(
  report: CoiCompositionAnalysisResult,
  conditionColumns: string[],
  language: CoiCompositionReportLanguage,
): string {
  const chartLanguage: CoiCompositionReportLanguage = 'en'
  const phases = [
    { key: 'te_ratio', title: 'TE · Triggering Event', subtitle: 'Proportion of four-phase codes' },
    { key: 'ex_ratio', title: 'EX · Exploration', subtitle: 'Proportion of four-phase codes' },
    { key: 'in_ratio', title: 'IN · Integration', subtitle: 'Proportion of four-phase codes' },
    { key: 're_ratio', title: 'RE · Resolution', subtitle: 'Proportion of four-phase codes' },
  ] as const
  const labels = Object.fromEntries(conditionColumns.map(condition => [condition, conditionLabel(condition, chartLanguage)]))
  const phaseStyles = [
    { metric: 'te_ratio', short: 'TE', pattern: 'report-phase-te' },
    { metric: 'ex_ratio', short: 'EX', pattern: 'report-phase-ex' },
    { metric: 'in_ratio', short: 'IN', pattern: 'report-phase-in' },
    { metric: 're_ratio', short: 'RE', pattern: 'report-phase-re' },
  ]
  const stackedRows = conditionColumns.map((condition, rowIndex) => {
    const phasesForCondition = phaseStyles.map(phase => ({
      ...phase,
      value: report.metrics.find(item => item.metric === phase.metric)?.conditions.find(item => item.condition === condition)?.mean ?? 0,
    }))
    const total = phasesForCondition.reduce((sum, phase) => sum + phase.value, 0) || 1
    let cursor = 0
    const segments = phasesForCondition.map(phase => {
      const start = cursor
      const width = phase.value / total
      cursor += width
      return `<rect x="${175 + start * 560}" y="${68 + rowIndex * 48}" width="${width * 560}" height="30" fill="url(#${phase.pattern})" stroke="#fff" stroke-width="1.5"/><text class="stack-text" x="${175 + (start + width / 2) * 560}" y="${87 + rowIndex * 48}" text-anchor="middle">${phase.short} ${(phase.value * 100).toFixed(1)}%</text>`
    }).join('')
    return `<text class="stack-label" x="156" y="${88 + rowIndex * 48}" text-anchor="end">${escapeHtml(conditionLabel(condition, chartLanguage))}</text>${segments}`
  }).join('')
  const axisTicks = [0, 25, 50, 75, 100].map(tick => `<line x1="${175 + tick * 5.6}" x2="${175 + tick * 5.6}" y1="232" y2="238"/><text x="${175 + tick * 5.6}" y="253" text-anchor="middle">${tick}%</text>`).join('')
  const stackedChart = `<section class="stacked-overview"><h3>Mean Composition by Condition<span>Each bar totals 100%; phases and mean proportions are labeled directly.</span></h3><svg viewBox="0 0 800 282" role="img"><defs><style>text{font-family:Arial,Helvetica,sans-serif;text-rendering:geometricPrecision}.stack-label{fill:#0f172a;font-size:15px;font-weight:750}.stack-text{fill:#fff;font-size:13px;font-weight:750;paint-order:stroke;stroke:#17203388;stroke-width:2px}.overview-title{fill:#0f172a;font-size:17px;font-weight:800}.overview-stat{fill:#334155;font-size:12px;font-weight:700}.overview-axis line{stroke:#64748b;stroke-width:1.4}.overview-axis text{fill:#475569;font-size:12px;font-weight:650}.overview-axis .axis-label{fill:#1e293b;font-size:14px;font-weight:750}</style><pattern id="report-phase-te" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#4B5563"/></pattern><pattern id="report-phase-ex" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#0072B2"/></pattern><pattern id="report-phase-in" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#009E73"/></pattern><pattern id="report-phase-re" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#D55E00"/></pattern></defs><text x="24" y="28" class="overview-title">(a) Mean CoI Composition by Condition</text><text x="776" y="28" text-anchor="end" class="overview-stat">PERMANOVA ${escapeHtml(academicPValue(report.global_test.p_value))} · R² = ${academicNumber(report.global_test.effect_size, 2)}</text>${stackedRows}<g class="overview-axis"><line x1="175" x2="735" y1="232" y2="232"/>${axisTicks}<text x="455" y="276" text-anchor="middle" class="axis-label">Mean Code Composition (%)</text></g></svg></section>`
  const compositionMaximum = Math.min(1, Math.max(0.5, Math.ceil(Math.max(...report.observations.flatMap(item => [item.te_ratio, item.ex_ratio, item.in_ratio, item.re_ratio]), 0) * 10) / 10))
  const panels = phases.map((phase, index) => {
    const test = report.statistical_tests.find(item => item.metric === phase.key)
    return staticSessionBoxplotHtml({
    title: phase.title,
    subtitle: phase.subtitle,
    conditions: conditionColumns,
    valuesByCondition: Object.fromEntries(conditionColumns.map(condition => [condition, report.observations.filter(item => item.condition === condition).map(item => item[phase.key])])),
    conditionLabels: labels,
    maximum: compositionMaximum,
    percent: true,
    unitLabel: 'Phase Proportion (%)',
    language: chartLanguage,
    panelLabel: `(${String.fromCharCode(98 + index)})`,
    statisticLabel: test ? `BH-adjusted ${academicPValue(test.p_value_adjusted)}${test.effect_size_name && test.effect_size != null ? ` · ${test.effect_size_name} = ${academicNumber(test.effect_size, 2)}` : ''}` : '',
  })}).join('')
  const caption = language === 'zh'
    ? `<strong>图 1.</strong> 上图为三个条件的平均四阶段构成（每个条形合计100%）；下图为会话级占比分布。箱体表示中位数和四分位区间，须线为1.5倍四分位距范围，小型实心圆点为每场会话，菱形与误差线表示均值及95%置信区间。四个分布面板使用共同的0–${(compositionMaximum * 100).toFixed(0)}%纵轴。`
    : `<strong>Figure 1.</strong> The upper chart shows mean four-phase composition by condition (each bar totals 100%); the lower panels show session-level distributions. Boxes show medians and interquartile ranges, whiskers extend to 1.5 IQR, small solid circles show sessions, and diamonds with error bars show means and 95% confidence intervals. Distribution panels share a 0–${(compositionMaximum * 100).toFixed(0)}% scale.`
  return `<figure>${stackedChart}<div class="boxplot-grid">${panels}</div><figcaption>${caption}</figcaption></figure>`
}

export function buildCoiCompositionReportHtml(
  report: CoiCompositionAnalysisResult,
  coderRole: CoiAnalysisCoderRole,
  conditionColumns: string[],
  selectedGroupIdsByCondition: Record<string, string[]>,
  groupOptionsByCondition: Record<string, AdminGroup[]>,
  language: CoiCompositionReportLanguage = 'zh',
): string {
  const isZh = language === 'zh'
  const generatedAt = new Date().toLocaleString(isZh ? 'zh-CN' : 'en-GB', { hour12: false })
  const groupNameById = new Map(
    Object.values(groupOptionsByCondition).flat().map(group => [group.id, group.name]),
  )

  const sampleRows = conditionColumns.map(condition => `
    <tr><th>${escapeHtml(conditionLabel(condition, language))}</th><td>${selectedGroupIdsByCondition[condition]?.length ?? 0}</td><td>${escapeHtml(selectedGroupNames(condition, selectedGroupIdsByCondition, groupOptionsByCondition, language))}</td><td>${report.sessions_by_condition[condition] ?? 0}</td></tr>
  `).join('')

  const descriptiveRows = report.metrics.map(metric => `
    <tr><th>${escapeHtml(metricLabel(metric.metric, metric.label, language))}</th>${conditionColumns.map(condition => {
      const stats = metric.conditions.find(item => item.condition === condition)
      return `<td>${stats?.n ?? 0}</td><td>${percent(stats?.mean)}</td><td>${percent(stats?.sd)}</td><td>${percent(stats?.median)}</td><td>${percent(stats?.min)}</td><td>${percent(stats?.max)}</td>`
    }).join('')}</tr>
  `).join('')
  const descriptiveHeader = conditionColumns.map(condition => `<th colspan="6">${escapeHtml(conditionLabel(condition, language))}</th>`).join('')
  const descriptiveSubheader = conditionColumns.map(() => `<th>n</th><th>M</th><th>SD</th><th>${isZh ? '中位数' : 'Median'}</th><th>${isZh ? '最小值' : 'Min'}</th><th>${isZh ? '最大值' : 'Max'}</th>`).join('')

  const testRows = report.statistical_tests.map(test => {
    const rawNominal = test.p_value != null && test.p_value < 0.05
    const adjustedSignificant = test.p_value_adjusted != null && test.p_value_adjusted < 0.05
    const rawStatus = rawNominal && !adjustedSignificant
      ? `<small class="p-status">${isZh ? '未经 BH 校正' : 'Unadjusted'}</small>`
      : ''
    return `
      <tr><th>${escapeHtml(metricLabel(test.metric, test.label, language))}</th><td>${escapeHtml(testLabel(test.test, language))}</td><td>${escapeHtml(test.statistic_name || '—')}=${escapeHtml(formatNumber(test.statistic))}</td><td><span class="${rawNominal ? 'p-raw-nominal' : ''}">${escapeHtml(pValueText(test.p_value))}</span>${rawStatus}</td><td><strong class="${adjustedSignificant ? 'p-adjusted-significant' : ''}">${escapeHtml(pValueText(test.p_value_adjusted))}</strong></td><td>${escapeHtml(test.effect_size_name || '—')}=${escapeHtml(formatNumber(test.effect_size))}</td><td>${escapeHtml(testNote(test, language))}</td></tr>
    `
  }).join('')

  const postHocSections = report.post_hoc_tests.map(item => {
    const label = metricLabel(item.metric, item.label, language)
    if (item.status !== 'ok' || item.pairs.length === 0) {
      return `<p class="note"><strong>${escapeHtml(label)}</strong>: ${escapeHtml(isZh ? (item.note || statusNote(item.status, language)) : statusNote(item.status, language))}</p>`
    }
    const pairRows = item.pairs.map(pair => `
      <tr><td>${escapeHtml(conditionLabel(pair.condition_a, language))}</td><td>${escapeHtml(conditionLabel(pair.condition_b, language))}</td><td>${escapeHtml(formatNumber(pair.mean_diff))}</td><td>${escapeHtml(pValueText(pair.p_value_adjusted))}</td><td>${pair.significant ? (isZh ? '是' : 'Yes') : (isZh ? '否' : 'No')}</td></tr>
    `).join('')
    return `<h3>${escapeHtml(label)} (${escapeHtml(postHocMethodLabel(item.method))})</h3><table><thead><tr><th>${isZh ? '条件 A' : 'Condition A'}</th><th>${isZh ? '条件 B' : 'Condition B'}</th><th>${isZh ? '均值差 (B−A)' : 'Mean difference (B−A)'}</th><th>${isZh ? '校正后 p' : 'Adjusted p'}</th><th>${isZh ? '显著' : 'Significant'}</th></tr></thead><tbody>${pairRows}</tbody></table>`
  }).join('')

  const observationRows = report.observations.map(item => `
    <tr><td>${escapeHtml(groupNameById.get(item.group_id) ?? item.group_id)}</td><td>${escapeHtml(item.session_id)}</td><td>${escapeHtml(conditionLabel(item.condition, language))}</td><td>${item.unit_count}</td><td>${item.te_count}</td><td>${item.ex_count}</td><td>${item.in_count}</td><td>${item.re_count}</td><td>${percent(item.te_ratio)}</td><td>${percent(item.ex_ratio)}</td><td>${percent(item.in_ratio)}</td><td>${percent(item.re_ratio)}</td></tr>
  `).join('')

  const excludedRows = report.excluded_sessions.map(item => `
    <tr><td>${escapeHtml(item.group_name ?? item.group_id)}</td><td>${escapeHtml(item.session_id)}</td><td>${escapeHtml(conditionLabel(item.condition, language))}</td><td>${item.uncoded_count}</td><td>${item.total_count}</td><td>${isZh ? `存在未完成的${escapeHtml(coderRoleLabel(coderRole, language))}，整场会话未纳入` : `The session contained incomplete ${escapeHtml(coderRoleLabel(coderRole, language))} and was excluded in full.`}</td></tr>
  `).join('')

  const title = isZh ? 'CoI 编码构成分析报告' : 'CoI Coding Composition Analysis Report'
  const figures = figuresHtml(report, conditionColumns, language)

  return `<!doctype html>
<html lang="${isZh ? 'zh-CN' : 'en'}">
<head>
  <meta charset="utf-8" />
  <title>${title}</title>
  <style>
    body { margin: 32px; color: #172033; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; }
    h1 { margin: 0 0 6px; font-size: 25px; } h2 { margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #d8e0eb; font-size: 17px; } h3 { font-size: 14px; }
    .meta, .note { color: #56657a; font-size: 12px; } .result { padding: 14px 16px; border-left: 4px solid #16a34a; background: #f2faf5; }
    table { width: 100%; margin: 10px 0 18px; border-collapse: collapse; font-size: 11px; } th, td { padding: 7px 8px; border: 1px solid #d8e0eb; text-align: left; vertical-align: top; } th { background: #f4f7fa; }
    .p-raw-nominal { display: inline-block; padding: 1px 5px; border: 1px solid #fed7aa; border-radius: 4px; color: #b45309; background: #fff7ed; font-weight: 700; } .p-adjusted-significant { display: inline-block; padding: 1px 5px; border: 1px solid #fecaca; border-radius: 4px; color: #b91c1c; background: #fef2f2; } .p-status { display: block; margin-top: 2px; color: #b45309; font-size: 9px; }
    figure { margin: 20px 0 30px; padding: 18px 20px; border: 1px solid #d8e0eb; border-radius: 8px; page-break-inside: avoid; }
    figcaption { margin-top: 16px; padding-top: 10px; border-top: 1px solid #e4eaf2; color: #455468; font-size: 11px; }
    .stacked-overview{margin-bottom:16px;padding:12px 14px 8px;border:1px solid #d3dbe5;border-radius:8px}.stacked-overview h3{display:flex;flex-direction:column;margin:0;font-size:16px}.stacked-overview h3 span{color:#526071;font-size:13px;font-weight:550}.stacked-overview svg{display:block;width:100%;height:auto}.stack-label{fill:#0f172a;font-size:15px;font-weight:750}.stack-text{fill:#fff;font-size:13px;font-weight:750;paint-order:stroke;stroke:#17203388;stroke-width:2px}${INTERACTIVE_CHART_CSS}@media print{.stacked-overview{border-color:#777}.stacked-overview svg{filter:grayscale(1) contrast(1.35)}.stack-text{stroke:none}}
    ${STATIC_BOXPLOT_CSS}
    @media print { body { margin: 16mm; } h2 { page-break-after: avoid; } table { page-break-inside: avoid; } }
  </style>
</head>
<body>
  <h1>${title}</h1>
  <div class="meta">${isZh ? '生成时间' : 'Generated'}: ${escapeHtml(generatedAt)}; ${isZh ? '编码来源' : 'Coding source'}: ${escapeHtml(coderRoleLabel(coderRole, language))}; ${isZh ? '纳入完整会话' : 'Included complete sessions'}: ${report.total_sessions}; ${isZh ? '排除会话' : 'Excluded sessions'}: ${report.excluded_sessions.length}</div>
  <h2>1. ${isZh ? '分析口径' : 'Analytic approach'}</h2>
  <p class="note">${isZh ? '以每场会话为一个观测值，分别计算 TE、EX、IN、RE 编码次数占四阶段全部编码次数的比例，再对条件内会话等权汇总。OTHER 不进入四阶段构成分母；存在未完成当前编码来源的观点时，整场会话排除。' : 'Each session was treated as one observation. TE, EX, IN, and RE counts were divided by the total number of four-phase codes within each session, and session-level proportions were then averaged with equal weight within each condition. OTHER was excluded from the four-phase denominator. Sessions containing incomplete codes from the selected coding source were excluded in full.'}</p>
  <h2>2. ${isZh ? '样本范围' : 'Sample'}</h2>
  <table><thead><tr><th>${isZh ? '条件' : 'Condition'}</th><th>${isZh ? '选中群组数' : 'Selected groups'}</th><th>${isZh ? '群组' : 'Groups'}</th><th>${isZh ? '纳入会话数' : 'Included sessions'}</th></tr></thead><tbody>${sampleRows}</tbody></table>
  <h2>3. ${isZh ? '整体构成检验' : 'Overall composition test'}</h2>
  <div class="result"><strong>${escapeHtml(report.global_test.method)}</strong><br>pseudo-F=${escapeHtml(formatNumber(report.global_test.statistic))}; p=${escapeHtml(pValueText(report.global_test.p_value))}; R²=${escapeHtml(formatNumber(report.global_test.effect_size))}; ${isZh ? '置换次数' : 'permutations'}=${report.global_test.permutations}<br><span class="note">${escapeHtml(globalNote(report, language))}</span></div>
  <h2>4. ${isZh ? 'CoI 四阶段构成可视化' : 'Visualization of four-phase CoI composition'}</h2>
  ${figures}
  <h2>5. ${isZh ? '四阶段描述性统计' : 'Descriptive statistics by phase'}</h2>
  <table><thead><tr><th rowspan="2">${isZh ? '阶段' : 'Phase'}</th>${descriptiveHeader}</tr><tr>${descriptiveSubheader}</tr></thead><tbody>${descriptiveRows}</tbody></table>
  <h2>6. ${isZh ? '阶段层面检验' : 'Phase-level tests'}</h2>
  <p class="note">${isZh ? '颜色说明：橙色表示原始 p < 0.05；红色表示 BH 校正后 p < 0.05。' : 'Color key: orange indicates an unadjusted p < .05; red indicates a BH-adjusted p < .05.'}</p>
  <table><thead><tr><th>${isZh ? '阶段' : 'Phase'}</th><th>${isZh ? '检验' : 'Test'}</th><th>${isZh ? '统计量' : 'Statistic'}</th><th>${isZh ? '原始 p' : 'Unadjusted p'}</th><th>${isZh ? 'BH 校正后 p' : 'BH-adjusted p'}</th><th>${isZh ? '效应量' : 'Effect size'}</th><th>${isZh ? '说明' : 'Interpretation'}</th></tr></thead><tbody>${testRows}</tbody></table>
  <h2>7. ${isZh ? '事后检验' : 'Post hoc tests'}</h2>${postHocSections}
  <h2>8. ${isZh ? '会话级分析数据' : 'Session-level analysis data'}</h2>
  <table><thead><tr><th>${isZh ? '群组' : 'Group'}</th><th>${isZh ? '会话 ID' : 'Session ID'}</th><th>${isZh ? '条件' : 'Condition'}</th><th>${isZh ? '有效观点' : 'Valid units'}</th><th>TE</th><th>EX</th><th>IN</th><th>RE</th><th>TE%</th><th>EX%</th><th>IN%</th><th>RE%</th></tr></thead><tbody>${observationRows}</tbody></table>
  <h2>9. ${isZh ? '被排除会话' : 'Excluded sessions'}</h2>
  ${excludedRows ? `<table><thead><tr><th>${isZh ? '群组' : 'Group'}</th><th>${isZh ? '会话 ID' : 'Session ID'}</th><th>${isZh ? '条件' : 'Condition'}</th><th>${isZh ? '未编码观点' : 'Uncoded units'}</th><th>${isZh ? '全部观点' : 'All units'}</th><th>${isZh ? '原因' : 'Reason'}</th></tr></thead><tbody>${excludedRows}</tbody></table>` : `<p class="note">${isZh ? '没有因编码不完整而被排除的会话。' : 'No sessions were excluded because of incomplete coding.'}</p>`}
  ${chartModalHtml(language)}${INTERACTIVE_CHART_SCRIPT}
</body>
</html>`
}
