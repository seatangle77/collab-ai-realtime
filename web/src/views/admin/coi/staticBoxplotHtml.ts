import { academicConditionColor, academicNiceMaximum, academicTicks } from '../task-score/academicChartStyle'

export const STATIC_BOXPLOT_CSS = `
.boxplot-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.boxplot-grid .wide{grid-column:1/-1}.report-boxplot{min-width:0;padding:12px 14px 8px;border:1px solid #d3dbe5;border-radius:8px}.report-boxplot h3{display:flex;flex-direction:column;margin:0 0 4px;font-size:16px}.report-boxplot h3 span{color:#526071;font-size:13px;font-weight:550}.report-boxplot svg{display:block;width:100%;height:auto}.report-boxplot .grid{stroke:#dce3eb;stroke-width:1.2;stroke-dasharray:3 3}.report-boxplot .axis{stroke:#64748b;stroke-width:1.6}.report-boxplot .tick,.report-boxplot .label,.report-boxplot .unit{fill:#334155;font-size:14px;font-weight:650}.report-boxplot .label{fill:#0f172a;font-size:15px;font-weight:750}.report-boxplot .sample{fill:#64748b;font-size:12px;font-weight:600}.report-boxplot .legend{display:flex;justify-content:center;gap:16px;flex-wrap:wrap;color:#475569;font-size:12px;font-weight:600}.report-boxplot .legend span{display:flex;align-items:center;gap:4px}.report-boxplot .box-key{width:11px;height:7px;border:1.5px solid #374151;background:#3741512b}.report-boxplot .point-key{width:4px;height:4px;border:1.25px solid #374151;border-radius:50%}.report-boxplot .mean-key{width:13px;border-top:2px solid #374151}@media(max-width:760px){.boxplot-grid{grid-template-columns:1fr}.boxplot-grid .wide{grid-column:auto}}@media print{.report-boxplot{border-color:#777}.report-boxplot svg{filter:grayscale(1) contrast(1.35)}}
`

interface StaticBoxplotOptions {
  title: string
  subtitle: string
  conditions: string[]
  valuesByCondition: Record<string, number[]>
  conditionLabels: Record<string, string>
  maximum?: number
  percent?: boolean
  unitLabel: string
  language: 'zh' | 'en'
  wide?: boolean
  panelLabel?: string
  statisticLabel?: string
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function quantile(values: number[], percentile: number): number {
  if (!values.length) return 0
  const index = (values.length - 1) * percentile
  const lower = Math.floor(index)
  const remainder = index - lower
  const low = values[lower] ?? 0
  const high = values[lower + 1] ?? low
  return low + (high - low) * remainder
}

function tCritical95(df: number): number {
  const values = [0, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]
  return values[Math.min(30, Math.max(1, df))] ?? 1.96
}

function statistics(input: number[]) {
  const values = [...input].filter(Number.isFinite).sort((a, b) => a - b)
  if (!values.length) return { n: 0, q1: 0, median: 0, q3: 0, low: 0, high: 0, mean: 0, ciLow: 0, ciHigh: 0 }
  const q1 = quantile(values, 0.25)
  const median = quantile(values, 0.5)
  const q3 = quantile(values, 0.75)
  const iqr = q3 - q1
  const low = values.find(value => value >= q1 - 1.5 * iqr) ?? values[0] ?? 0
  const high = [...values].reverse().find(value => value <= q3 + 1.5 * iqr) ?? values[values.length - 1] ?? 0
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length
  const variance = values.length > 1 ? values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1) : 0
  const margin = values.length > 1 ? tCritical95(values.length - 1) * Math.sqrt(variance / values.length) : 0
  return { n: values.length, q1, median, q3, low, high, mean, ciLow: mean - margin, ciHigh: mean + margin }
}

