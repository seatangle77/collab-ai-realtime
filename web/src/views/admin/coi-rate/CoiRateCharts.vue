<script setup lang="ts">
import { computed, ref } from 'vue'
import { Download, ZoomIn } from '@element-plus/icons-vue'
import type {
  CoiRateContrast,
  CoiRateMetricSummary,
  CoiRateObservation,
  CoiRatePermutationTest,
} from '../../../api/admin/coi-rate-analysis'
import CoiSessionBoxplot from '../coi/CoiSessionBoxplot.vue'
import { downloadSvgElement, serializeSvgElement } from '../task-score/analysisExport'
import { academicConditionColor, academicConditionLabel, academicNumber, academicPValue } from '../task-score/academicChartStyle'

const props = defineProps<{
  metrics: CoiRateMetricSummary[]
  observations: CoiRateObservation[]
  contrasts: CoiRateContrast[]
  conditions: string[]
  tests: CoiRatePermutationTest[]
}>()

const panels = [
  { metric: 'total_rate', key: 'total_rate', title: 'All Four CoI Phases', subtitle: 'TE + EX + IN + RE rate (codes/min)' },
  { metric: 'te_rate', key: 'te_rate', title: 'TE · Triggering Event', subtitle: 'Rate (codes/min)' },
  { metric: 'ex_rate', key: 'ex_rate', title: 'EX · Exploration', subtitle: 'Rate (codes/min)' },
  { metric: 'in_rate', key: 'in_rate', title: 'IN · Integration', subtitle: 'Rate (codes/min)' },
  { metric: 're_rate', key: 're_rate', title: 'RE · Resolution', subtitle: 'Rate (codes/min)' },
] as const

function valuesFor(key: keyof CoiRateObservation): Record<string, number[]> {
  return Object.fromEntries(props.conditions.map(condition => [
    condition,
    props.observations.filter(item => item.condition === condition).map(item => Number(item[key])).filter(Number.isFinite),
  ]))
}

function niceMaximum(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const steps = [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9, 10]
  return (steps.find(step => normalized <= step) ?? 10) * magnitude
}

const totalMaximum = computed(() => niceMaximum(Math.max(...props.observations.map(item => item.total_rate), 0) * 1.08))
const phaseMaximum = computed(() => niceMaximum(Math.max(...props.observations.flatMap(item => [item.te_rate, item.ex_rate, item.in_rate, item.re_rate]), 0) * 1.08))
const panelRows = computed(() => panels.map((panel, index) => {
  const test = props.tests.find(item => item.metric === panel.metric)
  return {
  ...panel,
  panelLabel: `(${String.fromCharCode(97 + index)})`,
  values: valuesFor(panel.key),
  maximum: panel.metric === 'total_rate' ? totalMaximum.value : phaseMaximum.value,
  statisticLabel: test ? `BH-adjusted ${academicPValue(test.p_value_adjusted)} · η² = ${academicNumber(test.effect_size, 2)}` : '',
  }
}))
const meanPanels = computed(() => panels.map((panel, panelIndex) => ({
  ...panel,
  panelLabel: `(${String.fromCharCode(97 + panelIndex)})`,
  test: props.tests.find(item => item.metric === panel.metric),
  conditions: props.conditions.map(condition => ({
    condition,
    value: props.metrics.find(item => item.metric === panel.metric)?.conditions.find(item => item.condition === condition)?.mean ?? 0,
    n: props.metrics.find(item => item.metric === panel.metric)?.conditions.find(item => item.condition === condition)?.n ?? 0,
  })),
})))
const totalMeanMaximum = computed(() => niceMaximum(Math.max(...meanPanels.value[0]!.conditions.map(item => item.value), 1) * 1.08))
const phaseMeanMaximum = computed(() => niceMaximum(Math.max(...meanPanels.value.slice(1).flatMap(panel => panel.conditions.map(item => item.value)), 0.1) * 1.08))
const contrastRows = computed(() => props.contrasts)
const contrastMaximum = computed(() => {
  const maximum = Math.max(...contrastRows.value.flatMap(item => [item.mean_difference, item.ci_low ?? 0, item.ci_high ?? 0].map(Math.abs)), 0.1)
  return Math.ceil(maximum * 10) / 10
})

function color(condition: string): string {
  return academicConditionColor(condition)
}

