import type { PostHocResult, StatisticalTestResult } from '../../../api/admin/coi-analysis'
import type { CoiCompositionObservation } from '../../../api/admin/coi-composition-analysis'
import {
  academicConditionColor,
  academicConditionLabel,
  academicNiceMaximum,
  academicPValue,
  academicTicks,
} from '../task-score/academicChartStyle'

interface PublicationFigureInput {
  observations: CoiCompositionObservation[]
  conditions: string[]
  tests: StatisticalTestResult[]
  postHocTests: PostHocResult[]
}

const PHASES = [
  { key: 'te_ratio', short: 'TE', title: 'Triggering Event' },
  { key: 'ex_ratio', short: 'EX', title: 'Exploration' },
  { key: 'in_ratio', short: 'IN', title: 'Integration' },
  { key: 're_ratio', short: 'RE', title: 'Resolution' },
] as const

function escapeXml(value: unknown): string {
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

function boxStatistics(input: number[]) {
  const values = [...input].filter(Number.isFinite).sort((a, b) => a - b)
  if (!values.length) return { n: 0, q1: 0, median: 0, q3: 0, low: 0, high: 0 }
  const q1 = quantile(values, 0.25)
  const median = quantile(values, 0.5)
  const q3 = quantile(values, 0.75)
  const iqr = q3 - q1
  return {
    n: values.length,
    q1,
    median,
    q3,
    low: values.find(value => value >= q1 - 1.5 * iqr) ?? values[0] ?? 0,
    high: [...values].reverse().find(value => value <= q3 + 1.5 * iqr) ?? values[values.length - 1] ?? 0,
  }
}

function phasePanel(
  input: PublicationFigureInput,
  phase: typeof PHASES[number],
  panelIndex: number,
): string {
  const panelWidth = 480
  const panelHeight = 380
  const panelX = 14 + panelIndex * 496
  const panelY = 48
  const left = 66
  const right = 14
  const top = 94
  const bottom = 72
  const plotWidth = panelWidth - left - right
  const plotHeight = panelHeight - top - bottom
  const valuesByCondition = Object.fromEntries(input.conditions.map(condition => [
    condition,
    input.observations
      .filter(item => item.condition === condition)
      .map(item => Number(item[phase.key]))
      .filter(Number.isFinite),
  ]))
  const allValues = Object.values(valuesByCondition).flat()
  const maximum = academicNiceMaximum(Math.max(...allValues, 0) * 1.03)
  const y = (value: number) => top + plotHeight - Math.min(1, Math.max(0, value / maximum)) * plotHeight
  const conditionX = (condition: string) => {
    const index = input.conditions.indexOf(condition)
    return left + plotWidth * (index + 0.5) / input.conditions.length
  }
  const test = input.tests.find(item => item.metric === phase.key)
  const pValue = test?.p_value_adjusted
  const significant = pValue != null && pValue < 0.05

  const ticks = academicTicks(maximum).map(value => {
    const tickY = y(value)
    return `<line class="grid" x1="${left}" x2="${panelWidth - right}" y1="${tickY}" y2="${tickY}"/><text class="tick" x="${left - 8}" y="${tickY + 5}" text-anchor="end">${Math.round(value * 100)}%</text>`
  }).join('')

  const boxes = input.conditions.map(condition => {
    const stats = boxStatistics(valuesByCondition[condition] ?? [])
    const x = conditionX(condition)
    const color = academicConditionColor(condition)
    if (!stats.n) return `<text class="condition" x="${x}" y="${top + plotHeight + 28}" text-anchor="middle">${escapeXml(academicConditionLabel(condition))}</text>`
    return `
      <line class="whisker" x1="${x}" x2="${x}" y1="${y(stats.high)}" y2="${y(stats.low)}" stroke="${color}"/>
      <line class="whisker" x1="${x - 18}" x2="${x + 18}" y1="${y(stats.high)}" y2="${y(stats.high)}" stroke="${color}"/>
      <line class="whisker" x1="${x - 18}" x2="${x + 18}" y1="${y(stats.low)}" y2="${y(stats.low)}" stroke="${color}"/>
      <rect class="box" x="${x - 35}" y="${y(stats.q3)}" width="70" height="${Math.max(2, y(stats.q1) - y(stats.q3))}" fill="${color}24" stroke="${color}"/>
      <line class="median" x1="${x - 35}" x2="${x + 35}" y1="${y(stats.median)}" y2="${y(stats.median)}" stroke="${color}"/>
      <text class="median-label" x="${x}" y="${y(stats.median) - 6}" text-anchor="middle">${(stats.median * 100).toFixed(1)}%</text>
      <text class="condition" x="${x}" y="${top + plotHeight + 28}" text-anchor="middle">${escapeXml(academicConditionLabel(condition))}</text>`
  }).join('')

  const significantPairs = input.postHocTests
    .find(item => item.metric === phase.key)?.pairs
    .filter(pair => pair.significant && pair.p_value_adjusted != null) ?? []
  const brackets = significantPairs.slice(0, 2).map((pair, index) => {
    const x1 = conditionX(pair.condition_a)
    const x2 = conditionX(pair.condition_b)
    const bracketY = 73 - index * 18
    return `<path class="sig-bracket" d="M ${x1} ${bracketY + 8} V ${bracketY} H ${x2} V ${bracketY + 8}"/><text class="sig-text" x="${(x1 + x2) / 2}" y="${bracketY - 5}" text-anchor="middle">${escapeXml(academicPValue(pair.p_value_adjusted))}*</text>`
  }).join('')

  return `<g transform="translate(${panelX} ${panelY})">
    <rect class="panel" width="${panelWidth}" height="${panelHeight}" rx="8"/>
    <text class="panel-title" x="18" y="29">(${String.fromCharCode(97 + panelIndex)}) ${phase.short} · ${phase.title}</text>
    <text class="panel-p${significant ? ' significant' : ''}" x="${panelWidth - 16}" y="29" text-anchor="end">All conditions: ${escapeXml(academicPValue(pValue))}${significant ? '*' : ''}</text>
    ${brackets}${ticks}
    <line class="axis" x1="${left}" x2="${left}" y1="${top}" y2="${top + plotHeight}"/>
    <line class="axis" x1="${left}" x2="${panelWidth - right}" y1="${top + plotHeight}" y2="${top + plotHeight}"/>
    <text class="axis-label" x="18" y="${top + plotHeight / 2}" transform="rotate(-90 18 ${top + plotHeight / 2})" text-anchor="middle">Proportion (%)</text>
    ${boxes}
  </g>`
}

export function buildCoiCompositionPublicationSvg(input: PublicationFigureInput): string {
  const panels = PHASES.map((phase, index) => phasePanel(input, phase, index)).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2000 468" role="img" aria-label="CoI phase proportions by experimental condition with p values">
    <defs><style>
      text{font-family:Arial,Helvetica,sans-serif;text-rendering:geometricPrecision}.figure-title{fill:#0f172a;font-size:22px;font-weight:800}.figure-note{fill:#64748b;font-size:13px;font-weight:650}.panel{fill:#fff;stroke:#cbd5e1;stroke-width:1.2}.panel-title{fill:#0f172a;font-size:16px;font-weight:800}.panel-p{fill:#475569;font-size:13px;font-weight:750}.panel-p.significant,.sig-text{fill:#c81e1e;font-weight:850}.sig-text{font-size:13px}.sig-bracket{fill:none;stroke:#c81e1e;stroke-width:2}.grid{stroke:#e5eaf0;stroke-width:1;stroke-dasharray:3 3}.tick{fill:#475569;font-size:11px;font-weight:600}.axis{stroke:#64748b;stroke-width:1.4}.axis-label{fill:#334155;font-size:11px;font-weight:700}.condition{fill:#1e293b;font-size:12px;font-weight:700}.whisker{stroke-width:1.8}.box{stroke-width:2}.median{stroke-width:2.6}.median-label{fill:#172033;font-size:11px;font-weight:800;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}
    </style></defs>
    <rect width="2000" height="468" fill="#fff"/>
    <text class="figure-title" x="20" y="31">CoI Phase Proportions by Experimental Condition</text>
    <text class="figure-note" x="1980" y="31" text-anchor="end"><tspan fill="#c81e1e">Red</tspan> indicates p &lt; .05</text>
    ${panels}
    <text class="figure-note" x="1000" y="456" text-anchor="middle">Box = middle 50% · horizontal line and label = median · whiskers = values within 1.5 IQR</text>
  </svg>`
}
