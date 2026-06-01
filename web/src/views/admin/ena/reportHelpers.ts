import type {
  EnaAnalysisMode,
  EnaMetricSummary,
  EnaNormalityResult,
  EnaStatTestResult,
  EnaPostHocResult,
  EnaAnalysisResult,
  EnaNetworkCondition,
} from '../../../api/admin/ena-analysis'

export const CONDITION_LABELS: Record<string, string> = {
  no_assistance: '无辅助',
  glasses: '智能眼镜',
  app_notification: 'APP 通知',
}

export function conditionLabel(condition: string): string {
  return CONDITION_LABELS[condition] ?? condition
}

export function modeDescription(mode: EnaAnalysisMode): string {
  return mode === 'two_conditions'
    ? 'no_assistance vs glasses'
    : 'no_assistance / glasses / app_notification'
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

export function pValueText(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value < 0.001) return '< .001'
  return formatNumber(value)
}

export function statFor(metric: EnaMetricSummary, condition: string) {
  return metric.conditions.find((c) => c.condition === condition)
}

export function meanDiffText(metric: EnaMetricSummary): string {
  const base = statFor(metric, 'no_assistance')
  const comp = statFor(metric, 'glasses')
  if (!base?.n || !comp?.n || base.mean === null || comp.mean === null) return '—'
  const diff = comp.mean - base.mean
  return `${diff > 0 ? '+' : ''}${formatNumber(diff)}`
}

export function normalityStatusLabel(item: EnaNormalityResult): string {
  if (item.status === 'ok') return item.is_normal ? '近似正态' : '偏离正态'
  if (item.status === 'insufficient_n') return '样本不足'
  if (item.status === 'constant_values') return '数值恒定'
  return '缺少依赖'
}

export function normalityTagType(item: EnaNormalityResult): 'success' | 'warning' | 'info' | 'danger' {
  if (item.status === 'ok') return item.is_normal ? 'success' : 'warning'
  if (item.status === 'dependency_missing') return 'danger'
  return 'info'
}

export function testLabel(test: EnaStatTestResult['test']): string {
  const labels: Record<EnaStatTestResult['test'], string> = {
    independent_samples_t_test: 'Independent-samples t-test',
    mann_whitney_u: 'Mann-Whitney U',
    one_way_anova: 'One-way ANOVA',
    kruskal_wallis: 'Kruskal-Wallis',
    insufficient_data: '样本不足',
  }
  return labels[test]
}

export function testStatusLabel(status: EnaStatTestResult['status']): string {
  const labels: Record<EnaStatTestResult['status'], string> = {
    ok: '已计算',
    insufficient_data: '样本不足',
    dependency_missing: '缺少依赖',
    calculation_error: '无法计算',
  }
  return labels[status]
}

export function postHocMethodLabel(method: EnaPostHocResult['method']): string {
  if (method === 'tukey_hsd') return 'Tukey HSD'
  if (method === 'dunn_bonferroni') return 'Dunn + Bonferroni'
  return '—'
}

export function postHocStatusLabel(status: EnaPostHocResult['status']): string {
  const labels: Record<EnaPostHocResult['status'], string> = {
    ok: '已计算',
    not_applicable: '不适用',
    insufficient_data: '样本不足',
    dependency_missing: '缺少依赖',
    calculation_error: '无法计算',
  }
  return labels[status]
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  TE: { x: 150, y: 42 },
  EX: { x: 42, y: 160 },
  IN: { x: 258, y: 160 },
  RE: { x: 150, y: 278 },
}

const NODE_COLORS: Record<string, string> = {
  TE: '#f59e0b',
  EX: '#3b82f6',
  IN: '#8b5cf6',
  RE: '#10b981',
}

const NODE_LABELS: Record<string, string> = {
  TE: '触发事件',
  EX: '探索',
  IN: '整合',
  RE: '解决',
}

function edgeStroke(weight: number, maxWeight: number): number {
  if (maxWeight <= 0) return 0.5
  return Math.max(0.5, (weight / maxWeight) * 16)
}

function diffColor(diff: number): string {
  if (diff > 0.01) return '#2563eb'
  if (diff < -0.01) return '#dc2626'
  return '#d1d5db'
}

