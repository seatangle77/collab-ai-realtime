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
  { metric: 'te_ratio', key: 'te_ratio', short: 'TE', label: 'Triggering Event', color: '#64748b' },
  { metric: 'ex_ratio', key: 'ex_ratio', short: 'EX', label: 'Exploration', color: '#3b82f6' },
  { metric: 'in_ratio', key: 'in_ratio', short: 'IN', label: 'Integration', color: '#16a34a' },
  { metric: 're_ratio', key: 're_ratio', short: 'RE', label: 'Resolution', color: '#f97316' },
] as const

function meanFor(metric: string, condition: string): number {
  return props.metrics
    .find((item) => item.metric === metric)
    ?.conditions.find((item) => item.condition === condition)
    ?.mean ?? 0
}

const compositionRows = computed(() => props.conditions.map((condition) => ({
  condition,
  segments: phases.map((phase) => ({ ...phase, value: meanFor(phase.metric, condition) })),
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
</script>

<template>
  <el-card class="chart-card" shadow="never">
    <template #header>
      <div class="card-heading">
        <div>
          <strong>三条件 CoI 编码构成</strong>
          <span>先按每场会话计算四阶段编码占比，再对条件内会话等权平均</span>
        </div>
        <div class="legend">
          <span v-for="phase in phases" :key="phase.metric">
            <i :style="{ background: phase.color }" />{{ phase.short }}
          </span>
        </div>
      </div>
    </template>

    <div class="stacked-chart">
      <div v-for="row in compositionRows" :key="row.condition" class="stacked-row">
        <div class="condition-name">{{ conditionLabel(row.condition) }}</div>
        <div class="stacked-bar" :aria-label="`${conditionLabel(row.condition)} CoI编码构成`">
          <div
            v-for="segment in row.segments"
            :key="segment.metric"
            class="stacked-segment"
            :style="{ width: `${segment.value * 100}%`, background: segment.color }"
            :title="`${segment.label}: ${percent(segment.value)}`"
          >
            <span v-if="segment.value >= 0.095">{{ segment.short }} {{ percent(segment.value) }}</span>
          </div>
        </div>
      </div>
      <div class="axis-row"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>
    </div>
  </el-card>

  <el-card class="chart-card" shadow="never">
    <template #header>
      <div class="card-heading">
        <div>
          <strong>组级分布</strong>
          <span>每个点代表一场会话，横线表示条件均值</span>
        </div>
      </div>
    </template>
    <div class="phase-grid">
      <section v-for="phase in phases" :key="phase.metric" class="phase-panel">
        <header>
          <span class="phase-chip" :style="{ background: phase.color }">{{ phase.short }}</span>
          <div><strong>{{ phase.label }}</strong><small>编码占比</small></div>
        </header>
        <div class="plot-area">
          <div class="y-axis"><span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span></div>
          <div class="plot-columns">
            <div v-for="condition in conditions" :key="condition" class="plot-column">
              <div class="grid-lines"><i /><i /><i /><i /><i /></div>
              <span
                v-for="(value, index) in valuesFor(phase.key, condition)"
                :key="`${condition}-${index}`"
                class="plot-dot"
                :style="{ bottom: `${value * 100}%`, left: `${dotLeft(index, valuesFor(phase.key, condition).length)}%`, background: phase.color }"
                :title="`${conditionLabel(condition)}: ${percent(value)}`"
              />
              <span class="mean-line" :style="{ bottom: `${meanFor(phase.metric, condition) * 100}%`, borderColor: phase.color }" />
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
.legend { display: flex; gap: 14px; }
.legend span { display: flex; align-items: center; gap: 5px; color: #475569; font-weight: 650; }
.legend i { width: 9px; height: 9px; border-radius: 3px; }
.stacked-chart { padding: 8px 6px 2px; }
.stacked-row { display: grid; grid-template-columns: 92px minmax(0, 1fr); align-items: center; gap: 14px; margin: 18px 0; }
.condition-name { color: #334155; font-size: 13px; font-weight: 700; text-align: right; }
.stacked-bar { display: flex; height: 46px; overflow: hidden; border-radius: 8px; background: #eef2f7; box-shadow: inset 0 0 0 1px rgba(15, 23, 42, .08); }
.stacked-segment { display: grid; place-items: center; min-width: 0; color: white; font-size: 12px; font-weight: 750; transition: width .25s ease; }
.stacked-segment span { overflow: hidden; padding: 0 5px; white-space: nowrap; text-shadow: 0 1px 2px rgba(0,0,0,.28); }
.axis-row { display: flex; justify-content: space-between; margin-left: 106px; color: #94a3b8; font-size: 11px; }
.phase-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.phase-panel { padding: 14px; border: 1px solid #e5eaf2; border-radius: 9px; background: #fbfcfe; }
.phase-panel header { display: flex; align-items: center; gap: 9px; margin-bottom: 12px; }
.phase-panel header > div { display: flex; flex-direction: column; }
.phase-panel header strong { color: #26364b; font-size: 13px; }
.phase-panel header small { color: #8a97aa; font-size: 11px; }
.phase-chip { display: grid; width: 32px; height: 28px; place-items: center; border-radius: 7px; color: white; font-size: 12px; font-weight: 800; }
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
</style>
