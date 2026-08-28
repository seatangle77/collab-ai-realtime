<script setup lang="ts">
import { computed, ref } from 'vue'
import { Download, ZoomIn } from '@element-plus/icons-vue'
import { downloadSvgElement, serializeSvgElement } from '../task-score/analysisExport'
import { academicConditionColor, academicConditionLabel, academicNiceMaximum, academicTicks } from '../task-score/academicChartStyle'

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  conditions: string[]
  valuesByCondition: Record<string, number[]>
  maximum?: number
  percent?: boolean
  unitLabel?: string
  panelLabel?: string
  statisticLabel?: string
  showPoints?: boolean
}>(), {
  subtitle: '',
  maximum: undefined,
  percent: false,
  unitLabel: '',
  panelLabel: '',
  statisticLabel: '',
  showPoints: true,
})
const svgRef = ref<SVGElement | null>(null)
const previewVisible = ref(false)
const previewMarkup = ref('')
const conditionLabelEn = academicConditionLabel
const fileStem = computed(() => props.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'coi-boxplot')

const WIDTH = 760
const HEIGHT = 452
const LEFT = 88
const RIGHT = 24
const TOP = 72
const BOTTOM = 96
const PLOT_WIDTH = WIDTH - LEFT - RIGHT
const PLOT_HEIGHT = HEIGHT - TOP - BOTTOM
const BOX_WIDTH = 62

const jitterPattern = [-24, -16, -8, 0, 8, 16, 24, -20, -12, -4, 4, 12, 20]

function color(condition: string): string {
  return academicConditionColor(condition)
}

function quantile(values: number[], percentile: number): number {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const index = (sorted.length - 1) * percentile
  const lower = Math.floor(index)
  const remainder = index - lower
  const low = sorted[lower] ?? 0
  const high = sorted[lower + 1] ?? low
  return low + (high - low) * remainder
}

function tCritical95(df: number): number {
  const values = [0, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]
  return values[Math.min(30, Math.max(1, df))] ?? 1.96
}

function statistics(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b)
  if (!sorted.length) return { n: 0, q1: 0, median: 0, q3: 0, whiskerLow: 0, whiskerHigh: 0, mean: 0, ciLow: 0, ciHigh: 0 }
  const q1 = quantile(sorted, 0.25)
  const median = quantile(sorted, 0.5)
  const q3 = quantile(sorted, 0.75)
  const iqr = q3 - q1
  const lowFence = q1 - 1.5 * iqr
  const highFence = q3 + 1.5 * iqr
  const whiskerLow = sorted.find(value => value >= lowFence) ?? sorted[0] ?? 0
  const whiskerHigh = [...sorted].reverse().find(value => value <= highFence) ?? sorted[sorted.length - 1] ?? 0
  const mean = sorted.reduce((sum, value) => sum + value, 0) / sorted.length
  const variance = sorted.length > 1
    ? sorted.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (sorted.length - 1)
    : 0
  const margin = sorted.length > 1 ? tCritical95(sorted.length - 1) * Math.sqrt(variance) / Math.sqrt(sorted.length) : 0
  return { n: sorted.length, q1, median, q3, whiskerLow, whiskerHigh, mean, ciLow: mean - margin, ciHigh: mean + margin }
}

const allValues = computed(() => props.conditions.flatMap(condition => props.valuesByCondition[condition] ?? []).filter(Number.isFinite))
const domainMaximum = computed(() => props.maximum ?? academicNiceMaximum(Math.max(...allValues.value, 0) * 1.03))
const groups = computed(() => props.conditions.map((condition, index) => ({
  condition,
  color: color(condition),
  x: LEFT + PLOT_WIDTH * (index + 0.5) / props.conditions.length,
  values: props.valuesByCondition[condition] ?? [],
  stats: statistics(props.valuesByCondition[condition] ?? []),
})))
const ticks = computed(() => academicTicks(domainMaximum.value).map(value => ({
  value,
  y: TOP + PLOT_HEIGHT - PLOT_HEIGHT * value / domainMaximum.value,
})))

function y(value: number): number {
  return TOP + PLOT_HEIGHT - Math.min(1, Math.max(0, value / domainMaximum.value)) * PLOT_HEIGHT
}

function format(value: number): string {
  return props.percent ? `${(value * 100).toFixed(0)}%` : value.toFixed(domainMaximum.value <= 2 ? 2 : 1)
}

function meanLabel(value: number): string {
  return props.percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(domainMaximum.value <= 2 ? 2 : 1)
}

