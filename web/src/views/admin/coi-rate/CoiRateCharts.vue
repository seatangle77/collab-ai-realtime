<script setup lang="ts">
import { computed } from 'vue'
import type {
  CoiRateContrast,
  CoiRateMetricSummary,
  CoiRateObservation,
} from '../../../api/admin/coi-rate-analysis'
import { conditionLabel } from '../coi/reportHelpers'

const props = defineProps<{
  metrics: CoiRateMetricSummary[]
  observations: CoiRateObservation[]
  contrasts: CoiRateContrast[]
  conditions: string[]
}>()

const phaseMetrics = [
  { metric: 'te_rate', short: 'TE', label: 'Triggering Event' },
  { metric: 'ex_rate', short: 'EX', label: 'Exploration' },
  { metric: 'in_rate', short: 'IN', label: 'Integration' },
  { metric: 're_rate', short: 'RE', label: 'Resolution' },
] as const

const conditionColors: Record<string, string> = {
  no_assistance: '#64748b',
  glasses: '#3b82f6',
  app_notification: '#f97316',
}

function color(condition: string): string {
  return conditionColors[condition] ?? '#64748b'
}

function meanFor(metric: string, condition: string): number {
  return props.metrics.find(item => item.metric === metric)
    ?.conditions.find(item => item.condition === condition)?.mean ?? 0
}

function observationValues(metric: keyof CoiRateObservation, condition: string): number[] {
  return props.observations
    .filter(item => item.condition === condition)
    .map(item => Number(item[metric]))
    .filter(Number.isFinite)
}

function niceMaximum(values: number[]): number {
  const maximum = Math.max(...values, 0)
  if (maximum <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(maximum))
  const normalized = maximum / magnitude
  const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return nice * magnitude
}

const totalScale = computed(() => niceMaximum(props.observations.map(item => item.total_rate * 1.08)))
const phaseScale = computed(() => niceMaximum(props.observations.flatMap(item => [item.te_rate, item.ex_rate, item.in_rate, item.re_rate].map(value => value * 1.08))))
const contrastScale = computed(() => {
  const values = props.contrasts.flatMap(item => [item.mean_difference, item.ci_low ?? 0, item.ci_high ?? 0].map(Math.abs))
  return niceMaximum(values) || 1
})

const totalRows = computed(() => props.conditions.map(condition => ({
  condition,
  mean: meanFor('total_rate', condition),
  values: observationValues('total_rate', condition),
})))

const phaseRows = computed(() => phaseMetrics.map(phase => ({
  ...phase,
  conditions: props.conditions.map(condition => ({
    condition,
    mean: meanFor(phase.metric, condition),
    values: observationValues(phase.metric, condition),
  })),
})))

const contrastRows = computed(() => props.contrasts.filter(item => item.metric !== 'total_rate'))

function position(value: number, maximum: number): number {
  return Math.min(100, Math.max(0, value / maximum * 100))
}

function contrastPosition(value: number): number {
  return Math.min(100, Math.max(0, 50 + value / (contrastScale.value * 2) * 100))
}

function formatRate(value: number | null | undefined): string {
  return value == null ? '—' : value.toFixed(2)
}

