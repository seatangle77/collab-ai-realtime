<script setup lang="ts">
import { computed } from 'vue'
import type { MetricSummary } from '../../../api/admin/coi-analysis'
import type { CoiCompositionObservation } from '../../../api/admin/coi-composition-analysis'
import CoiSessionBoxplot from '../coi/CoiSessionBoxplot.vue'
import { conditionLabel } from '../coi/reportHelpers'

const props = defineProps<{
  metrics: MetricSummary[]
  observations: CoiCompositionObservation[]
  conditions: string[]
}>()

const panels = [
  { metric: 'te_ratio', key: 'te_ratio', title: 'TE · Triggering Event', subtitle: '触发事件占四阶段编码的比例' },
  { metric: 'ex_ratio', key: 'ex_ratio', title: 'EX · Exploration', subtitle: '探索占四阶段编码的比例' },
  { metric: 'in_ratio', key: 'in_ratio', title: 'IN · Integration', subtitle: '整合占四阶段编码的比例' },
  { metric: 're_ratio', key: 're_ratio', title: 'RE · Resolution', subtitle: '解决占四阶段编码的比例' },
] as const
const phaseStyles = [
  { metric: 'te_ratio', short: 'TE', pattern: 'phase-te' },
  { metric: 'ex_ratio', short: 'EX', pattern: 'phase-ex' },
  { metric: 'in_ratio', short: 'IN', pattern: 'phase-in' },
  { metric: 're_ratio', short: 'RE', pattern: 'phase-re' },
] as const

function meanFor(metric: string, condition: string): number {
  return props.metrics.find(item => item.metric === metric)
    ?.conditions.find(item => item.condition === condition)?.mean ?? 0
}

const compositionRows = computed(() => props.conditions.map((condition, rowIndex) => {
  const raw = phaseStyles.map(phase => ({ ...phase, value: meanFor(phase.metric, condition) }))
  const total = raw.reduce((sum, phase) => sum + phase.value, 0) || 1
  let cursor = 0
  return {
    condition,
    y: 26 + rowIndex * 48,
    segments: raw.map(phase => {
      const width = phase.value / total
      const segment = { ...phase, start: cursor, width }
      cursor += width
      return segment
    }),
  }
}))

function valuesFor(key: keyof CoiCompositionObservation): Record<string, number[]> {
  return Object.fromEntries(props.conditions.map(condition => [
    condition,
    props.observations
      .filter(item => item.condition === condition)
      .map(item => Number(item[key]))
      .filter(Number.isFinite),
  ]))
}

const panelRows = computed(() => panels.map(panel => ({
  ...panel,
  values: valuesFor(panel.key),
})))
const compositionMaximum = computed(() => {
  const maximum = Math.max(...props.observations.flatMap(item => [item.te_ratio, item.ex_ratio, item.in_ratio, item.re_ratio]), 0)
  return Math.min(1, Math.max(0.5, Math.ceil(maximum * 10) / 10))
})
const scaleLabel = computed(() => `四个阶段使用共同的0–${(compositionMaximum.value * 100).toFixed(0)}%纵轴，便于直接比较`)
</script>

