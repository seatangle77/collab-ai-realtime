import type {
  QCronbachAlphaResult,
  QMetricSummary,
  QNormalityConditionResult,
  QStatisticalTestRecommendation,
  QStatisticalTestResult,
  QuestionnaireAnalysisMode,
  QuestionnaireAnalysisResult,
  QuestionnaireScaleKind,
} from '../../../api/admin/questionnaire-analysis'

export const CONDITION_LABELS: Record<string, string> = {
  no_assistance: '无辅助',
  glasses: '智能眼镜',
  app_notification: 'APP 通知',
}

export function conditionLabel(condition: string): string {
  return CONDITION_LABELS[condition] ?? condition
}

export function scaleLabel(scale: QuestionnaireScaleKind): string {
  return scale === 'srcc' ? 'SRCC（协作自我调节）' : 'PCS（感知凝聚力）'
}

export function modeDescription(mode: QuestionnaireAnalysisMode): string {
  return mode === 'two_conditions'
    ? 'no_assistance vs glasses'
    : 'no_assistance / glasses / app_notification'
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
}

export function pValueText(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value < 0.001) return '< .001'
  return formatNumber(value)
}

export function statFor(metric: QMetricSummary, condition: string) {
  return metric.conditions.find((c) => c.condition === condition)
}

export function normalityStatusLabel(item: QNormalityConditionResult): string {
  if (item.status === 'ok') return item.is_normal ? '近似正态' : '偏离正态'
  if (item.status === 'insufficient_n') return '样本不足'
  if (item.status === 'constant_values') return '数值恒定'
  return '缺少依赖'
}

export function normalityTagType(item: QNormalityConditionResult): 'success' | 'warning' | 'info' | 'danger' {
  if (item.status === 'ok') return item.is_normal ? 'success' : 'warning'
  if (item.status === 'dependency_missing') return 'danger'
  return 'info'
}

export function testLabel(test: QStatisticalTestRecommendation['recommended_test']): string {
  const labels: Record<QStatisticalTestRecommendation['recommended_test'], string> = {
    independent_samples_t_test: 'Independent-samples t-test',
    mann_whitney_u: 'Mann-Whitney U',
    one_way_anova: 'One-way ANOVA',
    kruskal_wallis: 'Kruskal-Wallis',
    insufficient_data: '样本不足',
  }
  return labels[test]
}

export function testStatusLabel(status: QStatisticalTestResult['status']): string {
  const labels: Record<QStatisticalTestResult['status'], string> = {
    ok: '已计算',
    insufficient_data: '样本不足',
    dependency_missing: '缺少依赖',
    calculation_error: '无法计算',
  }
  return labels[status]
}

export function cronbachStatusLabel(item: QCronbachAlphaResult): string {
  if (item.status === 'ok') return item.alpha !== null ? formatNumber(item.alpha) : '—'
  if (item.status === 'insufficient_n') return '样本不足'
  if (item.status === 'insufficient_items') return '题项不足'
  if (item.status === 'constant_values') return '数值恒定'
  return '—'
}

