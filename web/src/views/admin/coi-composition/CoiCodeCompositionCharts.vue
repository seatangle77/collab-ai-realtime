<script setup lang="ts">
import { computed } from 'vue'
import type { MetricSummary } from '../../../api/admin/coi-analysis'
import type { CoiCompositionObservation } from '../../../api/admin/coi-composition-analysis'
import { conditionLabel } from '../coi/reportHelpers'

const props = defineProps<{
  metrics: MetricSummary[]
  observations: CoiCompositionObservation[]
  conditions: string[]
}>()

const phases = [
  { metric: 'te_ratio', key: 'te_ratio', short: 'TE', label: 'Triggering Event' },
  { metric: 'ex_ratio', key: 'ex_ratio', short: 'EX', label: 'Exploration' },
  { metric: 'in_ratio', key: 'in_ratio', short: 'IN', label: 'Integration' },
  { metric: 're_ratio', key: 're_ratio', short: 'RE', label: 'Resolution' },
] as const

const conditionStyles: Record<string, { short: string; color: string }> = {
  no_assistance: { short: '无辅助', color: '#64748b' },
  glasses: { short: '智能眼镜', color: '#3b82f6' },
  app_notification: { short: 'APP 通知', color: '#f97316' },
}

function meanFor(metric: string, condition: string): number {
  return props.metrics
    .find((item) => item.metric === metric)
    ?.conditions.find((item) => item.condition === condition)
    ?.mean ?? 0
}

const alignedRows = computed(() => phases.map(phase => ({
  ...phase,
  conditions: props.conditions.map(condition => ({
    condition,
    value: meanFor(phase.metric, condition),
  })),
})))

function valuesFor(key: keyof CoiCompositionObservation, condition: string): number[] {
  return props.observations
    .filter((item) => item.condition === condition)
    .map((item) => Number(item[key]))
}

