<script setup lang="ts">
import { computed } from 'vue'
import type {
  CoiRateContrast,
  CoiRateMetricSummary,
  CoiRateObservation,
} from '../../../api/admin/coi-rate-analysis'
import CoiSessionBoxplot from '../coi/CoiSessionBoxplot.vue'
import { conditionLabel } from '../coi/reportHelpers'

const props = defineProps<{
  metrics: CoiRateMetricSummary[]
  observations: CoiRateObservation[]
  contrasts: CoiRateContrast[]
  conditions: string[]
}>()

const panels = [
  { metric: 'total_rate', key: 'total_rate', title: '全部四阶段观点', subtitle: 'TE＋EX＋IN＋RE编码次数／会话分钟数' },
  { metric: 'te_rate', key: 'te_rate', title: 'TE · Triggering Event', subtitle: '每分钟触发事件编码数' },
  { metric: 'ex_rate', key: 'ex_rate', title: 'EX · Exploration', subtitle: '每分钟探索编码数' },
  { metric: 'in_rate', key: 'in_rate', title: 'IN · Integration', subtitle: '每分钟整合编码数' },
  { metric: 're_rate', key: 're_rate', title: 'RE · Resolution', subtitle: '每分钟解决编码数' },
] as const

const conditionColors: Record<string, string> = {
  no_assistance: '#374151',
  glasses: '#1d4ed8',
  app_notification: '#c2410c',
}

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
  return (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10) * magnitude
}

const totalMaximum = computed(() => niceMaximum(Math.max(...props.observations.map(item => item.total_rate), 0) * 1.08))
const phaseMaximum = computed(() => niceMaximum(Math.max(...props.observations.flatMap(item => [item.te_rate, item.ex_rate, item.in_rate, item.re_rate]), 0) * 1.08))
const panelRows = computed(() => panels.map(panel => ({
  ...panel,
  values: valuesFor(panel.key),
  maximum: panel.metric === 'total_rate' ? totalMaximum.value : phaseMaximum.value,
})))
const contrastRows = computed(() => props.contrasts.filter(item => item.metric !== 'total_rate'))
const contrastMaximum = computed(() => {
  const maximum = Math.max(...contrastRows.value.flatMap(item => [item.mean_difference, item.ci_low ?? 0, item.ci_high ?? 0].map(Math.abs)), 0.1)
  return Math.ceil(maximum * 10) / 10
})

function contrastPosition(value: number): number {
  return Math.min(100, Math.max(0, 50 + value / (contrastMaximum.value * 2) * 100))
}

function color(condition: string): string {
  return conditionColors[condition] ?? '#64748b'
}

function signed(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}`
}
</script>

<template>
  <el-card class="academic-chart-card" shadow="never">
    <template #header>
      <div class="chart-heading">
        <div><strong>会话级观点产生率分布</strong><span>箱线图显示中位数与四分位区间；所有12场会话均以小型点符号展示</span></div>
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
        unit-label="编码次数／分钟"
      />
    </div>
    <footer class="figure-caption"><strong>图 1　三个实验条件下的CoI观点产生率分布。</strong><span>箱体表示中位数和四分位区间，须线延伸至1.5倍四分位距内的最远值，小型点符号为每场会话；圆形、方形和三角形分别对应无辅助、智能眼镜和APP通知，右侧菱形与误差线表示均值及其95%置信区间。</span></footer>
  </el-card>

  <el-card class="academic-chart-card" shadow="never">
    <template #header><div class="chart-heading"><div><strong>相对无辅助条件的效应差异</strong><span>均值差和会话级Bootstrap 95%置信区间；单位为编码次数／分钟</span></div></div></template>
    <div class="forest-chart">
      <div class="forest-axis"><span>−{{ contrastMaximum.toFixed(1) }}</span><span>0</span><span>+{{ contrastMaximum.toFixed(1) }}</span></div>
      <div v-for="row in contrastRows" :key="`${row.metric}-${row.comparison_condition}`" class="forest-row">
        <span class="forest-label"><strong>{{ row.label.replace(' 产生率', '') }}</strong><small>{{ conditionLabel(row.comparison_condition) }} − 无辅助</small></span>
        <div class="forest-track">
          <i class="zero-line" />
          <span
            v-if="row.ci_low != null && row.ci_high != null"
            class="ci-line"
            :style="{ left: `${contrastPosition(row.ci_low)}%`, width: `${contrastPosition(row.ci_high) - contrastPosition(row.ci_low)}%`, borderColor: color(row.comparison_condition) }"
          />
          <span class="effect-point" :style="{ left: `${contrastPosition(row.mean_difference)}%`, background: color(row.comparison_condition) }" />
        </div>
        <strong class="effect-value">{{ signed(row.mean_difference) }} <small>[{{ row.ci_low?.toFixed(2) ?? '—' }}, {{ row.ci_high?.toFixed(2) ?? '—' }}]</small></strong>
      </div>
    </div>
    <footer class="figure-caption"><strong>图 2　智能眼镜与APP通知相对无辅助条件的阶段产生率均值差。</strong><span>中间竖线表示零差异；置信区间跨过零表示当前数据仍与“无稳定差异”相容。</span></footer>
  </el-card>
</template>

<style scoped>
.academic-chart-card { border:1px solid #e3e9f2; border-radius:10px; }
.chart-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.chart-heading > div { display:flex; flex-direction:column; gap:4px; }
.chart-heading strong { color:#26364b; }
.chart-heading span { color:#718096; font-size:12px; }
.boxplot-layout { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }
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
@media(max-width:900px){.boxplot-layout{grid-template-columns:1fr}.wide-panel{grid-column:auto}.forest-row{grid-template-columns:126px minmax(0,1fr) 118px;gap:7px}.forest-axis{margin-left:140px;margin-right:126px}}
</style>
