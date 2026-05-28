import type {
  CoiAnalysisMode,
  CoiAnalysisResult,
  MetricSummary,
  NormalityConditionResult,
  PostHocResult,
  StatisticalTestResult,
} from '../../../api/admin/coi-analysis'
import type { AdminGroup } from '../../../types/admin'

export const CONDITION_LABELS: Record<string, string> = {
  no_assistance: '无辅助',
  glasses: '智能眼镜',
  app_notification: 'APP 通知',
}

export function conditionLabel(condition: string): string {
  return CONDITION_LABELS[condition] ?? condition
}

export function modeDescription(mode: CoiAnalysisMode): string {
  return mode === 'two_conditions'
    ? 'no_assistance vs glasses'
    : 'no_assistance / glasses / app_notification'
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
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

export function testLabel(test: StatisticalTestResult['test']): string {
  const labels: Record<StatisticalTestResult['test'], string> = {
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

export function pValueText(value: number | null | undefined): string {
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

export function buildCoiReportHtml(
  report: CoiAnalysisResult,
  mode: CoiAnalysisMode,
  conditionColumns: string[],
  selectedGroupIdsByCondition: Record<string, string[]>,
  groupOptionsByCondition: Record<string, AdminGroup[]>,
): string {
  const generatedAt = new Date().toLocaleString()

  const descriptiveHeader = () => {
    const conditionHeaders = conditionColumns.map((c) => `<th colspan="6">${escapeHtml(conditionLabel(c))}</th>`).join('')
    const subHeaders = conditionColumns.map(() => `<th>n</th><th>M</th><th>SD</th><th>Median</th><th>Min</th><th>Max</th>`).join('')
    return `<tr><th rowspan="2">指标</th>${conditionHeaders}${mode === 'two_conditions' ? '<th rowspan="2">均值差</th>' : ''}</tr><tr>${subHeaders}</tr>`
  }

  const descriptiveRows = report.metrics.map((metric) => {
    const cells = conditionColumns.map((c) => {
      const s = statFor(metric, c)
      return `<td>${s?.n ?? 0}</td><td>${escapeHtml(formatNumber(s?.mean))}</td><td>${escapeHtml(formatNumber(s?.sd))}</td><td>${escapeHtml(formatNumber(s?.median))}</td><td>${escapeHtml(formatNumber(s?.min))}</td><td>${escapeHtml(formatNumber(s?.max))}</td>`
    }).join('')
    return `<tr><th>${escapeHtml(metric.label)}</th>${cells}${mode === 'two_conditions' ? `<td>${escapeHtml(meanDiffText(metric))}</td>` : ''}</tr>`
  }).join('')

  const normalityRows = report.normality.map((item) => `
    <tr><th>${escapeHtml(item.label)}</th><td>${escapeHtml(conditionLabel(item.condition))}</td><td>${item.n}</td><td>${escapeHtml(formatNumber(item.statistic))}</td><td>${escapeHtml(pValueText(item.p_value))}</td><td>${escapeHtml(normalityStatusLabel(item))}</td><td>${escapeHtml(item.note)}</td></tr>
  `).join('')

  const inferentialRows = report.statistical_tests.map((item) => `
    <tr><th>${escapeHtml(item.label)}</th><td>${escapeHtml(testLabel(item.test))}</td><td>${escapeHtml(item.statistic_name || '—')}</td><td>${escapeHtml(formatNumber(item.statistic))}</td><td>${escapeHtml(pValueText(item.p_value))}</td><td>${escapeHtml(item.effect_size_name || '—')}</td><td>${escapeHtml(formatNumber(item.effect_size))}</td><td>${escapeHtml(testStatusLabel(item.status))}</td><td>${escapeHtml(item.note)}</td></tr>
  `).join('')

  const postHocMethodLabel = (method: PostHocResult['method']) =>
    method === 'tukey_hsd' ? 'Tukey HSD' : method === 'dunn_bonferroni' ? 'Dunn + Bonferroni' : '—'

  const postHocSection = report.post_hoc_tests.map((item) => {
    if (item.status !== 'ok' || item.pairs.length === 0) {
      return `<p class="note"><strong>${escapeHtml(item.label)}</strong>：${escapeHtml(item.note)}</p>`
    }
    const pairRows = item.pairs.map((pair) => `
      <tr><td>${escapeHtml(conditionLabel(pair.condition_a))}</td><td>${escapeHtml(conditionLabel(pair.condition_b))}</td><td>${escapeHtml(formatNumber(pair.mean_diff))}</td><td>${escapeHtml(pValueText(pair.p_value_adjusted))}</td><td>${pair.significant === true ? '*' : pair.significant === false ? 'ns' : '—'}</td></tr>
    `).join('')
    return `<h3>${escapeHtml(item.label)}（${escapeHtml(postHocMethodLabel(item.method))}）</h3><table><thead><tr><th>条件 A</th><th>条件 B</th><th>均值差 (B−A)</th><th>p (校正后)</th><th>显著</th></tr></thead><tbody>${pairRows}</tbody></table>`
  }).join('')

  const sampleRows = conditionColumns.map((c) => `
    <tr><th>${escapeHtml(conditionLabel(c))}</th><td>${selectedGroupIdsByCondition[c]?.length ?? 0}</td><td>${escapeHtml(selectedGroupNames(c, selectedGroupIdsByCondition, groupOptionsByCondition))}</td></tr>
  `).join('')

  const excludedRows = report.excluded_sessions.length > 0
    ? report.excluded_sessions.map((s) => `<tr><td>${escapeHtml(s.session_id)}</td><td>${escapeHtml(s.group_name ?? s.group_id)}</td><td>${escapeHtml(conditionLabel(s.condition))}</td><td>${s.uncoded_count} / ${s.total_count}</td></tr>`).join('')
    : '<tr><td colspan="4">无排除会话</td></tr>'

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>CoI 认知参与度分析报告</title>
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
    @media print { body { margin: 18mm; } h2 { page-break-after: avoid; } }
  </style>
</head>
<body>
  <h1>CoI 认知参与度分析报告</h1>
  <div class="meta">生成时间：${escapeHtml(generatedAt)}</div>
  <div class="meta">分析模式：${escapeHtml(modeDescription(mode))}；纳入会话数：${report.total_sessions}</div>
  <h2>1. 分析方法</h2>
  <p class="note">基于 CoI 框架 Cognitive Presence 维度对已编码发言进行量化分析。权重：TE=1, EX=2, IN=3, RE=4。高阶认知参与比例 = (IN+RE) / 总有效认知话语数。加权得分 = Σ(类别数×权重) / 总有效认知话语数。只纳入全部发言已编码的会话。</p>
  <h2>2. 样本选择</h2>
  <table><thead><tr><th>条件</th><th>小组数</th><th>小组</th></tr></thead><tbody>${sampleRows}</tbody></table>
  <h2>3. 排除会话</h2>
  <table><thead><tr><th>会话 ID</th><th>小组</th><th>条件</th><th>未编码 / 总计</th></tr></thead><tbody>${excludedRows}</tbody></table>
  <h2>4. 描述性统计</h2>
  <table><thead>${descriptiveHeader()}</thead><tbody>${descriptiveRows}</tbody></table>
  <h2>5. 正态性检查（Shapiro-Wilk）</h2>
  <table><thead><tr><th>指标</th><th>条件</th><th>n</th><th>W</th><th>p</th><th>判断</th><th>说明</th></tr></thead><tbody>${normalityRows}</tbody></table>
  <h2>6. 推断统计</h2>
  <table><thead><tr><th>指标</th><th>检验</th><th>统计量</th><th>值</th><th>p</th><th>Effect size</th><th>值</th><th>状态</th><th>说明</th></tr></thead><tbody>${inferentialRows}</tbody></table>
  <h2>7. 事后检验（Post-hoc）</h2>
  <p class="note">仅三条件且全局检验 p &lt; 0.05 时执行；Tukey HSD 用于 ANOVA，Dunn + Bonferroni 用于 Kruskal-Wallis。</p>
  ${postHocSection}
</body>
</html>`
}