function pointX(groupX: number, index: number): number {
  return groupX + (jitterPattern[index % jitterPattern.length] ?? 0)
}

function openPreview() {
  if (!svgRef.value) return
  previewMarkup.value = serializeSvgElement(svgRef.value)
  previewVisible.value = true
}

function downloadChart() {
  if (svgRef.value) downloadSvgElement(svgRef.value, `${fileStem.value}.svg`)
}
</script>

<template>
  <section class="boxplot-panel">
    <header><div><strong>{{ title }}</strong><span v-if="subtitle">{{ subtitle }}</span></div><div class="chart-actions"><el-tooltip content="Enlarge chart"><el-button :icon="ZoomIn" circle size="small" @click="openPreview" /></el-tooltip><el-tooltip content="Download SVG"><el-button :icon="Download" circle size="small" @click="downloadChart" /></el-tooltip></div></header>
    <svg ref="svgRef" :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" role="img" :aria-label="`${title}: box plots, session observations, means, and 95% confidence intervals`" @click="openPreview">
      <text x="18" y="25" class="panel-title">{{ panelLabel ? `${panelLabel}  ` : '' }}{{ title }}</text>
      <text v-if="subtitle" x="18" y="46" class="panel-subtitle">{{ subtitle }}</text>
      <text v-if="statisticLabel" :x="WIDTH - RIGHT" y="25" text-anchor="end" class="statistic-label">{{ statisticLabel }}</text>
      <g class="grid">
        <template v-for="tick in ticks" :key="tick.value">
          <line :x1="LEFT" :x2="WIDTH - RIGHT" :y1="tick.y" :y2="tick.y" />
          <text :x="LEFT - 9" :y="tick.y + 4" text-anchor="end">{{ format(tick.value) }}</text>
        </template>
      </g>
      <line class="axis-line" :x1="LEFT" :x2="LEFT" :y1="TOP" :y2="TOP + PLOT_HEIGHT" />
      <line class="axis-line" :x1="LEFT" :x2="WIDTH - RIGHT" :y1="TOP + PLOT_HEIGHT" :y2="TOP + PLOT_HEIGHT" />
      <text v-if="unitLabel" class="axis-label" x="22" :y="TOP + PLOT_HEIGHT / 2" :transform="`rotate(-90 22 ${TOP + PLOT_HEIGHT / 2})`" text-anchor="middle">{{ unitLabel }}</text>

      <g v-for="group in groups" :key="group.condition">
        <template v-if="group.stats.n">
          <line class="whisker" :stroke="group.color" :x1="group.x" :x2="group.x" :y1="y(group.stats.whiskerHigh)" :y2="y(group.stats.whiskerLow)" />
          <line class="whisker-cap" :stroke="group.color" :x1="group.x - 17" :x2="group.x + 17" :y1="y(group.stats.whiskerHigh)" :y2="y(group.stats.whiskerHigh)" />
          <line class="whisker-cap" :stroke="group.color" :x1="group.x - 17" :x2="group.x + 17" :y1="y(group.stats.whiskerLow)" :y2="y(group.stats.whiskerLow)" />
          <rect
            class="box"
            :x="group.x - BOX_WIDTH / 2"
            :y="y(group.stats.q3)"
            :width="BOX_WIDTH"
            :height="Math.max(2, y(group.stats.q1) - y(group.stats.q3))"
            :stroke="group.color"
            :fill="`${group.color}38`"
            :data-condition="group.condition"
          />
          <line class="median" :stroke="group.color" :x1="group.x - BOX_WIDTH / 2" :x2="group.x + BOX_WIDTH / 2" :y1="y(group.stats.median)" :y2="y(group.stats.median)" />
          <line class="ci" :stroke="group.color" :x1="group.x + 43" :x2="group.x + 43" :y1="y(group.stats.ciHigh)" :y2="y(group.stats.ciLow)" />
          <line class="ci-cap" :stroke="group.color" :x1="group.x + 37" :x2="group.x + 49" :y1="y(group.stats.ciHigh)" :y2="y(group.stats.ciHigh)" />
          <line class="ci-cap" :stroke="group.color" :x1="group.x + 37" :x2="group.x + 49" :y1="y(group.stats.ciLow)" :y2="y(group.stats.ciLow)" />
          <polygon
            class="mean"
            :fill="group.color"
            :points="`${group.x + 43},${y(group.stats.mean) - 5} ${group.x + 48},${y(group.stats.mean)} ${group.x + 43},${y(group.stats.mean) + 5} ${group.x + 38},${y(group.stats.mean)}`"
          />
          <circle
            v-if="showPoints"
            v-for="(value, index) in group.values"
            :key="`${group.condition}-${index}`"
            class="raw-point"
            :cx="pointX(group.x, index)"
            :cy="y(value)"
            r="2.4"
            :fill="group.color"
          ><title>{{ conditionLabelEn(group.condition) }} · {{ format(value) }}</title></circle>
        </template>
        <text class="condition-label" :x="group.x" :y="TOP + PLOT_HEIGHT + 26" text-anchor="middle">{{ conditionLabelEn(group.condition) }}</text>
        <text class="n-label" :x="group.x" :y="TOP + PLOT_HEIGHT + 46" text-anchor="middle">n={{ group.stats.n }} · M={{ meanLabel(group.stats.mean) }}</text>
      </g>
      <text :x="LEFT + PLOT_WIDTH / 2" :y="HEIGHT - 12" text-anchor="middle" class="axis-label">Experimental Condition</text>
    </svg>
    <footer><span><i class="box-key" />Median and IQR</span><span v-if="showPoints"><i class="point-key" />Session</span><span><i class="mean-key" />Mean and 95% CI</span></footer>
    <el-dialog v-model="previewVisible" :title="title" width="96vw" top="2vh" append-to-body><div class="coi-large-chart" v-html="previewMarkup" /></el-dialog>
  </section>