<template>
  <el-card class="academic-chart-card" shadow="never">
    <template #header>
      <div class="chart-heading">
        <strong>会话级CoI四阶段构成分布</strong>
        <span>{{ scaleLabel }}</span>
      </div>
    </template>

    <section class="composition-overview">
      <header><strong>条件平均构成</strong><span>每个条形合计为100%；颜色与纹理共同区分四个阶段</span></header>
      <svg viewBox="0 0 760 182" role="img" aria-label="三种实验条件的CoI四阶段平均构成百分比堆叠条形图">
        <defs>
          <pattern id="phase-te" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#374151" /></pattern>
          <pattern id="phase-ex" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#1d4ed8" /><path d="M-2,2 L2,-2 M0,8 L8,0 M6,10 L10,6" stroke="#fff" stroke-width="1.2" opacity=".65" /></pattern>
          <pattern id="phase-in" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#047857" /><circle cx="2" cy="2" r="1" fill="#fff" opacity=".7" /><circle cx="6" cy="6" r="1" fill="#fff" opacity=".7" /></pattern>
          <pattern id="phase-re" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#b91c1c" /><path d="M0,4 H8 M4,0 V8" stroke="#fff" stroke-width="1" opacity=".6" /></pattern>
        </defs>
        <g v-for="row in compositionRows" :key="row.condition">
          <text class="condition-text" x="126" :y="row.y + 20" text-anchor="end">{{ conditionLabel(row.condition) }}</text>
          <g v-for="segment in row.segments" :key="segment.metric">
            <rect
              class="stack-segment"
              :x="145 + segment.start * 560"
              :y="row.y"
              :width="segment.width * 560"
              height="30"
              :fill="`url(#${segment.pattern})`"
            />
            <text class="segment-text" :x="145 + (segment.start + segment.width / 2) * 560" :y="row.y + 19" text-anchor="middle">
              {{ segment.short }} {{ (segment.value * 100).toFixed(1) }}%
            </text>
          </g>
        </g>
      </svg>
      <div class="phase-legend"><span><i class="te" />TE 触发事件</span><span><i class="ex" />EX 探索</span><span><i class="in" />IN 整合</span><span><i class="re" />RE 解决</span></div>
    </section>

    <div class="boxplot-layout">
      <CoiSessionBoxplot
        v-for="panel in panelRows"
        :key="panel.metric"
        :title="panel.title"
        :subtitle="panel.subtitle"
        :conditions="conditions"
        :values-by-condition="panel.values"
        :maximum="compositionMaximum"
        percent
        unit-label="阶段占比"
      />
    </div>

    <footer class="figure-caption">
      <strong>图 1　三种实验条件下CoI四阶段的平均构成与会话级分布。</strong>
      <span>上方100%堆叠条形图用于概览条件平均构成；下方箱体表示中位数和四分位区间，须线延伸至1.5倍四分位距内的最远值，小型点符号为每场会话，右侧菱形与误差线表示均值及其95%置信区间。圆形、方形和三角形分别对应无辅助、智能眼镜和APP通知，因此黑白打印时仍可区分。</span>
    </footer>
  </el-card>
</template>

<style scoped>
.academic-chart-card { border:1px solid #e3e9f2; border-radius:10px; }
.chart-heading { display:flex; flex-direction:column; gap:4px; }
.chart-heading strong { color:#26364b; }
.chart-heading span { color:#718096; font-size:12px; }
.boxplot-layout { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }
.composition-overview { margin-bottom:18px; padding:14px 16px 10px; border:1px solid #d7dee8; border-radius:9px; }
.composition-overview header { display:flex; flex-direction:column; gap:2px; }
.composition-overview header strong { color:#26364b; font-size:14px; }
.composition-overview header span { color:#66758a; font-size:11px; }
.composition-overview svg { display:block; width:100%; max-height:250px; }
.condition-text { fill:#334155; font-size:12px; font-weight:650; }
.segment-text { fill:#fff; font-size:10px; font-weight:650; paint-order:stroke; stroke:#17203355; stroke-width:2px; }
.stack-segment { stroke:#fff; stroke-width:1.5; }
.phase-legend { display:flex; justify-content:center; gap:18px; flex-wrap:wrap; color:#4b5563; font-size:10px; }
.phase-legend span { display:flex; align-items:center; gap:5px; }
.phase-legend i { width:14px; height:9px; border:1px solid #374151; }
.phase-legend .te { background:#374151; }.phase-legend .ex { background:repeating-linear-gradient(135deg,#1d4ed8 0,#1d4ed8 3px,#fff 3px,#fff 4px); }.phase-legend .in { background:#047857; }.phase-legend .re { background:#b91c1c; }
.figure-caption { display:flex; flex-direction:column; gap:4px; margin:18px 4px 2px; padding-top:12px; border-top:1px solid #eef2f6; color:#66758a; font-size:11px; line-height:1.65; }
.figure-caption strong { color:#3f4f63; font-weight:650; }
@media(max-width:900px){.boxplot-layout{grid-template-columns:1fr}}
@media print {
  .composition-overview { border-color:#777; }
  .segment-text { stroke:none; }
  .stack-segment { stroke:#111; }
  .phase-legend i { filter:grayscale(1); }
}
</style>