export function staticSessionBoxplotHtml(options: StaticBoxplotOptions): string {
  const width = 760
  const height = 452
  const left = 88
  const right = 24
  const top = 72
  const bottom = 96
  const plotWidth = width - left - right
  const plotHeight = height - top - bottom
  const allValues = options.conditions.flatMap(condition => options.valuesByCondition[condition] ?? [])
  const maximum = options.maximum ?? academicNiceMaximum(Math.max(...allValues, 0) * 1.03)
  const y = (value: number) => top + plotHeight - Math.min(1, Math.max(0, value / maximum)) * plotHeight
  const format = (value: number) => options.percent ? `${(value * 100).toFixed(0)}%` : value.toFixed(maximum <= 2 ? 2 : 1)
  const jitter = [-24, -16, -8, 0, 8, 16, 24, -20, -12, -4, 4, 12, 20]

  const ticks = academicTicks(maximum).map(value => {
    const tickY = y(value)
    return `<line class="grid" x1="${left}" x2="${width - right}" y1="${tickY}" y2="${tickY}"/><text class="tick" x="${left - 9}" y="${tickY + 4}" text-anchor="end">${format(value)}</text>`
  }).join('')

  const groups = options.conditions.map((condition, groupIndex) => {
    const values = (options.valuesByCondition[condition] ?? []).filter(Number.isFinite)
    const stats = statistics(values)
    const x = left + plotWidth * (groupIndex + 0.5) / options.conditions.length
    const color = academicConditionColor(condition)
    const label = options.conditionLabels[condition] ?? condition
    const points = values.map((value, index) => {
      const pointX = x + (jitter[index % jitter.length] ?? 0)
      const title = `<title>${escapeHtml(label)} · ${format(value)}</title>`
      return `<circle cx="${pointX}" cy="${y(value)}" r="2.4" fill="${color}" fill-opacity=".82">${title}</circle>`
    }).join('')
    const marks = stats.n ? `
      <line x1="${x}" x2="${x}" y1="${y(stats.high)}" y2="${y(stats.low)}" stroke="${color}" stroke-width="1.6"/>
      <line x1="${x - 17}" x2="${x + 17}" y1="${y(stats.high)}" y2="${y(stats.high)}" stroke="${color}" stroke-width="1.6"/>
      <line x1="${x - 17}" x2="${x + 17}" y1="${y(stats.low)}" y2="${y(stats.low)}" stroke="${color}" stroke-width="1.6"/>
      <rect x="${x - 31}" y="${y(stats.q3)}" width="62" height="${Math.max(2, y(stats.q1) - y(stats.q3))}" fill="${color}20" stroke="${color}" stroke-width="2"/>
      <line x1="${x - 31}" x2="${x + 31}" y1="${y(stats.median)}" y2="${y(stats.median)}" stroke="${color}" stroke-width="2.5"/>
      <line x1="${x + 43}" x2="${x + 43}" y1="${y(stats.ciHigh)}" y2="${y(stats.ciLow)}" stroke="${color}" stroke-width="2"/>
      <line x1="${x + 37}" x2="${x + 49}" y1="${y(stats.ciHigh)}" y2="${y(stats.ciHigh)}" stroke="${color}" stroke-width="2"/>
      <line x1="${x + 37}" x2="${x + 49}" y1="${y(stats.ciLow)}" y2="${y(stats.ciLow)}" stroke="${color}" stroke-width="2"/>
      <polygon points="${x + 43},${y(stats.mean) - 5} ${x + 48},${y(stats.mean)} ${x + 43},${y(stats.mean) + 5} ${x + 38},${y(stats.mean)}" fill="${color}" stroke="#fff"/>
      ${points}` : ''
    const mean = options.percent ? `${(stats.mean * 100).toFixed(1)}%` : stats.mean.toFixed(maximum <= 2 ? 2 : 1)
    return `${marks}<text class="label" x="${x}" y="${top + plotHeight + 26}" text-anchor="middle">${escapeHtml(label)}</text><text class="sample" x="${x}" y="${top + plotHeight + 46}" text-anchor="middle">n=${stats.n} · M=${mean}</text>`
  }).join('')

  const legend = options.language === 'zh'
    ? '<span><i class="box-key"></i>中位数与四分位区间</span><span><i class="point-key"></i>每场会话</span><span><i class="mean-key"></i>均值及95% CI</span>'
    : '<span><i class="box-key"></i>Median and IQR</span><span><i class="point-key"></i>Session</span><span><i class="mean-key"></i>Mean and 95% CI</span>'

  return `<section class="report-boxplot${options.wide ? ' wide' : ''}"><h3>${escapeHtml(options.title)}<span>${escapeHtml(options.subtitle)}</span></h3><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(options.title)}"><defs><style>text{font-family:Arial,Helvetica,sans-serif;text-rendering:geometricPrecision}.grid{stroke:#dce3eb;stroke-width:1.2;stroke-dasharray:3 3}.axis{stroke:#64748b;stroke-width:1.6}.tick{fill:#334155;font-size:14px;font-weight:650}.label{fill:#0f172a;font-size:15px;font-weight:750}.sample{fill:#64748b;font-size:12px;font-weight:600}.panel-title{fill:#0f172a;font-size:17px;font-weight:800}.panel-subtitle{fill:#526071;font-size:12px;font-weight:600}.statistic{fill:#334155;font-size:12px;font-weight:700}.axis-label{fill:#1e293b;font-size:14px;font-weight:750}</style></defs><text class="panel-title" x="18" y="25">${escapeHtml(options.panelLabel ? `${options.panelLabel}  ${options.title}` : options.title)}</text><text class="panel-subtitle" x="18" y="46">${escapeHtml(options.subtitle)}</text>${options.statisticLabel ? `<text class="statistic" x="${width - right}" y="25" text-anchor="end">${escapeHtml(options.statisticLabel)}</text>` : ''}${ticks}<line class="axis" x1="${left}" x2="${left}" y1="${top}" y2="${top + plotHeight}"/><line class="axis" x1="${left}" x2="${width - right}" y1="${top + plotHeight}" y2="${top + plotHeight}"/><text class="axis-label" x="22" y="${top + plotHeight / 2}" transform="rotate(-90 22 ${top + plotHeight / 2})" text-anchor="middle">${escapeHtml(options.unitLabel)}</text>${groups}<text class="axis-label" x="${left + plotWidth / 2}" y="${height - 12}" text-anchor="middle">Experimental Condition</text></svg><div class="legend">${legend}</div></section>`
}