function dotLeft(index: number, length: number): number {
  if (length <= 1) return 50
  return 14 + (index % 6) * 14 + (Math.floor(index / 6) % 2) * 4
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function plotPercent(value: number): number {
  return Math.min(100, Math.max(0, value * 200))
}

function conditionColor(condition: string): string {
  return conditionStyles[condition]?.color ?? '#64748b'
}
</script>

<template>
  <el-card class="chart-card" shadow="never">
    <template #header>
      <div class="card-heading">
        <div>
          <strong>四阶段条件对比</strong>
          <span>四个阶段统一使用0–50%刻度；同一行直接比较三个条件</span>
        </div>
        <div class="condition-legend">
          <span v-for="condition in conditions" :key="condition">
            <i :style="{ background: conditionColor(condition) }" />{{ conditionLabel(condition) }}
          </span>
        </div>
      </div>
    </template>

    <div class="aligned-chart">
      <div v-for="row in alignedRows" :key="row.metric" class="aligned-row">
        <div class="phase-name"><strong>{{ row.short }}</strong><span>{{ row.label }}</span></div>
        <div class="aligned-plot" :aria-label="`${row.label}三条件均值`">
          <div class="vertical-grid"><i v-for="tick in 6" :key="tick" /></div>
          <div
            v-for="entry in row.conditions"
            :key="entry.condition"
            class="condition-series"
            :style="{ '--series-color': conditionColor(entry.condition) }"
          >
            <span class="value-line" :style="{ width: `${plotPercent(entry.value)}%` }" />
            <span class="value-dot" :style="{ left: `${plotPercent(entry.value)}%` }" />
            <span class="value-text" :style="{ left: `${plotPercent(entry.value)}%` }">{{ percent(entry.value) }}</span>
          </div>
        </div>
      </div>
      <div class="aligned-axis"><span>0%</span><span>10%</span><span>20%</span><span>30%</span><span>40%</span><span>50%</span></div>
    </div>
  </el-card>

  <el-card class="chart-card" shadow="never">
    <template #header>
      <div class="card-heading">
        <div>
          <strong>组级分布</strong>
          <span>每个点代表一场会话，横线表示条件均值；四个面板均使用0–50%刻度</span>
        </div>
      </div>
    </template>
    <div class="phase-grid">
      <section v-for="phase in phases" :key="phase.metric" class="phase-panel">
        <header>
          <span class="phase-chip">{{ phase.short }}</span>
          <div><strong>{{ phase.label }}</strong><small>编码占比</small></div>
        </header>
        <div class="plot-area">
          <div class="y-axis"><span>50%</span><span>40%</span><span>30%</span><span>20%</span><span>10%</span><span>0%</span></div>
          <div class="plot-columns">
            <div v-for="condition in conditions" :key="condition" class="plot-column">
              <div class="grid-lines"><i /><i /><i /><i /><i /><i /></div>
              <span
                v-for="(value, index) in valuesFor(phase.key, condition)"
                :key="`${condition}-${index}`"
                class="plot-dot"
                :style="{ bottom: `${plotPercent(value)}%`, left: `${dotLeft(index, valuesFor(phase.key, condition).length)}%`, background: conditionColor(condition) }"
                :title="`${conditionLabel(condition)}: ${percent(value)}`"
              />
              <span class="mean-line" :style="{ bottom: `${plotPercent(meanFor(phase.metric, condition))}%`, borderColor: conditionColor(condition) }" />
              <div class="plot-label">{{ conditionLabel(condition) }}</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </el-card>
</template>

<style scoped>
.chart-card { border: 1px solid #e3e9f2; border-radius: 10px; }
.card-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.card-heading > div:first-child { display: flex; flex-direction: column; gap: 4px; }
.card-heading span { color: #718096; font-size: 12px; }
.condition-legend { display: flex; gap: 14px; flex-wrap: wrap; }
.condition-legend span { display: flex; align-items: center; gap: 5px; color: #475569; font-size: 12px; font-weight: 650; }
.condition-legend i { width: 9px; height: 9px; border-radius: 50%; }
.aligned-chart { padding: 4px 12px 0; }
.aligned-row { display: grid; grid-template-columns: 116px minmax(0, 1fr); align-items: center; gap: 18px; margin: 16px 0; }
.phase-name { display: flex; flex-direction: column; align-items: flex-end; }
.phase-name strong { color: #26364b; font-size: 14px; }
.phase-name span { color: #8a97aa; font-size: 10px; }
.aligned-plot { position: relative; display: grid; grid-template-rows: repeat(3, 18px); min-height: 54px; }
.vertical-grid { position: absolute; inset: 0; display: flex; justify-content: space-between; pointer-events: none; }
.vertical-grid i { height: 100%; border-left: 1px dashed #e1e7ef; }
.condition-series { position: relative; min-width: 0; --series-color: #64748b; }
.value-line { position: absolute; top: 8px; left: 0; height: 2px; border-radius: 99px; background: var(--series-color); opacity: .25; }
.value-dot { position: absolute; top: 4px; width: 10px; height: 10px; margin-left: -5px; border: 2px solid white; border-radius: 50%; background: var(--series-color); box-shadow: 0 1px 3px rgba(15,23,42,.2); }
.value-text { position: absolute; top: 1px; margin-left: 9px; color: #344054; font-size: 11px; font-weight: 700; white-space: nowrap; }
.aligned-axis { display: flex; justify-content: space-between; margin-left: 134px; color: #94a3b8; font-size: 11px; }
.phase-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.phase-panel { padding: 14px; border: 1px solid #e5eaf2; border-radius: 9px; background: #fbfcfe; }
.phase-panel header { display: flex; align-items: center; gap: 9px; margin-bottom: 12px; }
.phase-panel header > div { display: flex; flex-direction: column; }
.phase-panel header strong { color: #26364b; font-size: 13px; }
.phase-panel header small { color: #8a97aa; font-size: 11px; }
.phase-chip { display: grid; width: 32px; height: 28px; place-items: center; border-radius: 7px; color: #324055; background: #e9eef5; font-size: 12px; font-weight: 800; }
.plot-area { display: grid; grid-template-columns: 38px minmax(0, 1fr); height: 190px; }
.y-axis { display: flex; flex-direction: column; justify-content: space-between; padding: 0 7px 21px 0; color: #9aa7ba; font-size: 10px; text-align: right; }
.plot-columns { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; min-width: 0; }
.plot-column { position: relative; height: 168px; border-left: 1px solid #eef2f6; border-right: 1px solid #eef2f6; }
.grid-lines { position: absolute; inset: 0 0 0; display: flex; flex-direction: column; justify-content: space-between; }
.grid-lines i { display: block; border-top: 1px dashed #e5eaf1; }
.plot-dot { position: absolute; z-index: 2; width: 7px; height: 7px; margin: 0 0 -3.5px -3.5px; border: 1.5px solid white; border-radius: 50%; box-shadow: 0 1px 3px rgba(15,23,42,.28); }
.mean-line { position: absolute; z-index: 3; left: 9%; right: 9%; margin-bottom: -1px; border-top: 2px solid; }
.plot-label { position: absolute; top: 174px; left: 50%; transform: translateX(-50%); color: #66758a; font-size: 10px; white-space: nowrap; }
@media (max-width: 1100px) { .phase-grid { grid-template-columns: 1fr; } }
@media (max-width: 720px) {
  .card-heading { flex-direction: column; }
  .aligned-row { grid-template-columns: 62px minmax(0, 1fr); gap: 10px; }
  .phase-name span { display: none; }
  .aligned-axis { margin-left: 72px; }
}
</style>
