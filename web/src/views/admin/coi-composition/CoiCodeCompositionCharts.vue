<script setup lang="ts">
import { computed, ref } from 'vue'
import { Download, ZoomIn } from '@element-plus/icons-vue'
import type { MetricSummary, PostHocResult, StatisticalTestResult } from '../../../api/admin/coi-analysis'
import type { CoiCompositionObservation, CompositionGlobalTest } from '../../../api/admin/coi-composition-analysis'
import CoiSessionBoxplot from '../coi/CoiSessionBoxplot.vue'
import CoiCompositionPublicationFigure from './CoiCompositionPublicationFigure.vue'
import { downloadSvgElement, serializeSvgElement } from '../task-score/analysisExport'
import { academicNiceMaximum, academicNumber, academicPValue } from '../task-score/academicChartStyle'

const props = defineProps<{
  metrics: MetricSummary[]
  observations: CoiCompositionObservation[]
  conditions: string[]
  tests: StatisticalTestResult[]
  postHocTests: PostHocResult[]
  globalTest: CompositionGlobalTest
}>()

const panels = [
  { metric: 'te_ratio', key: 'te_ratio', title: 'TE · Triggering Event', subtitle: 'Proportion of four-phase codes' },
  { metric: 'ex_ratio', key: 'ex_ratio', title: 'EX · Exploration', subtitle: 'Proportion of four-phase codes' },
  { metric: 'in_ratio', key: 'in_ratio', title: 'IN · Integration', subtitle: 'Proportion of four-phase codes' },
  { metric: 're_ratio', key: 're_ratio', title: 'RE · Resolution', subtitle: 'Proportion of four-phase codes' },
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

const panelRows = computed(() => panels.map((panel, index) => ({
  ...panel,
  panelLabel: `(${String.fromCharCode(97 + index)})`,
  values: valuesFor(panel.key),
  maximum: academicNiceMaximum(Math.max(...props.observations.map(item => Number(item[panel.key])).filter(Number.isFinite), 0) * 1.03),
  statisticLabel: (() => {
    const test = props.tests.find(item => item.metric === panel.metric)
    if (!test) return ''
    return `BH-adjusted ${academicPValue(test.p_value_adjusted)}${test.effect_size_name && test.effect_size != null ? ` · ${test.effect_size_name} = ${academicNumber(test.effect_size, 2)}` : ''}`
  })(),
})))
const scaleLabel = 'Each phase uses a compact, data-appropriate percentage scale.'
const overviewSvgRef = ref<SVGElement | null>(null)
const previewVisible = ref(false)
const previewMarkup = ref('')
const conditionLabelsEn: Record<string, string> = { no_assistance: 'No Assistance', glasses: 'Smart Glasses', app_notification: 'App Notification' }
const conditionLabelEn = (condition: string) => conditionLabelsEn[condition] ?? condition
function openOverview() {
  if (!overviewSvgRef.value) return
  previewMarkup.value = serializeSvgElement(overviewSvgRef.value)
  previewVisible.value = true
}
function downloadOverview() {
  if (overviewSvgRef.value) downloadSvgElement(overviewSvgRef.value, 'coi-mean-composition.svg')
}
</script>

<template>
  <el-card class="academic-chart-card" shadow="never">
    <template #header>
      <div class="chart-heading">
        <strong>Session-Level Four-Phase CoI Composition</strong>
        <span>{{ scaleLabel }}</span>
      </div>
    </template>

    <CoiCompositionPublicationFigure
      :observations="observations"
      :conditions="conditions"
      :tests="tests"
      :post-hoc-tests="postHocTests"
    />

    <section class="composition-overview">
      <header><div><strong>Mean Composition by Condition</strong><span>Each bar totals 100%; labels show phase and mean proportion.</span></div><div class="chart-actions"><el-tooltip content="Enlarge chart"><el-button :icon="ZoomIn" circle size="small" @click="openOverview" /></el-tooltip><el-tooltip content="Download SVG"><el-button :icon="Download" circle size="small" @click="downloadOverview" /></el-tooltip></div></header>
      <svg ref="overviewSvgRef" viewBox="0 0 800 282" role="img" aria-label="Mean four-phase CoI composition by condition" @click="openOverview">
        <defs>
          <pattern id="phase-te" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#4B5563" /></pattern>
          <pattern id="phase-ex" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#0072B2" /></pattern>
          <pattern id="phase-in" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#009E73" /></pattern>
          <pattern id="phase-re" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#D55E00" /></pattern>
        </defs>
        <text x="24" y="28" class="overview-title">Mean CoI Composition by Condition</text>
        <text x="776" y="28" text-anchor="end" class="overview-stat">PERMANOVA {{ academicPValue(globalTest.p_value) }} · R² = {{ academicNumber(globalTest.effect_size, 2) }}</text>
        <g v-for="row in compositionRows" :key="row.condition" :transform="`translate(0 42)`">
          <text class="condition-text" x="156" :y="row.y + 20" text-anchor="end">{{ conditionLabelEn(row.condition) }}</text>
          <g v-for="segment in row.segments" :key="segment.metric">
            <rect
              class="stack-segment"
              :x="175 + segment.start * 560"
              :y="row.y"
              :width="segment.width * 560"
              height="30"
              :fill="`url(#${segment.pattern})`"
            />
            <text class="segment-text" :x="175 + (segment.start + segment.width / 2) * 560" :y="row.y + 19" text-anchor="middle">
              {{ segment.short }} {{ (segment.value * 100).toFixed(1) }}%
            </text>
          </g>
        </g>
        <g class="overview-axis">
          <line x1="165" x2="165" y1="68" y2="194" />
          <line v-for="tickY in [83, 131, 179]" :key="`condition-${tickY}`" x1="165" x2="173" :y1="tickY" :y2="tickY" />
          <text x="28" y="131" transform="rotate(-90 28 131)" text-anchor="middle" class="axis-label">Experimental Condition</text>
          <line x1="175" x2="735" y1="232" y2="232" />
          <g v-for="tick in [0, 25, 50, 75, 100]" :key="tick">
            <line :x1="175 + tick * 5.6" :x2="175 + tick * 5.6" y1="232" y2="238" />
            <text :x="175 + tick * 5.6" y="253" text-anchor="middle">{{ tick }}%</text>
          </g>
          <text x="455" y="276" text-anchor="middle" class="axis-label">Mean Code Composition (%)</text>
        </g>
      </svg>
      <div class="phase-legend"><span><i class="te" />TE Triggering Event</span><span><i class="ex" />EX Exploration</span><span><i class="in" />IN Integration</span><span><i class="re" />RE Resolution</span></div>
    </section>

    <div class="boxplot-layout">
      <CoiSessionBoxplot
        v-for="panel in panelRows"
        :key="panel.metric"
        :title="panel.title"
        :subtitle="panel.subtitle"
        :conditions="conditions"
        :values-by-condition="panel.values"
        :maximum="panel.maximum"
        percent
        unit-label="Phase Proportion (%)"
        :panel-label="panel.panelLabel"
        :statistic-label="panel.statisticLabel"
        :show-points="false"
      />
    </div>

    <footer class="figure-caption">
      <strong>Figure 1. Mean composition and session-level distributions of the four CoI phases.</strong>
      <span>The upper 100% stacked bars summarize condition means. Box plots show medians, IQRs, session observations, and means with 95% confidence intervals.</span>
    </footer>
    <el-dialog v-model="previewVisible" title="Mean Composition by Condition" width="96vw" top="2vh" append-to-body><div class="coi-composition-large" v-html="previewMarkup" /></el-dialog>
  </el-card>
</template>

<style scoped>
.academic-chart-card { border:1px solid #e3e9f2; border-radius:10px; }
.chart-heading { display:flex; flex-direction:column; gap:4px; }
.chart-heading strong { color:#26364b; }
.chart-heading span { color:#718096; font-size:12px; }
.boxplot-layout { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }
.composition-overview { margin-bottom:18px; padding:14px 16px 10px; border:1px solid #d7dee8; border-radius:9px; }
.composition-overview header { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.composition-overview header > div:first-child { display:flex; flex-direction:column; gap:3px; }
.composition-overview header strong { color:#172033; font-size:16px; font-weight:750; }
.composition-overview header span { color:#526071; font-size:13px; font-weight:550; }
.chart-actions{display:flex;gap:7px;flex-shrink:0}
.composition-overview svg { display:block; width:100%; max-height:280px; cursor:zoom-in; font-family:Arial,"Helvetica Neue",sans-serif; text-rendering:geometricPrecision; }
.condition-text { fill:#0f172a; font-size:15px; font-weight:750; }
.overview-title { fill:#0f172a; font-size:17px; font-weight:800; }
.overview-stat { fill:#334155; font-size:12px; font-weight:700; }
.overview-axis line { stroke:#64748b; stroke-width:1.4; }
.overview-axis text { fill:#475569; font-size:12px; font-weight:650; }
.overview-axis .axis-label { fill:#1e293b; font-size:14px; font-weight:750; }
.segment-text { fill:#fff; font-size:13px; font-weight:750; paint-order:stroke; stroke:#17203388; stroke-width:2px; }
.stack-segment { stroke:#fff; stroke-width:1.5; }
.phase-legend { display:flex; justify-content:center; gap:20px; flex-wrap:wrap; color:#334155; font-size:13px; font-weight:650; }
.phase-legend span { display:flex; align-items:center; gap:5px; }
.phase-legend i { width:14px; height:9px; border:1px solid #374151; }
.phase-legend .te { background:#4B5563; }.phase-legend .ex { background:#0072B2; }.phase-legend .in { background:#009E73; }.phase-legend .re { background:#D55E00; }
.figure-caption { display:flex; flex-direction:column; gap:4px; margin:18px 4px 2px; padding-top:12px; border-top:1px solid #eef2f6; color:#66758a; font-size:11px; line-height:1.65; }
.figure-caption strong { color:#3f4f63; font-weight:650; }
:global(.coi-composition-large){overflow:auto;background:#fff}:global(.coi-composition-large svg){display:block;width:1800px;max-width:none;height:auto}
@media(max-width:900px){.boxplot-layout{grid-template-columns:1fr}}
@media print {
  .composition-overview { border-color:#777; }
  .segment-text { stroke:none; }
  .stack-segment { stroke:#111; }
  .phase-legend i { filter:grayscale(1); }
}
</style>