function networkSvg(net: EnaNetworkCondition, isDiff = false): string {
  const weights = net.edges.map((edge) => Math.abs(isDiff ? (edge.weight_diff ?? 0) : edge.weight))
  const maxWeight = Math.max(...weights, 0.001)
  const edges = net.edges.map((edge) => {
    const source = NODE_POSITIONS[edge.source] ?? { x: 150, y: 160 }
    const target = NODE_POSITIONS[edge.target] ?? { x: 150, y: 160 }
    const weight = isDiff ? Math.abs(edge.weight_diff ?? 0) : edge.weight
    const color = isDiff ? diffColor(edge.weight_diff ?? 0) : weight < 0.01 ? '#e5e7eb' : '#6b7280'
    const label = isDiff
      ? `${(edge.weight_diff ?? 0) > 0 ? '+' : ''}${formatNumber(edge.weight_diff ?? 0)}`
      : formatNumber(edge.weight)
    const showLabel = isDiff ? Math.abs(edge.weight_diff ?? 0) >= 0.05 : edge.weight >= 0.05
    return `
      <line x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" stroke="${color}" stroke-width="${edgeStroke(weight, maxWeight)}" stroke-linecap="round" opacity="0.85" />
      ${showLabel ? `<text x="${(source.x + target.x) / 2}" y="${(source.y + target.y) / 2 - 4}" text-anchor="middle" class="edge-label">${escapeHtml(label)}</text>` : ''}
    `
  }).join('')
  const nodes = net.nodes.map((node) => {
    const pos = NODE_POSITIONS[node] ?? { x: 150, y: 160 }
    const color = NODE_COLORS[node] ?? '#64748b'
    return `
      <g>
        <circle cx="${pos.x}" cy="${pos.y}" r="28" fill="${color}" fill-opacity="0.15" stroke="${color}" stroke-width="2" />
        <text x="${pos.x}" y="${pos.y - 5}" text-anchor="middle" class="node-code" fill="${color}">${escapeHtml(node)}</text>
        <text x="${pos.x}" y="${pos.y + 10}" text-anchor="middle" class="node-label">${escapeHtml(NODE_LABELS[node] ?? node)}</text>
      </g>
    `
  }).join('')
  const title = isDiff ? '差异图（条件B − 条件A）' : conditionLabel(net.condition)
  return `
    <div class="network-card">
      <h3>${escapeHtml(title)}</h3>
      <svg class="network-svg" viewBox="0 0 300 320" role="img" aria-label="${escapeHtml(title)}">
        ${edges}
        ${nodes}
      </svg>
    </div>
  `
}

function enaNetworkChartsHtml(report: EnaAnalysisResult): string {
  const conditionNetworks = report.networks.map((net) => networkSvg(net)).join('')
  const diffNetwork = report.diff_network ? networkSvg(report.diff_network, true) : ''
  const diffLegend = report.diff_network
    ? '<p class="note">差异图中蓝色表示条件 B 连接更强，红色表示条件 A 连接更强，灰色表示差异小于 0.01。</p>'
    : '<p class="note">三条件主报告展示各条件网络图；不生成两两差异网络图。</p>'
  return `
    <div class="network-grid">
      ${conditionNetworks}
      ${diffNetwork}
    </div>
    ${diffLegend}
  `
}

