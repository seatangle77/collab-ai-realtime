<script setup lang="ts">
import { computed } from 'vue'
import type {
  GroupMeanMetricResult,
  MixedModelMetricResult,
  PairwiseContrast,
} from '../../../api/admin/questionnaire-hierarchical-analysis'
import type { QMetricSummary, QStatisticalTestResult } from '../../../api/admin/questionnaire-analysis'
import { conditionLabel, formatNumber } from '../questionnaire/reportHelpers'

const props = defineProps<{
  kind: 'individual' | 'group' | 'mixed'
  conditions: string[]
  groupMetric?: GroupMeanMetricResult
  mixedMetric?: MixedModelMetricResult
  individualMetric?: QMetricSummary
  individualTest?: QStatisticalTestResult
  individualPAdjusted?: number | null
  individualPairs?: PairwiseContrast[]
}>()

const colors: Record<string, string> = {
  no_assistance: '#64748b',
  glasses: '#2563eb',
  app_notification: '#ea580c',
}
const left = 74
const right = 786
const plotTop = 128
const plotBottom = 322
const yMin = 1
const yMax = 7

const title = computed(() => props.individualMetric?.label ?? props.groupMetric?.label ?? props.mixedMetric?.label ?? '')
const test = computed(() => props.groupMetric?.test ?? props.mixedMetric?.fixed_effect_test)
const pairs = computed(() => props.kind === 'individual' ? (props.individualPairs ?? []) : (test.value?.pairwise ?? []))
const xFor = (condition: string) => {
  const index = props.conditions.indexOf(condition)
  const width = right - left
  return left + (index + 0.5) * (width / props.conditions.length)
}
const yFor = (value: number) => plotBottom - ((value - yMin) / (yMax - yMin)) * (plotBottom - plotTop)
const pFor = (pair: PairwiseContrast) => pair.p_value_adjusted ?? pair.p_value
const sigLabel = (p: number | null | undefined) => {
  if (p === null || p === undefined) return '—'
  if (p < 0.001) return '***'
  if (p < 0.01) return '**'
  if (p < 0.05) return '*'
  return 'n.s.'
}
const pText = (p: number | null | undefined) => {
  if (p === null || p === undefined) return 'p = —'
  if (p < 0.001) return 'p < .001'
  return `p = ${p.toFixed(3).replace('0.', '.')}`
}
const omnibusP = computed(() => props.kind === 'individual'
  ? (props.individualPAdjusted ?? props.individualTest?.p_value)
  : (test.value?.p_value_adjusted ?? test.value?.p_value))
const groupPoints = computed(() => props.groupMetric?.observations ?? [])
const mixedMeans = computed(() => props.mixedMetric?.estimated_means ?? [])
const individualStats = computed(() => props.individualMetric?.conditions ?? [])
const pairY = (index: number) => 48 + index * 23
const jitter = (index: number) => ((index % 7) - 3) * 7
</script>