function signedRate(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}`
}
</script>

<template>
  <el-card class="rate-chart-card" shadow="never">
    <template #header>
      <div class="chart-heading">
        <div><strong>全部四阶段观点产生率</strong><span>每个圆点代表一场会话；粗线表示条件均值</span></div>
        <div class="legend">
          <span v-for="condition in conditions" :key="condition"><i :style="{ background: color(condition) }" />{{ conditionLabel(condition) }}</span>
        </div>
      </div>
    </template>
    <div class="rate-lanes">
      <div v-for="row in totalRows" :key="row.condition" class="rate-lane">
        <span class="condition-name">{{ conditionLabel(row.condition) }}</span>
        <div class="rate-track">
          <i v-for="tick in 5" :key="tick" class="grid-line" :style="{ left: `${(tick - 1) * 25}%` }" />
          <span class="mean-line" :style="{ width: `${position(row.mean, totalScale)}%`, background: color(row.condition) }" />
          <span
            v-for="(value, index) in row.values"
            :key="`${row.condition}-${index}`"
            class="session-dot"
            :style="{ left: `${position(value, totalScale)}%`, top: `${3 + index % 3 * 6}px`, borderColor: color(row.condition) }"
          />
        </div>
        <strong>{{ formatRate(row.mean) }}/min</strong>
      </div>
      <div class="axis"><span>0</span><span>{{ formatRate(totalScale / 4) }}</span><span>{{ formatRate(totalScale / 2) }}</span><span>{{ formatRate(totalScale * 0.75) }}</span><span>{{ formatRate(totalScale) }}/min</span></div>
    </div>
    <footer class="figure-caption"><strong>图 1　每分钟四阶段有效观点总数。</strong><span>会话总时长来自系统记录的会话开始与结束时间；沉默时间保留在整场讨论时长中。</span></footer>
  </el-card>

  <el-card class="rate-chart-card" shadow="never">
    <template #header><div class="chart-heading"><div><strong>四阶段观点产生率</strong><span>四个阶段共用相同的每分钟刻度</span></div></div></template>
    <div class="phase-chart">
      <section v-for="row in phaseRows" :key="row.metric" class="phase-group">
        <div class="phase-name"><strong>{{ row.short }}</strong><span>{{ row.label }}</span></div>
        <div class="phase-lanes">
          <div v-for="entry in row.conditions" :key="entry.condition" class="phase-lane">
            <span class="condition-name">{{ conditionLabel(entry.condition) }}</span>
            <div class="rate-track">
              <i v-for="tick in 5" :key="tick" class="grid-line" :style="{ left: `${(tick - 1) * 25}%` }" />
              <span class="mean-line" :style="{ width: `${position(entry.mean, phaseScale)}%`, background: color(entry.condition) }" />
              <span
                v-for="(value, index) in entry.values"
                :key="`${entry.condition}-${index}`"
                class="session-dot"
                :style="{ left: `${position(value, phaseScale)}%`, top: `${3 + index % 3 * 6}px`, borderColor: color(entry.condition) }"
              />
            </div>
            <strong>{{ formatRate(entry.mean) }}</strong>
          </div>
        </div>
      </section>
      <div class="phase-axis"><span>0</span><span>{{ formatRate(phaseScale / 4) }}</span><span>{{ formatRate(phaseScale / 2) }}</span><span>{{ formatRate(phaseScale * 0.75) }}</span><span>{{ formatRate(phaseScale) }}/min</span></div>
    </div>
    <footer class="figure-caption"><strong>图 2　TE、EX、IN与RE的会话级每分钟产生率。</strong><span>圆点展示真实会话分布，均值线用于比较条件方向；统计结论以置换检验和BH校正结果为准。</span></footer>
  </el-card>

  <el-card class="rate-chart-card" shadow="never">
    <template #header><div class="chart-heading"><div><strong>相对无辅助条件的产生率差异</strong><span>点表示均值差，横线表示会话级Bootstrap 95%置信区间</span></div></div></template>
    <div class="contrast-chart">
      <div class="contrast-axis"><span>−{{ formatRate(contrastScale) }}</span><span>0</span><span>+{{ formatRate(contrastScale) }}/min</span></div>
      <div v-for="row in contrastRows" :key="`${row.metric}-${row.comparison_condition}`" class="contrast-row">
        <span><strong>{{ row.label.replace(' 产生率', '') }}</strong> · {{ conditionLabel(row.comparison_condition) }}</span>
        <div class="contrast-track">
          <i class="zero-line" />
          <span
            v-if="row.ci_low != null && row.ci_high != null"
            class="ci-line"
            :style="{ left: `${contrastPosition(row.ci_low)}%`, width: `${contrastPosition(row.ci_high) - contrastPosition(row.ci_low)}%`, borderColor: color(row.comparison_condition) }"
          />
          <span class="contrast-dot" :style="{ left: `${contrastPosition(row.mean_difference)}%`, background: color(row.comparison_condition) }" />
        </div>
        <strong :class="{ positive: row.mean_difference > 0, negative: row.mean_difference < 0 }">{{ signedRate(row.mean_difference) }}/min</strong>
      </div>
    </div>
    <footer class="figure-caption"><strong>图 3　智能眼镜和APP通知相对无辅助条件的阶段产生率差异。</strong><span>置信区间跨过0表示当前数据仍与“无稳定差异”相容；图中不以颜色或方向代替统计显著性判断。</span></footer>
  </el-card>
</template>

<style scoped>
.rate-chart-card { border: 1px solid #e3e9f2; border-radius: 10px; }
.chart-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.chart-heading > div:first-child { display: flex; flex-direction: column; gap: 4px; }
.chart-heading strong { color: #26364b; }
.chart-heading span { color: #718096; font-size: 12px; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; }
.legend span { display: flex; align-items: center; gap: 5px; color: #475569; font-size: 12px; font-weight: 650; }
.legend i { width: 9px; height: 9px; border-radius: 50%; }
.rate-lanes { padding: 8px 12px 0; }
.rate-lane, .phase-lane { display: grid; grid-template-columns: 92px minmax(0, 1fr) 76px; align-items: center; gap: 12px; min-height: 38px; }
.condition-name { overflow: hidden; color: #64748b; font-size: 11px; text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.rate-track { position: relative; height: 23px; }
.grid-line { position: absolute; inset-block: 0; border-left: 1px dashed #e3e9f1; }
.mean-line { position: absolute; z-index: 1; top: 10px; left: 0; height: 4px; border-radius: 2px; opacity: 0.7; }
.session-dot { position: absolute; z-index: 2; width: 6px; height: 6px; margin-left: -3px; border: 1.5px solid; border-radius: 50%; background: white; }
.rate-lane > strong, .phase-lane > strong { color: #344054; font-size: 12px; font-variant-numeric: tabular-nums; }
.axis, .phase-axis { display: flex; justify-content: space-between; margin: 7px 88px 0 104px; color: #94a3b8; font-size: 10px; }
.phase-chart { padding: 0 12px; }
.phase-group { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 20px; padding: 14px 0; border-bottom: 1px solid #edf1f5; }
.phase-name { display: flex; flex-direction: column; align-items: flex-end; justify-content: center; }
.phase-name strong { color: #26364b; }
.phase-name span { color: #8a97aa; font-size: 10px; }
.phase-lanes { display: flex; flex-direction: column; gap: 2px; }
.phase-axis { margin-left: 236px; }
.figure-caption { display: flex; flex-direction: column; gap: 4px; margin: 18px 12px 2px 124px; padding-top: 12px; border-top: 1px solid #eef2f6; color: #66758a; font-size: 11px; line-height: 1.65; }
.figure-caption strong { color: #3f4f63; font-weight: 650; }
.contrast-chart { padding: 6px 12px 0; }
.contrast-axis { display: flex; justify-content: space-between; margin: 0 92px 4px 200px; color: #94a3b8; font-size: 10px; }
.contrast-row { display: grid; grid-template-columns: 176px minmax(0, 1fr) 82px; align-items: center; gap: 12px; min-height: 42px; border-top: 1px solid #f0f3f7; }
.contrast-row > span:first-child { color: #64748b; font-size: 11px; text-align: right; }
.contrast-track { position: relative; height: 22px; }
.zero-line { position: absolute; inset-block: 0; left: 50%; border-left: 1px solid #9aa7b8; }
.ci-line { position: absolute; top: 10px; border-top: 2px solid; }
.ci-line::before, .ci-line::after { position: absolute; top: -4px; height: 8px; border-left: 1.5px solid; border-color: inherit; content: ''; }
.ci-line::before { left: 0; }
.ci-line::after { right: 0; }
.contrast-dot { position: absolute; top: 7px; width: 8px; height: 8px; margin-left: -4px; border: 1px solid white; border-radius: 50%; box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.16); }
.contrast-row > strong { color: #475569; font-size: 11px; font-variant-numeric: tabular-nums; }
.positive { color: #167044 !important; }
.negative { color: #b54747 !important; }
@media (max-width: 760px) {
  .chart-heading { flex-direction: column; }
  .phase-group { grid-template-columns: 45px minmax(0, 1fr); gap: 7px; }
  .phase-name span, .legend { display: none; }
  .rate-lane, .phase-lane { grid-template-columns: 68px minmax(0, 1fr) 58px; gap: 6px; }
  .axis, .phase-axis { margin-left: 78px; margin-right: 64px; }
  .contrast-row { grid-template-columns: 118px minmax(0, 1fr) 68px; gap: 7px; }
  .contrast-axis { margin-left: 128px; margin-right: 74px; }
  .figure-caption { margin-left: 12px; }
}
</style>