</template>

<style scoped>
.boxplot-panel { min-width:0; padding:14px 16px 10px; border:1px solid #e2e8f0; border-radius:9px; background:#fff; }
.boxplot-panel header { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:4px; }
.boxplot-panel header > div:first-child { display:flex; flex-direction:column; gap:3px; }
.boxplot-panel header strong { color:#172033; font-size:16px; font-weight:750; }
.boxplot-panel header span { color:#526071; font-size:13px; font-weight:550; }
.chart-actions{display:flex;gap:7px;flex-shrink:0}
svg { display:block; width:100%; height:auto; overflow:visible; cursor:zoom-in; font-family:Arial,"Helvetica Neue",sans-serif; text-rendering:geometricPrecision; }
.grid line { stroke:#e7ecf2; stroke-width:1; stroke-dasharray:3 3; }
.grid text, .condition-label, .n-label { fill:#334155; font-size:14px; font-weight:650; }
.panel-title { fill:#0f172a; font-size:17px; font-weight:800; }
.panel-subtitle { fill:#526071; font-size:12px; font-weight:600; }
.statistic-label { fill:#334155; font-size:12px; font-weight:700; }
.axis-label { fill:#1e293b; font-size:14px; font-weight:750; }
.condition-label { fill:#0f172a; font-size:15px; font-weight:750; }
.n-label { fill:#64748b; font-size:12px; font-weight:600; }
.axis-line { stroke:#64748b; stroke-width:1.6; }
.whisker, .whisker-cap { stroke-width:1.6; }
.box { stroke-width:2; }
.median { stroke-width:2.5; }
.ci, .ci-cap { stroke-width:2; }
.mean { stroke:white; stroke-width:1; }
.raw-point { opacity:.9; }
.boxplot-panel footer { display:flex; justify-content:center; gap:18px; flex-wrap:wrap; color:#475569; font-size:12px; font-weight:600; }
.boxplot-panel footer span { display:flex; align-items:center; gap:5px; }
.boxplot-panel footer i { display:inline-block; }
.box-key { width:12px; height:8px; border:1.5px solid #64748b; background:#64748b18; }
.point-key { width:5px; height:5px; border-radius:50%; background:#374151; }
.mean-key { width:14px; height:2px; background:#64748b; transform:rotate(90deg); }
:global(.coi-large-chart){overflow:auto;background:#fff}:global(.coi-large-chart svg){display:block;width:1800px;max-width:none;height:auto}
@media print {
  .boxplot-panel { border-color:#777; }
  .box[data-condition="no_assistance"] { stroke:#111 !important; fill:#e5e5e5 !important; }
  .box[data-condition="glasses"],.box[data-condition="app_notification"] { stroke:#111 !important; fill:#fff !important; }
  .whisker,.whisker-cap,.median,.ci,.ci-cap { stroke:#111 !important; }
  .raw-point { fill:#111 !important; }
  .mean { fill:#111 !important; }
}
</style>
