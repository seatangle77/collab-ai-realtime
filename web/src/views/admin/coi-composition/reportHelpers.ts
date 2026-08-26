import type { CoiCompositionAnalysisResult } from '../../../api/admin/coi-composition-analysis'
import type { CoiAnalysisCoderRole, PostHocResult, StatisticalTestResult } from '../../../api/admin/coi-analysis'
import type { AdminGroup } from '../../../types/admin'
import { formatNumber, pValueText } from '../coi/reportHelpers'

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

function meanFor(report: CoiCompositionAnalysisResult, metric: string, condition: string): number {
  return report.metrics.find(item => item.metric === metric)
    ?.conditions.find(item => item.condition === condition)?.mean ?? 0
}

function figuresHtml(
  report: CoiCompositionAnalysisResult,
  conditionColumns: string[],
  language: CoiCompositionReportLanguage,
): string {
  const phases = [
    { metric: 'te_ratio', short: 'TE', name: language === 'zh' ? '触发事件' : 'Triggering Event' },
    { metric: 'ex_ratio', short: 'EX', name: language === 'zh' ? '探索' : 'Exploration' },
    { metric: 'in_ratio', short: 'IN', name: language === 'zh' ? '整合' : 'Integration' },
    { metric: 're_ratio', short: 'RE', name: language === 'zh' ? '解决' : 'Resolution' },
  ]
  const colors: Record<string, string> = {
    no_assistance: '#64748b', glasses: '#3b82f6', app_notification: '#f97316',
  }
  const meanRows = phases.map(phase => `
    <div class="mean-group">
      <div class="phase-label"><strong>${phase.short}</strong><span>${phase.name}</span></div>
      <div>${conditionColumns.map(condition => {
        const value = meanFor(report, phase.metric, condition)
        return `<div class="mean-row"><span>${escapeHtml(conditionLabel(condition, language))}</span><div class="mean-track"><i style="width:${Math.min(100, value / 0.4 * 100)}%;background:${colors[condition] ?? '#64748b'}"></i></div><strong>${percent(value)}</strong></div>`
      }).join('')}</div>
    </div>
  `).join('')

  const comparisons = conditionColumns.filter(condition => condition !== 'no_assistance')
  const deltaRows = phases.map(phase => `
    <div class="delta-group">
      <div class="phase-label"><strong>${phase.short}</strong><span>${phase.name}</span></div>
      <div>${comparisons.map(condition => {
        const delta = (meanFor(report, phase.metric, condition) - meanFor(report, phase.metric, 'no_assistance')) * 100
        const width = Math.min(50, Math.abs(delta) / 16 * 100)
        const left = delta < 0 ? 50 - width : 50
        const value = `${delta > 0 ? '+' : ''}${delta.toFixed(1)} pp`
        return `<div class="delta-row"><span>${escapeHtml(conditionLabel(condition, language))}</span><div class="delta-track"><b></b><i style="left:${left}%;width:${width}%;background:${colors[condition] ?? '#64748b'}"></i></div><strong>${escapeHtml(value)}</strong></div>`
      }).join('')}</div>
    </div>
  `).join('')

  const figureOneCaption = language === 'zh'
    ? '<strong>图 1.</strong> 三种辅助条件下 Community of Inquiry（CoI）四阶段的平均编码占比。各场会话先分别计算阶段占比，再在条件内等权平均。TE = 触发事件；EX = 探索；IN = 整合；RE = 解决。'
    : '<strong>Figure 1.</strong> Mean proportions of the four Community of Inquiry (CoI) phases across the three assistance conditions. Phase proportions were first calculated within each session and then averaged across sessions, with each session weighted equally. TE = Triggering Event; EX = Exploration; IN = Integration; RE = Resolution.'
  const figureTwoCaption = language === 'zh'
    ? '<strong>图 2.</strong> 智能眼镜和 APP 通知条件相对无辅助条件的 CoI 阶段平均占比差异。数值表示百分点差异（pp）；正值表示高于无辅助，负值表示低于无辅助。该图呈现描述性差异，不代表统计显著。'
    : '<strong>Figure 2.</strong> Differences in mean CoI phase proportions between each assisted condition and the no-assistance condition. Values represent percentage-point differences (pp); positive values indicate higher proportions and negative values indicate lower proportions. These are descriptive differences and do not imply statistical significance.'

  return `
    <figure><div class="mean-axis"><span>0%</span><span>10%</span><span>20%</span><span>30%</span><span>40%</span></div>${meanRows}<figcaption>${figureOneCaption}</figcaption></figure>
    <figure><div class="delta-axis"><span>−8</span><span>−4</span><span>0</span><span>+4</span><span>+8 pp</span></div>${deltaRows}<figcaption>${figureTwoCaption}</figcaption></figure>
  `
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
    .phase-label { display: flex; flex-direction: column; justify-content: center; text-align: right; } .phase-label span { color: #7b899d; font-size: 9px; }
    .mean-axis, .delta-axis { display: flex; justify-content: space-between; margin: 0 58px 6px 190px; color: #8a98aa; font-size: 9px; }
    .mean-group, .delta-group { display: grid; grid-template-columns: 100px minmax(0, 1fr); gap: 14px; padding: 10px 0; border-top: 1px solid #edf1f5; }
    .mean-row, .delta-row { display: grid; grid-template-columns: 76px minmax(0, 1fr) 48px; align-items: center; gap: 8px; min-height: 21px; color: #64748b; font-size: 9px; }
    .mean-row > span, .delta-row > span { text-align: right; } .mean-row > strong, .delta-row > strong { color: #334155; font-size: 9px; }
    .mean-track { height: 15px; background: repeating-linear-gradient(to right, transparent 0, transparent calc(25% - 1px), #e5eaf1 25%); }
    .mean-track i { display: block; height: 15px; border-radius: 2px; }
    .delta-track { position: relative; height: 15px; background: linear-gradient(to right, transparent 24.8%, #e5eaf1 25%, transparent 25.2%, transparent 74.8%, #e5eaf1 75%, transparent 75.2%); }
    .delta-track b { position: absolute; top: 0; bottom: 0; left: 50%; border-left: 1px solid #8996a8; } .delta-track i { position: absolute; top: 2px; height: 11px; border-radius: 2px; }
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