export function buildEnaReportHtml(
  report: EnaAnalysisResult,
  mode: EnaAnalysisMode,
  conditionColumns: string[],
): string {
  const generatedAt = new Date().toLocaleString()

  const descriptiveHeader = () => {
    const cols = conditionColumns.map((c) => `<th colspan="6">${escapeHtml(conditionLabel(c))}</th>`).join('')
    const sub = conditionColumns.map(() => '<th>n</th><th>M</th><th>SD</th><th>Med</th><th>Min</th><th>Max</th>').join('')
    return `<tr><th rowspan="2">指标</th>${cols}${mode === 'two_conditions' ? '<th rowspan="2">均值差</th>' : ''}</tr><tr>${sub}</tr>`
  }

  const descriptiveRows = report.metrics.map((m) => {
    const cells = conditionColumns.map((c) => {
      const s = statFor(m, c)
      return `<td>${s?.n ?? 0}</td><td>${escapeHtml(formatNumber(s?.mean))}</td><td>${escapeHtml(formatNumber(s?.sd))}</td><td>${escapeHtml(formatNumber(s?.median))}</td><td>${escapeHtml(formatNumber(s?.min))}</td><td>${escapeHtml(formatNumber(s?.max))}</td>`
    }).join('')
    return `<tr><th>${escapeHtml(m.label)}</th>${cells}${mode === 'two_conditions' ? `<td>${escapeHtml(meanDiffText(m))}</td>` : ''}</tr>`
  }).join('')

  const normalityRows = report.normality.map((item) =>
    `<tr><th>${escapeHtml(item.label)}</th><td>${escapeHtml(conditionLabel(item.condition))}</td><td>${item.n}</td><td>${escapeHtml(formatNumber(item.statistic))}</td><td>${escapeHtml(pValueText(item.p_value))}</td><td>${escapeHtml(normalityStatusLabel(item))}</td><td>${escapeHtml(item.note)}</td></tr>`,
  ).join('')

  const inferentialRows = report.statistical_tests.map((item) =>
    `<tr><th>${escapeHtml(item.label)}</th><td>${escapeHtml(testLabel(item.test))}</td><td>${escapeHtml(item.statistic_name ?? '—')}=${escapeHtml(formatNumber(item.statistic))}</td><td>${escapeHtml(pValueText(item.p_value))}</td><td>${escapeHtml(item.effect_size_name ?? '—')}=${escapeHtml(formatNumber(item.effect_size))}</td><td>${escapeHtml(testStatusLabel(item.status))}</td><td>${escapeHtml(item.note)}</td></tr>`,
  ).join('')

  const postHocSection = report.post_hoc_tests.map((item) => {
    if (item.status !== 'ok' || item.pairs.length === 0) {
      return `<p class="note"><strong>${escapeHtml(item.label)}</strong>：${escapeHtml(item.note)}</p>`
    }
    const pairRows = item.pairs.map((pair) =>
      `<tr><td>${escapeHtml(conditionLabel(pair.condition_a))}</td><td>${escapeHtml(conditionLabel(pair.condition_b))}</td><td>${escapeHtml(formatNumber(pair.mean_diff))}</td><td>${escapeHtml(pValueText(pair.p_value_adjusted))}</td><td>${pair.significant === true ? '*' : pair.significant === false ? 'ns' : '—'}</td></tr>`,
    ).join('')
    return `<h3>${escapeHtml(item.label)}（${escapeHtml(postHocMethodLabel(item.method))}）</h3><table><thead><tr><th>条件 A</th><th>条件 B</th><th>均值差 (B−A)</th><th>p (校正后)</th><th>显著</th></tr></thead><tbody>${pairRows}</tbody></table>`
  }).join('')

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>ENA 认知过程网络分析报告</title>
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
    .network-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 10px 0 18px; }
    .network-card { padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; background: #f8fafc; page-break-inside: avoid; }
    .network-card h3 { margin-top: 0; }
    .network-svg { display: block; width: 100%; height: auto; }
    .edge-label { fill: #374151; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 9px; }
    .node-code { font-size: 12px; font-weight: 700; }
    .node-label { fill: #6b7280; font-size: 9px; }
    @media (max-width: 900px) { .network-grid { grid-template-columns: 1fr; } }
    @media print { body { margin: 18mm; } h2 { page-break-after: avoid; } }
  </style>
</head>
<body>
  <h1>ENA 认知过程网络分析报告</h1>
  <div class="meta">生成时间：${escapeHtml(generatedAt)}</div>
  <div class="meta">分析模式：${escapeHtml(modeDescription(mode))}；纳入会话数：${report.total_sessions}</div>
  <p class="note">基于 CoI 编码结果，使用 2 分钟滑动时间窗口（步长 30s）计算话语类别共现强度，重点分析 EX-IN、IN-RE 及高阶认知连接。</p>
  <h2>1. 描述性统计</h2>
  <table><thead>${descriptiveHeader()}</thead><tbody>${descriptiveRows}</tbody></table>
  <h2>2. 正态性检查（Shapiro-Wilk）</h2>
  <table><thead><tr><th>指标</th><th>条件</th><th>n</th><th>W</th><th>p</th><th>判断</th><th>说明</th></tr></thead><tbody>${normalityRows}</tbody></table>
  <h2>3. 报告结果与可视化</h2>
  <p class="note">网络图展示 CoI 阶段之间的共现连接强度；p 值与 effect size 见下方推断统计表。</p>
  ${report.charts?.networks ? `<img src="${report.charts.networks}" style="max-width:100%;display:block;margin:10px 0 18px;border-radius:6px" alt="ENA 网络图">` : enaNetworkChartsHtml(report)}
  <h2>4. 推断统计</h2>
  <table><thead><tr><th>指标</th><th>检验</th><th>统计量</th><th>p</th><th>Effect size</th><th>状态</th><th>说明</th></tr></thead><tbody>${inferentialRows}</tbody></table>
  <h2>5. 事后检验（Post-hoc）</h2>
  <p class="note">仅三条件且全局检验 p &lt; 0.05 时执行。</p>
  ${postHocSection}
</body>
</html>`
}
