<script setup lang="ts">
import { computed } from 'vue'
import { conditionLabel } from './reportHelpers'

const props = withDefaults(defineProps<{
  title: string
  subtitle?: string
  conditions: string[]
  valuesByCondition: Record<string, number[]>
  maximum?: number
  percent?: boolean
  unitLabel?: string
}>(), {
  subtitle: '',
  maximum: undefined,
  percent: false,
  unitLabel: '',
})

const WIDTH = 720
const HEIGHT = 320
const LEFT = 62
const RIGHT = 18
const TOP = 30
const BOTTOM = 62
const PLOT_WIDTH = WIDTH - LEFT - RIGHT
const PLOT_HEIGHT = HEIGHT - TOP - BOTTOM
const BOX_WIDTH = 62

const colors: Record<string, string> = {
  no_assistance: '#374151',
  glasses: '#1d4ed8',
  app_notification: '#c2410c',
}
const jitterPattern = [-24, -16, -8, 0, 8, 16, 24, -20, -12, -4, 4, 12, 20]

function color(condition: string): string {
  return colors[condition] ?? '#374151'
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

function niceMaximum(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10
  return nice * magnitude
}

const allValues = computed(() => props.conditions.flatMap(condition => props.valuesByCondition[condition] ?? []).filter(Number.isFinite))
const domainMaximum = computed(() => props.maximum ?? niceMaximum(Math.max(...allValues.value, 0) * 1.08))
const groups = computed(() => props.conditions.map((condition, index) => ({
  condition,
  color: color(condition),
  x: LEFT + PLOT_WIDTH * (index + 0.5) / props.conditions.length,
  values: props.valuesByCondition[condition] ?? [],
  stats: statistics(props.valuesByCondition[condition] ?? []),
})))
const ticks = computed(() => Array.from({ length: 5 }, (_, index) => ({
  value: domainMaximum.value * index / 4,
  y: TOP + PLOT_HEIGHT - PLOT_HEIGHT * index / 4,
})))

function y(value: number): number {
  return TOP + PLOT_HEIGHT - Math.min(1, Math.max(0, value / domainMaximum.value)) * PLOT_HEIGHT
}

function format(value: number): string {
  return props.percent ? `${(value * 100).toFixed(0)}%` : value.toFixed(domainMaximum.value <= 2 ? 2 : 1)
}

function pointX(groupX: number, index: number): number {
  return groupX + (jitterPattern[index % jitterPattern.length] ?? 0)
}
</script>

<template>
  <section class="boxplot-panel">
    <header><strong>{{ title }}</strong><span v-if="subtitle">{{ subtitle }}</span></header>
    <svg :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" role="img" :aria-label="`${title}：三种实验条件的箱线图、会话原始点、均值与95%置信区间`">
      <g class="grid">
        <template v-for="tick in ticks" :key="tick.value">
          <line :x1="LEFT" :x2="WIDTH - RIGHT" :y1="tick.y" :y2="tick.y" />
          <text :x="LEFT - 9" :y="tick.y + 4" text-anchor="end">{{ format(tick.value) }}</text>
        </template>
      </g>
      <line class="axis-line" :x1="LEFT" :x2="LEFT" :y1="TOP" :y2="TOP + PLOT_HEIGHT" />
      <text v-if="unitLabel" class="unit-label" :x="LEFT" :y="15">{{ unitLabel }}</text>

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
            v-for="(value, index) in group.condition === 'no_assistance' ? group.values : []"
            :key="`${group.condition}-${index}`"
            class="raw-point"
            :cx="pointX(group.x, index)"
            :cy="y(value)"
            r="2.6"
            :stroke="group.color"
          ><title>{{ conditionLabel(group.condition) }} · {{ format(value) }}</title></circle>
          <rect
            v-for="(value, index) in group.condition === 'glasses' ? group.values : []"
            :key="`${group.condition}-${index}`"
            class="raw-point"
            :x="pointX(group.x, index) - 2.5"
            :y="y(value) - 2.5"
            width="5"
            height="5"
            :stroke="group.color"
          ><title>{{ conditionLabel(group.condition) }} · {{ format(value) }}</title></rect>
          <polygon
            v-for="(value, index) in group.condition !== 'no_assistance' && group.condition !== 'glasses' ? group.values : []"
            :key="`${group.condition}-${index}`"
            class="raw-point"
            :points="`${pointX(group.x, index)},${y(value) - 3} ${pointX(group.x, index) + 2.8},${y(value) + 2.3} ${pointX(group.x, index) - 2.8},${y(value) + 2.3}`"
            :stroke="group.color"
          ><title>{{ conditionLabel(group.condition) }} · {{ format(value) }}</title></polygon>
        </template>
        <text class="condition-label" :x="group.x" :y="TOP + PLOT_HEIGHT + 26" text-anchor="middle">{{ conditionLabel(group.condition) }}</text>
        <text class="n-label" :x="group.x" :y="TOP + PLOT_HEIGHT + 43" text-anchor="middle">n={{ group.stats.n }}</text>
      </g>
    </svg>
    <footer><span><i class="box-key" />中位数与四分位区间</span><span><i class="point-key" />每场会话</span><span><i class="mean-key" />均值及95% CI</span></footer>
  </section>
</template>

<style scoped>
.boxplot-panel { min-width:0; padding:14px 16px 10px; border:1px solid #e2e8f0; border-radius:9px; background:#fff; }
.boxplot-panel header { display:flex; flex-direction:column; gap:2px; margin-bottom:4px; }
.boxplot-panel header strong { color:#26364b; font-size:14px; }
.boxplot-panel header span { color:#7a8799; font-size:11px; }
svg { display:block; width:100%; height:auto; overflow:visible; }
.grid line { stroke:#e7ecf2; stroke-width:1; stroke-dasharray:3 3; }
.grid text, .unit-label, .condition-label, .n-label { fill:#718096; font-size:11px; }
.unit-label { font-weight:650; }
.n-label { fill:#9aa5b4; font-size:9px; }
.axis-line { stroke:#aeb8c5; stroke-width:1; }
.whisker, .whisker-cap { stroke-width:1.6; }
.box { stroke-width:2; }
.median { stroke-width:2.5; }
.ci, .ci-cap { stroke-width:2; }
.mean { stroke:white; stroke-width:1; }
.raw-point { fill:white; fill-opacity:.92; stroke-width:1.25; opacity:.95; }
.boxplot-panel footer { display:flex; justify-content:center; gap:16px; flex-wrap:wrap; color:#718096; font-size:9px; }
.boxplot-panel footer span { display:flex; align-items:center; gap:5px; }
.boxplot-panel footer i { display:inline-block; }
.box-key { width:12px; height:8px; border:1.5px solid #64748b; background:#64748b18; }
.point-key { width:4px; height:4px; border:1.25px solid #374151; border-radius:50%; background:white; }
.mean-key { width:14px; height:2px; background:#64748b; transform:rotate(90deg); }
@media print {
  .boxplot-panel { border-color:#777; }
  .box[data-condition="no_assistance"] { stroke:#111 !important; fill:#e5e5e5 !important; }
  .box[data-condition="glasses"] { stroke:#111 !important; fill:#fff !important; stroke-dasharray:7 3; }
  .box[data-condition="app_notification"] { stroke:#111 !important; fill:#fff !important; stroke-dasharray:2 2; }
  .whisker,.whisker-cap,.median,.ci,.ci-cap,.raw-point { stroke:#111 !important; }
  .mean { fill:#111 !important; }
}
</style>