export function cronbachTagType(item: QCronbachAlphaResult): 'success' | 'warning' | 'info' | 'danger' {
  if (item.status !== 'ok' || item.alpha === null) return 'info'
  if (item.alpha >= 0.7) return 'success'
  if (item.alpha >= 0.6) return 'warning'
  return 'danger'
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

export function buildQuestionnaireReportHtml(
  report: QuestionnaireAnalysisResult,
  mode: QuestionnaireAnalysisMode,
  scale: QuestionnaireScaleKind,
): string {
  const conditionColumns = report.conditions
  const generatedAt = new Date().toLocaleString()

  const descriptiveHeader = () => {
    const conditionHeaders = conditionColumns
      .map((c) => `<th colspan="6">${escapeHtml(conditionLabel(c))}</th>`)
      .join('')
    const subHeaders = conditionColumns.map(() => '<th>n</th><th>M</th><th>SD</th><th>Median</th><th>Min</th><th>Max</th>').join('')
    return `<tr><th rowspan="2">指标</th>${conditionHeaders}</tr><tr>${subHeaders}</tr>`
  }

  const descriptiveRows = report.metrics.map((metric) => {
    const cells = conditionColumns.map((c) => {
      const s = statFor(metric, c)
      return `<td>${s?.n ?? 0}</td><td>${escapeHtml(formatNumber(s?.mean ?? null))}</td><td>${escapeHtml(formatNumber(s?.sd ?? null))}</td><td>${escapeHtml(formatNumber(s?.median ?? null))}</td><td>${escapeHtml(formatNumber(s?.min ?? null))}</td><td>${escapeHtml(formatNumber(s?.max ?? null))}</td>`
    }).join('')
    return `<tr><th>${escapeHtml(metric.label)}</th>${cells}</tr>`
  }).join('')

  const reliabilityRows = report.reliability.map((item) => {
    const alphaText = item.status === 'ok' && item.alpha !== null ? formatNumber(item.alpha) : item.status
    return `<tr><th>${escapeHtml(item.label)}</th><td>${item.n_items}</td><td>${item.n_obs}</td><td>${escapeHtml(alphaText)}</td><td>${escapeHtml(item.note)}</td></tr>`
  }).join('')

  const normalityRows = report.normality.map((item) => `
    <tr><th>${escapeHtml(item.label)}</th><td>${escapeHtml(conditionLabel(item.condition))}</td><td>${item.n}</td><td>${escapeHtml(formatNumber(item.statistic))}</td><td>${escapeHtml(pValueText(item.p_value))}</td><td>${escapeHtml(normalityStatusLabel(item))}</td><td>${escapeHtml(item.note)}</td></tr>
  `).join('')

  const inferentialRows = report.statistical_tests.map((item) => `
    <tr><th>${escapeHtml(item.label)}</th><td>${escapeHtml(testLabel(item.test))}</td><td>${escapeHtml(item.statistic_name || '—')}=${escapeHtml(formatNumber(item.statistic))}</td><td>${escapeHtml(pValueText(item.p_value))}</td><td>${item.effect_size_name ? `${escapeHtml(item.effect_size_name)}=${escapeHtml(formatNumber(item.effect_size))}` : '—'}</td><td>${escapeHtml(testStatusLabel(item.status))}</td><td>${escapeHtml(item.note)}</td></tr>
  `).join('')

  const postHocSection = report.post_hoc_tests.map((item) => {
    if (item.status !== 'ok' || item.pairs.length === 0) {
      return `<p class="note"><strong>${escapeHtml(item.label)}</strong>：${escapeHtml(item.note)}</p>`
    }
    const method = item.method === 'tukey_hsd' ? 'Tukey HSD' : 'Dunn + Bonferroni'
    const pairRows = item.pairs.map((p) => `
      <tr><td>${escapeHtml(conditionLabel(p.condition_a))}</td><td>${escapeHtml(conditionLabel(p.condition_b))}</td><td>${escapeHtml(formatNumber(p.mean_diff))}</td><td>${escapeHtml(pValueText(p.p_value_adjusted))}</td><td>${p.significant === true ? '*' : p.significant === false ? 'ns' : '—'}</td></tr>
    `).join('')
    return `<h3>${escapeHtml(item.label)}（${escapeHtml(method)}）</h3><table><thead><tr><th>条件 A</th><th>条件 B</th><th>均值差 (B−A)</th><th>p (校正后)</th><th>显著</th></tr></thead><tbody>${pairRows}</tbody></table>`
  }).join('')

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(scaleLabel(scale))} 统计分析报告</title>
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
  <h1>${escapeHtml(scaleLabel(scale))} 统计分析报告</h1>
  <div class="meta">生成时间：${escapeHtml(generatedAt)}</div>
  <div class="meta">分析模式：${escapeHtml(modeDescription(mode))}；量表：${escapeHtml(scale.toUpperCase())}；纳入记录数：${report.total_entries}</div>
  <h2>1. 描述性统计</h2>
  <table><thead>${descriptiveHeader()}</thead><tbody>${descriptiveRows}</tbody></table>
  <h2>2. 内部一致性（Cronbach's α）</h2>
  <p class="note">α ≥ 0.7 视为可接受的内部一致性。</p>
  <table><thead><tr><th>维度</th><th>题项数</th><th>n</th><th>α</th><th>说明</th></tr></thead><tbody>${reliabilityRows}</tbody></table>
  <h2>3. 正态性检查（Shapiro-Wilk）</h2>
  <table><thead><tr><th>指标</th><th>条件</th><th>n</th><th>W</th><th>p</th><th>判断</th><th>说明</th></tr></thead><tbody>${normalityRows}</tbody></table>
  <h2>4. 推断统计</h2>
  <table><thead><tr><th>指标</th><th>检验</th><th>统计量</th><th>p</th><th>Effect size</th><th>状态</th><th>说明</th></tr></thead><tbody>${inferentialRows}</tbody></table>
  <h2>5. 事后检验（Post-hoc）</h2>
  <p class="note">仅三条件且全局检验 p &lt; 0.05 时执行；Tukey HSD 用于 ANOVA，Dunn + Bonferroni 用于 Kruskal-Wallis。</p>
  ${postHocSection}
</body>
</html>`
}
