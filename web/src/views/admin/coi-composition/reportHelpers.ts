import type { CoiCompositionAnalysisResult } from '../../../api/admin/coi-composition-analysis'
import type { CoiAnalysisCoderRole, PostHocResult, StatisticalTestResult } from '../../../api/admin/coi-analysis'
import type { AdminGroup } from '../../../types/admin'
import { formatNumber, pValueText } from '../coi/reportHelpers'
import { STATIC_BOXPLOT_CSS, staticSessionBoxplotHtml } from '../coi/staticBoxplotHtml'

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
  const phases = [
    { key: 'te_ratio', title: language === 'zh' ? 'TE · 触发事件' : 'TE · Triggering Event', subtitle: language === 'zh' ? '触发事件占四阶段编码的比例' : 'Triggering Event as a proportion of four-phase codes' },
    { key: 'ex_ratio', title: language === 'zh' ? 'EX · 探索' : 'EX · Exploration', subtitle: language === 'zh' ? '探索占四阶段编码的比例' : 'Exploration as a proportion of four-phase codes' },
    { key: 'in_ratio', title: language === 'zh' ? 'IN · 整合' : 'IN · Integration', subtitle: language === 'zh' ? '整合占四阶段编码的比例' : 'Integration as a proportion of four-phase codes' },
    { key: 're_ratio', title: language === 'zh' ? 'RE · 解决' : 'RE · Resolution', subtitle: language === 'zh' ? '解决占四阶段编码的比例' : 'Resolution as a proportion of four-phase codes' },
  ] as const
  const labels = Object.fromEntries(conditionColumns.map(condition => [condition, conditionLabel(condition, language)]))
  const compositionMaximum = Math.min(1, Math.max(0.5, Math.ceil(Math.max(...report.observations.flatMap(item => [item.te_ratio, item.ex_ratio, item.in_ratio, item.re_ratio]), 0) * 10) / 10))
  const panels = phases.map(phase => staticSessionBoxplotHtml({
    title: phase.title,
    subtitle: phase.subtitle,
    conditions: conditionColumns,
    valuesByCondition: Object.fromEntries(conditionColumns.map(condition => [condition, report.observations.filter(item => item.condition === condition).map(item => item[phase.key])])),
    conditionLabels: labels,
    maximum: compositionMaximum,
    percent: true,
    unitLabel: language === 'zh' ? '阶段占比' : 'Phase proportion',
    language,
  })).join('')
  const caption = language === 'zh'
    ? `<strong>图 1.</strong> 三种实验条件下CoI四阶段编码占比的会话级分布。箱体表示中位数和四分位区间，须线为1.5倍四分位距范围，圆点为每场会话，菱形与误差线表示均值及95%置信区间。四个面板使用共同的0–${(compositionMaximum * 100).toFixed(0)}%纵轴。`
    : `<strong>Figure 1.</strong> Session-level distributions of the four CoI phase proportions across the three conditions. Boxes show medians and interquartile ranges, whiskers extend to 1.5 IQR, points show sessions, and diamonds with error bars show means and 95% confidence intervals. All panels share a 0–${(compositionMaximum * 100).toFixed(0)}% scale.`
  return `<figure><div class="boxplot-grid">${panels}</div><figcaption>${caption}</figcaption></figure>`
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

  const testRows = report.statistical_tests.map(test => `
    <tr><th>${escapeHtml(metricLabel(test.metric, test.label, language))}</th><td>${escapeHtml(testLabel(test.test, language))}</td><td>${escapeHtml(test.statistic_name || '—')}=${escapeHtml(formatNumber(test.statistic))}</td><td>${escapeHtml(pValueText(test.p_value))}</td><td>${escapeHtml(pValueText(test.p_value_adjusted))}</td><td>${escapeHtml(test.effect_size_name || '—')}=${escapeHtml(formatNumber(test.effect_size))}</td><td>${escapeHtml(testNote(test, language))}</td></tr>
  `).join('')

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
    figure { margin: 20px 0 30px; padding: 18px 20px; border: 1px solid #d8e0eb; border-radius: 8px; page-break-inside: avoid; }
    figcaption { margin-top: 16px; padding-top: 10px; border-top: 1px solid #e4eaf2; color: #455468; font-size: 11px; }
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
  <table><thead><tr><th>${isZh ? '阶段' : 'Phase'}</th><th>${isZh ? '检验' : 'Test'}</th><th>${isZh ? '统计量' : 'Statistic'}</th><th>p</th><th>${isZh ? '校正后 p（BH）' : 'BH-adjusted p'}</th><th>${isZh ? '效应量' : 'Effect size'}</th><th>${isZh ? '说明' : 'Interpretation'}</th></tr></thead><tbody>${testRows}</tbody></table>
  <h2>7. ${isZh ? '事后检验' : 'Post hoc tests'}</h2>${postHocSections}
  <h2>8. ${isZh ? '会话级分析数据' : 'Session-level analysis data'}</h2>
  <table><thead><tr><th>${isZh ? '群组' : 'Group'}</th><th>${isZh ? '会话 ID' : 'Session ID'}</th><th>${isZh ? '条件' : 'Condition'}</th><th>${isZh ? '有效观点' : 'Valid units'}</th><th>TE</th><th>EX</th><th>IN</th><th>RE</th><th>TE%</th><th>EX%</th><th>IN%</th><th>RE%</th></tr></thead><tbody>${observationRows}</tbody></table>
  <h2>9. ${isZh ? '被排除会话' : 'Excluded sessions'}</h2>
  ${excludedRows ? `<table><thead><tr><th>${isZh ? '群组' : 'Group'}</th><th>${isZh ? '会话 ID' : 'Session ID'}</th><th>${isZh ? '条件' : 'Condition'}</th><th>${isZh ? '未编码观点' : 'Uncoded units'}</th><th>${isZh ? '全部观点' : 'All units'}</th><th>${isZh ? '原因' : 'Reason'}</th></tr></thead><tbody>${excludedRows}</tbody></table>` : `<p class="note">${isZh ? '没有因编码不完整而被排除的会话。' : 'No sessions were excluded because of incomplete coding.'}</p>`}
</body>
</html>`
}