<template>
  <div class="metric-chart-shell">
    <svg class="metric-chart" viewBox="0 0 840 370" role="img" :aria-label="`${title} ${kind === 'individual' ? '个人' : kind === 'group' ? '小组均值' : '混合效应'}图`">
      <text x="22" y="22" class="chart-title">{{ title }}</text>
      <text x="818" y="22" text-anchor="end" :class="['omnibus', omnibusP != null && omnibusP < 0.05 ? 'significant' : 'nonsig']">
        总体 {{ pText(omnibusP) }} · {{ sigLabel(omnibusP) }}
      </text>

      <g v-for="(pair, index) in pairs" :key="`${pair.condition_a}-${pair.condition_b}`">
        <path
          :d="`M ${xFor(pair.condition_a)} ${pairY(index) + 7} V ${pairY(index)} H ${xFor(pair.condition_b)} V ${pairY(index) + 7}`"
          :class="pFor(pair) != null && pFor(pair)! < 0.05 ? 'bracket significant-stroke' : 'bracket'"
        />
        <text
          :x="(xFor(pair.condition_a) + xFor(pair.condition_b)) / 2"
          :y="pairY(index) - 3"
          text-anchor="middle"
          :class="['pair-label', pFor(pair) != null && pFor(pair)! < 0.05 ? 'significant' : 'nonsig']"
        >{{ sigLabel(pFor(pair)) }} · {{ pText(pFor(pair)) }}</text>
      </g>

      <g v-for="tick in [1, 2, 3, 4, 5, 6, 7]" :key="tick">
        <line :x1="left" :x2="right" :y1="yFor(tick)" :y2="yFor(tick)" class="grid" />
        <text :x="left - 16" :y="yFor(tick) + 4" text-anchor="end" class="axis-label">{{ tick }}</text>
      </g>
      <line :x1="left" :x2="left" :y1="plotTop" :y2="plotBottom" class="axis" />
      <line :x1="left" :x2="right" :y1="plotBottom" :y2="plotBottom" class="axis" />

      <template v-if="kind === 'individual'">
        <g v-for="stat in individualStats" :key="stat.condition">
          <line
            v-if="stat.mean != null && stat.sd != null && stat.n > 1"
            :x1="xFor(stat.condition)" :x2="xFor(stat.condition)"
            :y1="yFor(Math.min(7, stat.mean + 1.96 * stat.sd / Math.sqrt(stat.n)))"
            :y2="yFor(Math.max(1, stat.mean - 1.96 * stat.sd / Math.sqrt(stat.n)))"
            class="ci-line"
          />
          <circle v-if="stat.mean != null" :cx="xFor(stat.condition)" :cy="yFor(stat.mean)" r="8" :fill="colors[stat.condition] ?? '#64748b'" />
          <text v-if="stat.mean != null" :x="xFor(stat.condition) + 14" :y="yFor(stat.mean) + 4" class="value-label">M={{ formatNumber(stat.mean) }}</text>
        </g>
      </template>
      <template v-else-if="kind === 'group'">
        <circle
          v-for="(point, index) in groupPoints"
          :key="`${point.group_id}-${point.metric}`"
          :cx="xFor(point.condition) + jitter(index)"
          :cy="yFor(point.value)"
          r="5.5"
          :fill="colors[point.condition] ?? '#64748b'"
          fill-opacity=".6"
        >
          <title>{{ point.group_id }} · G={{ point.participant_count }} · {{ formatNumber(point.value) }}</title>
        </circle>
        <g v-for="stat in groupMetric?.conditions ?? []" :key="stat.condition">
          <line
            v-if="stat.mean != null && stat.sd != null && stat.n > 1"
            :x1="xFor(stat.condition)" :x2="xFor(stat.condition)"
            :y1="yFor(Math.min(7, stat.mean + 1.96 * stat.sd / Math.sqrt(stat.n)))"
            :y2="yFor(Math.max(1, stat.mean - 1.96 * stat.sd / Math.sqrt(stat.n)))"
            class="ci-line"
          />
          <rect
            v-if="stat.mean != null"
            :x="xFor(stat.condition) - 7" :y="yFor(stat.mean) - 7"
            width="14" height="14" rx="2"
            :fill="colors[stat.condition] ?? '#64748b'"
          />
          <text v-if="stat.mean != null" :x="xFor(stat.condition) + 13" :y="yFor(stat.mean) + 4" class="value-label">
            M={{ formatNumber(stat.mean) }}
          </text>
        </g>
      </template>

      <template v-else>
        <g v-for="item in mixedMeans" :key="item.condition">
          <line :x1="xFor(item.condition)" :x2="xFor(item.condition)" :y1="yFor(item.ci_high)" :y2="yFor(item.ci_low)" class="ci-line" />
          <line :x1="xFor(item.condition) - 10" :x2="xFor(item.condition) + 10" :y1="yFor(item.ci_high)" :y2="yFor(item.ci_high)" class="ci-line" />
          <line :x1="xFor(item.condition) - 10" :x2="xFor(item.condition) + 10" :y1="yFor(item.ci_low)" :y2="yFor(item.ci_low)" class="ci-line" />
          <circle :cx="xFor(item.condition)" :cy="yFor(item.estimate)" r="8" :fill="colors[item.condition] ?? '#64748b'" />
          <text :x="xFor(item.condition) + 14" :y="yFor(item.estimate) + 4" class="value-label">{{ formatNumber(item.estimate) }}</text>
        </g>
      </template>

      <g v-for="condition in conditions" :key="condition">
        <text :x="xFor(condition)" y="348" text-anchor="middle" class="condition-label">{{ conditionLabel(condition) }}</text>
      </g>
      <text x="20" y="220" text-anchor="middle" class="axis-title" transform="rotate(-90 20 220)">量表均分（1–7）</text>
    </svg>
    <div class="chart-caption">
      <span v-if="kind === 'individual'">圆点为个人层面的条件均值，误差线为普通 95% CI。</span>
      <span v-else-if="kind === 'group'">圆点为小组均值，方块为条件均值，误差线为 95% CI。</span>
      <span v-else>圆点为混合模型估计边际均值，误差线为 95% CI。</span>
      <span>星号和 n.s. 均依据校正后 p 值。</span>
    </div>
  </div>
</template>

<style scoped>
.metric-chart-shell { border: 1px solid #e1e7f0; border-radius: 10px; background: #fff; overflow: hidden; }
.metric-chart { display: block; width: 100%; min-width: 620px; }
.chart-title { fill: #172033; font-size: 16px; font-weight: 800; }
.omnibus, .pair-label { font-size: 11px; font-weight: 750; }
.significant { fill: #b91c1c; }
.nonsig { fill: #64748b; }
.bracket { fill: none; stroke: #94a3b8; stroke-width: 1.3; }
.significant-stroke { stroke: #b91c1c; stroke-width: 1.8; }
.grid { stroke: #e5eaf1; stroke-width: 1; stroke-dasharray: 3 3; }
.axis { stroke: #64748b; stroke-width: 1.4; }
.axis-label, .value-label { fill: #475569; font-size: 11px; font-weight: 650; }
.condition-label, .axis-title { fill: #1e293b; font-size: 12px; font-weight: 750; }
.ci-line { stroke: #1e293b; stroke-width: 2; }
.chart-caption { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 16px; padding: 8px 14px 12px; color: #64748b; font-size: 12px; }
</style>