function signed(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}`
}

const conditionLabelEn = academicConditionLabel
const metricLabelsEn: Record<string, string> = { te_rate: 'TE Triggering Event', ex_rate: 'EX Exploration', in_rate: 'IN Integration', re_rate: 'RE Resolution' }
const meanSvgRef = ref<SVGElement | null>(null)
const forestSvgRef = ref<SVGElement | null>(null)
const previewVisible = ref(false)
const previewTitle = ref('')
const previewMarkup = ref('')
const forestHeight = computed(() => 126 + contrastRows.value.length * 64)
function phasePanelLeft(index: number) { return 24 + (index % 2) * 590 }
function phasePanelTop(index: number) { return 286 + Math.floor(index / 2) * 244 }
function svgBarWidth(value: number, maximum: number, width: number) { return Math.max(0, Math.min(width, value / maximum * width)) }
function contrastX(value: number) { return 390 + Math.min(1, Math.max(0, (value + contrastMaximum.value) / (contrastMaximum.value * 2))) * 500 }
function axisTicks(maximum: number) { return Array.from({ length: 5 }, (_, index) => maximum * index / 4) }
function totalAxisX(value: number) { return 225 + value / totalMeanMaximum.value * 800 }
function phaseAxisX(value: number, left: number) { return left + 165 + value / phaseMeanMaximum.value * 340 }
function contrastTicks() { return Array.from({ length: 5 }, (_, index) => -contrastMaximum.value + contrastMaximum.value * 2 * index / 4) }
function testLabel(metric: string) {
  const test = props.tests.find(item => item.metric === metric)
  return test ? `BH-adjusted ${academicPValue(test.p_value_adjusted)} · η² = ${academicNumber(test.effect_size, 2)}` : ''
}
function openChart(svg: SVGElement | null, title: string) {
  if (!svg) return
  previewTitle.value = title
  previewMarkup.value = serializeSvgElement(svg)
  previewVisible.value = true
}
function downloadChart(svg: SVGElement | null, filename: string) {
  if (svg) downloadSvgElement(svg, filename)
}
</script>

<template>
  <el-card class="academic-chart-card" shadow="never">
    <template #header><div class="chart-heading"><div><strong>Mean CoI Idea-Generation Rates</strong><span>Condition means; all four phase panels share one scale.</span></div><div class="chart-actions"><el-tooltip content="Enlarge chart"><el-button :icon="ZoomIn" circle @click="openChart(meanSvgRef, 'Mean CoI Idea-Generation Rates')" /></el-tooltip><el-tooltip content="Download SVG"><el-button :icon="Download" circle @click="downloadChart(meanSvgRef, 'coi-mean-idea-generation-rates.svg')" /></el-tooltip></div></div></template>
    <svg v-if="meanPanels[0]" ref="meanSvgRef" class="rate-svg" viewBox="0 0 1200 790" role="img" aria-label="Mean CoI idea-generation rates by condition" @click="openChart(meanSvgRef, 'Mean CoI Idea-Generation Rates')">
      <text x="24" y="30" class="chart-title">(a) All Four CoI Phases</text>
      <text x="1170" y="30" text-anchor="end" class="stat-label">{{ testLabel('total_rate') }}</text>
      <g class="numeric-axis">
        <template v-for="tick in axisTicks(totalMeanMaximum)" :key="tick">
          <line :x1="totalAxisX(tick)" :x2="totalAxisX(tick)" y1="48" y2="205" class="grid-line" />
          <text :x="totalAxisX(tick)" y="225" text-anchor="middle">{{ tick.toFixed(2) }}</text>
        </template>
        <line x1="225" x2="1025" y1="205" y2="205" class="axis-line" />
        <text x="625" y="250" text-anchor="middle" class="axis-title">Rate (codes/min)</text>
      </g>
      <g v-for="(entry, index) in meanPanels[0].conditions" :key="entry.condition">
        <text x="205" :y="76 + index * 48" text-anchor="end" class="condition">{{ conditionLabelEn(entry.condition) }}</text>
        <rect x="225" :y="57 + index * 48" :width="svgBarWidth(entry.value, totalMeanMaximum, 800)" height="24" :fill="color(entry.condition)" />
        <text :x="Math.min(1100, totalAxisX(entry.value) + 10)" :y="76 + index * 48" class="value">{{ entry.value.toFixed(3) }} (n={{ entry.n }})</text>
      </g>
      <line x1="24" x2="1176" y1="270" y2="270" class="panel-line" />
      <g v-for="(panel, panelIndex) in meanPanels.slice(1)" :key="panel.metric">
        <text :x="phasePanelLeft(panelIndex)" :y="phasePanelTop(panelIndex)" class="chart-title">{{ panel.panelLabel }} {{ panel.title.replace(' · ', ' ') }}</text>
        <text :x="phasePanelLeft(panelIndex) + 550" :y="phasePanelTop(panelIndex)" text-anchor="end" class="stat-label">{{ testLabel(panel.metric) }}</text>
        <g class="numeric-axis">
          <template v-for="tick in axisTicks(phaseMeanMaximum)" :key="tick">
            <line :x1="phaseAxisX(tick, phasePanelLeft(panelIndex))" :x2="phaseAxisX(tick, phasePanelLeft(panelIndex))" :y1="phasePanelTop(panelIndex) + 18" :y2="phasePanelTop(panelIndex) + 172" class="grid-line" />
            <text :x="phaseAxisX(tick, phasePanelLeft(panelIndex))" :y="phasePanelTop(panelIndex) + 191" text-anchor="middle">{{ tick.toFixed(2) }}</text>
          </template>
          <line :x1="phasePanelLeft(panelIndex) + 165" :x2="phasePanelLeft(panelIndex) + 505" :y1="phasePanelTop(panelIndex) + 172" :y2="phasePanelTop(panelIndex) + 172" class="axis-line" />
          <text :x="phasePanelLeft(panelIndex) + 335" :y="phasePanelTop(panelIndex) + 216" text-anchor="middle" class="axis-title">Rate (codes/min)</text>
        </g>
        <g v-for="(entry, index) in panel.conditions" :key="entry.condition">
          <text :x="phasePanelLeft(panelIndex) + 145" :y="phasePanelTop(panelIndex) + 44 + index * 46" text-anchor="end" class="condition">{{ conditionLabelEn(entry.condition) }}</text>
          <rect :x="phasePanelLeft(panelIndex) + 165" :y="phasePanelTop(panelIndex) + 26 + index * 46" :width="svgBarWidth(entry.value, phaseMeanMaximum, 340)" height="23" :fill="color(entry.condition)" />
          <text :x="phasePanelLeft(panelIndex) + 515" :y="phasePanelTop(panelIndex) + 44 + index * 46" class="value">{{ entry.value.toFixed(3) }}</text>
        </g>
      </g>
    </svg>
    <footer class="figure-caption"><strong>Figure 1. Mean CoI idea-generation rates across the three conditions.</strong><span>Bar length represents the condition mean. Inferential tests and session-level distributions determine whether differences are stable.</span></footer>
  </el-card>

  <el-card class="academic-chart-card" shadow="never">
    <template #header>
      <div class="chart-heading">
        <div><strong>Session-Level Idea-Generation Rate Distributions</strong><span>Box plots show medians, IQRs, all sessions, means, and 95% confidence intervals.</span></div>
      </div>
    </template>
    <div class="boxplot-layout">
      <CoiSessionBoxplot
        v-for="panel in panelRows"
        :key="panel.metric"
        :class="{ 'wide-panel': panel.metric === 'total_rate' }"
        :title="panel.title"
        :subtitle="panel.subtitle"
        :conditions="conditions"
        :values-by-condition="panel.values"
        :maximum="panel.maximum"
        unit-label="Rate (codes/min)"
        :panel-label="panel.panelLabel"
        :statistic-label="panel.statisticLabel"
      />
    </div>
    <footer class="figure-caption"><strong>Figure 2. Session-level CoI idea-generation rate distributions.</strong><span>Boxes show medians and IQRs; points show sessions; diamonds and error bars show means and 95% confidence intervals.</span></footer>
  </el-card>

  <el-card class="academic-chart-card" shadow="never">
    <template #header><div class="chart-heading"><div><strong>Effects Relative to No Assistance</strong><span>Mean differences with session-level bootstrap 95% confidence intervals.</span></div><div class="chart-actions"><el-tooltip content="Enlarge chart"><el-button :icon="ZoomIn" circle @click="openChart(forestSvgRef, 'Effects Relative to No Assistance')" /></el-tooltip><el-tooltip content="Download SVG"><el-button :icon="Download" circle @click="downloadChart(forestSvgRef, 'coi-rate-effects-vs-no-assistance.svg')" /></el-tooltip></div></div></template>
    <svg ref="forestSvgRef" class="rate-svg" :viewBox="`0 0 1200 ${forestHeight}`" role="img" aria-label="Mean differences relative to no assistance" @click="openChart(forestSvgRef, 'Effects Relative to No Assistance')">
      <g class="numeric-axis">
        <template v-for="tick in contrastTicks()" :key="tick">
          <line :x1="contrastX(tick)" :x2="contrastX(tick)" y1="34" :y2="forestHeight - 58" :class="tick === 0 ? 'zero-line-svg' : 'grid-line'" />
          <text :x="contrastX(tick)" :y="forestHeight - 35" text-anchor="middle">{{ signed(tick) }}</text>
        </template>
        <line x1="390" x2="890" :y1="forestHeight - 58" :y2="forestHeight - 58" class="axis-line" />
        <text x="640" :y="forestHeight - 8" text-anchor="middle" class="axis-title">Mean Difference in Rate (codes/min)</text>
      </g>
      <g v-for="(row,index) in contrastRows" :key="`${row.metric}-${row.comparison_condition}`">
        <line x1="25" x2="1175" :y1="50 + index * 64" :y2="50 + index * 64" stroke="#e2e8f0" />
        <text x="350" :y="73 + index * 64" text-anchor="end" class="metric">{{ metricLabelsEn[row.metric] ?? row.metric }}</text>
        <text x="350" :y="91 + index * 64" text-anchor="end" class="comparison">{{ conditionLabelEn(row.comparison_condition) }} − No Assistance · {{ testLabel(row.metric) }}</text>
        <line v-if="row.ci_low != null && row.ci_high != null" :x1="contrastX(row.ci_low)" :x2="contrastX(row.ci_high)" :y1="78 + index * 64" :y2="78 + index * 64" :stroke="color(row.comparison_condition)" stroke-width="4" />
        <line v-if="row.ci_low != null" :x1="contrastX(row.ci_low)" :x2="contrastX(row.ci_low)" :y1="70 + index * 64" :y2="86 + index * 64" :stroke="color(row.comparison_condition)" stroke-width="3" />
        <line v-if="row.ci_high != null" :x1="contrastX(row.ci_high)" :x2="contrastX(row.ci_high)" :y1="70 + index * 64" :y2="86 + index * 64" :stroke="color(row.comparison_condition)" stroke-width="3" />
        <polygon :points="`${contrastX(row.mean_difference)},${70 + index * 64} ${contrastX(row.mean_difference) + 8},${78 + index * 64} ${contrastX(row.mean_difference)},${86 + index * 64} ${contrastX(row.mean_difference) - 8},${78 + index * 64}`" :fill="color(row.comparison_condition)" />
        <text x="925" :y="83 + index * 64" class="effect">{{ signed(row.mean_difference) }} [{{ row.ci_low?.toFixed(2) ?? '—' }}, {{ row.ci_high?.toFixed(2) ?? '—' }}]</text>
      </g>
    </svg>
    <footer class="figure-caption"><strong>Figure 3. Total and phase-rate differences for Smart Glasses and App Notification relative to No Assistance.</strong><span>Diamonds show mean differences and horizontal lines show bootstrap 95% confidence intervals; intervals crossing zero indicate no stable difference.</span></footer>
  </el-card>
  <el-dialog v-model="previewVisible" :title="previewTitle" width="96vw" top="2vh" append-to-body><div class="coi-rate-large" v-html="previewMarkup" /></el-dialog>
</template>

<style scoped>
.academic-chart-card { border:1px solid #e3e9f2; border-radius:10px; }
.chart-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.chart-heading > div { display:flex; flex-direction:column; gap:4px; }
.chart-heading strong { color:#172033; font-size:16px; font-weight:750; }
.chart-heading span { color:#526071; font-size:13px; font-weight:550; }
.chart-actions{display:flex;gap:8px;flex-shrink:0}.rate-svg{display:block;width:100%;height:auto;cursor:zoom-in;font-family:Arial,"Helvetica Neue",sans-serif;text-rendering:geometricPrecision}
.rate-svg .chart-title{fill:#0f172a;font-size:18px;font-weight:800}.rate-svg .condition{fill:#1e293b;font-size:14px;font-weight:700}.rate-svg .value{fill:#1e293b;font-size:13px;font-weight:750}.rate-svg .stat-label{fill:#334155;font-size:11px;font-weight:700}.rate-svg .metric{fill:#0f172a;font-size:15px;font-weight:750}.rate-svg .comparison{fill:#526071;font-size:11px;font-weight:600}.rate-svg .effect{fill:#1e293b;font-size:14px;font-weight:700}.rate-svg .numeric-axis text{fill:#475569;font-size:12px;font-weight:650}.rate-svg .axis-title{fill:#1e293b;font-size:14px;font-weight:750}.rate-svg .grid-line{stroke:#dfe6ee;stroke-width:1;stroke-dasharray:3 3}.rate-svg .axis-line{stroke:#64748b;stroke-width:1.5}.rate-svg .zero-line-svg{stroke:#334155;stroke-width:2}.rate-svg .panel-line{stroke:#cbd5e1;stroke-width:1.5}
.boxplot-layout { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }
.mean-total-panel { padding:2px 12px 18px; border-bottom:1px solid #e2e8f0; }
.mean-total-panel h3,.mean-phase-panel h3 { margin:0 0 10px; color:#26364b; font-size:13px; }
.mean-phase-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:22px 34px; padding:20px 12px 4px; }
.mean-bar-row { display:grid; grid-template-columns:94px minmax(0,1fr) 86px; align-items:center; gap:10px; min-height:32px; color:#475569; font-size:11px; }
.mean-bar-row.compact { grid-template-columns:86px minmax(0,1fr) 58px; }
.mean-bar-track { height:14px; background:repeating-linear-gradient(to right,#f1f4f8 0,#f1f4f8 calc(25% - 1px),#d8e0e9 25%,#f1f4f8 calc(25% + 1px)); }
.mean-bar-track i { display:block; height:14px; border-radius:2px; }
.mean-bar-row strong { color:#253247; font-variant-numeric:tabular-nums; }
.wide-panel { grid-column:1 / -1; }
.figure-caption { display:flex; flex-direction:column; gap:4px; margin:18px 4px 2px; padding-top:12px; border-top:1px solid #eef2f6; color:#66758a; font-size:11px; line-height:1.65; }
.figure-caption strong { color:#3f4f63; font-weight:650; }
.forest-chart { padding:4px 12px 0; }
.forest-axis { display:flex; justify-content:space-between; margin:0 168px 5px 196px; color:#94a3b8; font-size:10px; }
.forest-row { display:grid; grid-template-columns:172px minmax(0,1fr) 154px; align-items:center; gap:12px; min-height:47px; border-top:1px solid #edf1f5; }
.forest-label { display:flex; flex-direction:column; align-items:flex-end; color:#445268; font-size:11px; }
.forest-label small { color:#8793a4; }
.forest-track { position:relative; height:24px; background:linear-gradient(to right,transparent 24.8%,#edf1f5 25%,transparent 25.2%,transparent 74.8%,#edf1f5 75%,transparent 75.2%); }
.zero-line { position:absolute; inset-block:0; left:50%; border-left:1.5px solid #8491a2; }
.ci-line { position:absolute; top:11px; border-top:2.5px solid; }
.ci-line::before,.ci-line::after { position:absolute; top:-5px; height:10px; border-left:2px solid; border-color:inherit; content:''; }
.ci-line::before { left:0; }.ci-line::after { right:0; }
.effect-point { position:absolute; top:7px; width:10px; height:10px; margin-left:-5px; transform:rotate(45deg); border:1px solid white; box-shadow:0 0 0 1px rgba(15,23,42,.15); }
.effect-value { color:#3f4f63; font-size:11px; font-variant-numeric:tabular-nums; }
.effect-value small { color:#7d899a; font-weight:500; }
:global(.coi-rate-large){overflow:auto;background:#fff}:global(.coi-rate-large svg){display:block;width:1900px;max-width:none;height:auto}
@media(max-width:900px){.boxplot-layout,.mean-phase-grid{grid-template-columns:1fr}.wide-panel{grid-column:auto}.forest-row{grid-template-columns:126px minmax(0,1fr) 118px;gap:7px}.forest-axis{margin-left:140px;margin-right:126px}}
</style>
