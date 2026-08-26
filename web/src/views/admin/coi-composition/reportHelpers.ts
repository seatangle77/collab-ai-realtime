import type { CoiCompositionAnalysisResult } from '../../../api/admin/coi-composition-analysis'
import type { CoiAnalysisCoderRole, PostHocResult } from '../../../api/admin/coi-analysis'
import type { AdminGroup } from '../../../types/admin'
import {
  coderRoleLabel,
  conditionLabel,
  formatNumber,
  pValueText,
  selectedGroupNames,
  testLabel,
} from '../coi/reportHelpers'

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

function postHocMethodLabel(method: PostHocResult['method']): string {
  if (method === 'tukey_hsd') return 'Tukey HSD'
  if (method === 'dunn_bonferroni') return 'Dunn + Bonferroni'
  return '—'
}

export function buildCoiCompositionReportHtml(
  report: CoiCompositionAnalysisResult,
  coderRole: CoiAnalysisCoderRole,
  conditionColumns: string[],
  selectedGroupIdsByCondition: Record<string, string[]>,
  groupOptionsByCondition: Record<string, AdminGroup[]>,
): string {
  const generatedAt = new Date().toLocaleString('zh-CN', { hour12: false })
  const groupNameById = new Map(
    Object.values(groupOptionsByCondition).flat().map(group => [group.id, group.name]),
  )
  const phases = [
    { metric: 'te_ratio', key: 'te_ratio', label: 'TE', color: '#64748b' },
    { metric: 'ex_ratio', key: 'ex_ratio', label: 'EX', color: '#3b82f6' },
    { metric: 'in_ratio', key: 'in_ratio', label: 'IN', color: '#16a34a' },
    { metric: 're_ratio', key: 're_ratio', label: 'RE', color: '#f97316' },
  ] as const

  const sampleRows = conditionColumns.map(condition => `
    <tr><th>${escapeHtml(conditionLabel(condition))}</th><td>${selectedGroupIdsByCondition[condition]?.length ?? 0}</td><td>${escapeHtml(selectedGroupNames(condition, selectedGroupIdsByCondition, groupOptionsByCondition))}</td><td>${report.sessions_by_condition[condition] ?? 0}</td></tr>
  `).join('')

  const compositionRows = conditionColumns.map(condition => {
    const segments = phases.map(phase => {
      const value = report.metrics.find(metric => metric.metric === phase.metric)
        ?.conditions.find(item => item.condition === condition)?.mean ?? 0
      return `<span style="width:${Math.max(0, value * 100)}%;background:${phase.color}" title="${phase.label}: ${percent(value)}">${value >= 0.095 ? `${phase.label} ${percent(value)}` : ''}</span>`
    }).join('')
    return `<div class="chart-row"><strong>${escapeHtml(conditionLabel(condition))}</strong><div class="stacked-bar">${segments}</div></div>`
  }).join('')

  const descriptiveRows = report.metrics.map(metric => `
    <tr><th>${escapeHtml(metric.label)}</th>${conditionColumns.map(condition => {
      const stats = metric.conditions.find(item => item.condition === condition)
      return `<td>${stats?.n ?? 0}</td><td>${percent(stats?.mean)}</td><td>${percent(stats?.sd)}</td><td>${percent(stats?.median)}</td><td>${percent(stats?.min)}</td><td>${percent(stats?.max)}</td>`
    }).join('')}</tr>
  `).join('')
  const descriptiveHeader = conditionColumns.map(condition => `<th colspan="6">${escapeHtml(conditionLabel(condition))}</th>`).join('')
  const descriptiveSubheader = conditionColumns.map(() => '<th>n</th><th>M</th><th>SD</th><th>Median</th><th>Min</th><th>Max</th>').join('')

  const testRows = report.statistical_tests.map(test => `
    <tr><th>${escapeHtml(test.label)}</th><td>${escapeHtml(testLabel(test.test))}</td><td>${escapeHtml(test.statistic_name || '—')}=${escapeHtml(formatNumber(test.statistic))}</td><td>${escapeHtml(pValueText(test.p_value))}</td><td>${escapeHtml(pValueText(test.p_value_adjusted))}</td><td>${escapeHtml(test.effect_size_name || '—')}=${escapeHtml(formatNumber(test.effect_size))}</td><td>${escapeHtml(test.note)}</td></tr>
  `).join('')

  const postHocSections = report.post_hoc_tests.map(item => {
    if (item.status !== 'ok' || item.pairs.length === 0) {
      return `<p class="note"><strong>${escapeHtml(item.label)}</strong>：${escapeHtml(item.note)}</p>`
    }
    const pairRows = item.pairs.map(pair => `
      <tr><td>${escapeHtml(conditionLabel(pair.condition_a))}</td><td>${escapeHtml(conditionLabel(pair.condition_b))}</td><td>${escapeHtml(formatNumber(pair.mean_diff))}</td><td>${escapeHtml(pValueText(pair.p_value_adjusted))}</td><td>${pair.significant ? '*' : 'ns'}</td></tr>
    `).join('')
    return `<h3>${escapeHtml(item.label)}（${escapeHtml(postHocMethodLabel(item.method))}）</h3><table><thead><tr><th>条件 A</th><th>条件 B</th><th>均值差 (B−A)</th><th>校正后 p</th><th>显著</th></tr></thead><tbody>${pairRows}</tbody></table>`
  }).join('')

  const observationRows = report.observations.map(item => `
    <tr><td>${escapeHtml(groupNameById.get(item.group_id) ?? item.group_id)}</td><td>${escapeHtml(item.session_id)}</td><td>${escapeHtml(conditionLabel(item.condition))}</td><td>${item.unit_count}</td><td>${item.te_count}</td><td>${item.ex_count}</td><td>${item.in_count}</td><td>${item.re_count}</td><td>${percent(item.te_ratio)}</td><td>${percent(item.ex_ratio)}</td><td>${percent(item.in_ratio)}</td><td>${percent(item.re_ratio)}</td></tr>
  `).join('')

  const excludedRows = report.excluded_sessions.map(item => `
    <tr><td>${escapeHtml(item.group_name ?? item.group_id)}</td><td>${escapeHtml(item.session_id)}</td><td>${escapeHtml(conditionLabel(item.condition))}</td><td>${item.uncoded_count}</td><td>${item.total_count}</td><td>存在未完成的 ${escapeHtml(coderRoleLabel(coderRole))}，整场会话未纳入</td></tr>
  `).join('')

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>CoI 编码构成分析报告</title>
  <style>
    body { margin: 32px; color: #172033; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; }
    h1 { margin: 0 0 6px; font-size: 25px; } h2 { margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #d8e0eb; font-size: 17px; } h3 { font-size: 14px; }
    .meta, .note { color: #56657a; font-size: 12px; } .result { padding: 14px 16px; border-left: 4px solid #16a34a; background: #f2faf5; }
    table { width: 100%; margin: 10px 0 18px; border-collapse: collapse; font-size: 11px; } th, td { padding: 7px 8px; border: 1px solid #d8e0eb; text-align: left; vertical-align: top; } th { background: #f4f7fa; }
    .legend { display: flex; gap: 14px; margin: 10px 0; font-size: 12px; } .legend i { display: inline-block; width: 9px; height: 9px; margin-right: 4px; border-radius: 2px; }
    .chart-row { display: grid; grid-template-columns: 90px minmax(0, 1fr); align-items: center; gap: 12px; margin: 14px 0; font-size: 12px; }
    .stacked-bar { display: flex; height: 40px; overflow: hidden; border-radius: 7px; background: #eef2f7; } .stacked-bar span { display: grid; place-items: center; overflow: hidden; color: white; font-size: 10px; font-weight: 700; white-space: nowrap; }
    @media print { body { margin: 16mm; } h2 { page-break-after: avoid; } table, .chart-row { page-break-inside: avoid; } }
  </style>
</head>
<body>
  <h1>CoI 编码构成分析报告</h1>
  <div class="meta">生成时间：${escapeHtml(generatedAt)}；编码来源：${escapeHtml(coderRoleLabel(coderRole))}；纳入完整会话：${report.total_sessions}；排除会话：${report.excluded_sessions.length}</div>
  <h2>1. 分析口径</h2>
  <p class="note">以每场会话为一个观测值，分别计算 TE、EX、IN、RE 编码次数占四阶段全部编码次数的比例，再对条件内会话等权汇总。OTHER 不进入四阶段构成分母；存在未完成当前编码来源的观点时，整场会话排除。</p>
  <h2>2. 样本范围</h2>
  <table><thead><tr><th>条件</th><th>选中群组数</th><th>群组</th><th>纳入会话数</th></tr></thead><tbody>${sampleRows}</tbody></table>
  <h2>3. 整体构成检验</h2>
  <div class="result"><strong>${escapeHtml(report.global_test.method)}</strong><br>pseudo-F=${escapeHtml(formatNumber(report.global_test.statistic))}；p=${escapeHtml(pValueText(report.global_test.p_value))}；R²=${escapeHtml(formatNumber(report.global_test.effect_size))}；置换次数=${report.global_test.permutations}<br><span class="note">${escapeHtml(report.global_test.note)}</span></div>
  <h2>4. 三条件 CoI 编码构成</h2>
  <div class="legend">${phases.map(phase => `<span><i style="background:${phase.color}"></i>${phase.label}</span>`).join('')}</div>
  ${compositionRows}
  <h2>5. 四阶段描述性统计</h2>
  <table><thead><tr><th rowspan="2">阶段</th>${descriptiveHeader}</tr><tr>${descriptiveSubheader}</tr></thead><tbody>${descriptiveRows}</tbody></table>
  <h2>6. 阶段层面检验</h2>
  <table><thead><tr><th>阶段</th><th>检验</th><th>统计量</th><th>p</th><th>p_adj (BH)</th><th>Effect size</th><th>说明</th></tr></thead><tbody>${testRows}</tbody></table>
  <h2>7. 事后检验</h2>${postHocSections}
  <h2>8. 会话级分析数据</h2>
  <table><thead><tr><th>群组</th><th>会话 ID</th><th>条件</th><th>有效观点</th><th>TE</th><th>EX</th><th>IN</th><th>RE</th><th>TE%</th><th>EX%</th><th>IN%</th><th>RE%</th></tr></thead><tbody>${observationRows}</tbody></table>
  <h2>9. 被排除会话</h2>
  ${excludedRows ? `<table><thead><tr><th>群组</th><th>会话 ID</th><th>条件</th><th>未编码观点</th><th>全部观点</th><th>原因</th></tr></thead><tbody>${excludedRows}</tbody></table>` : '<p class="note">没有因编码不完整而被排除的会话。</p>'}
</body>
</html>`
}
