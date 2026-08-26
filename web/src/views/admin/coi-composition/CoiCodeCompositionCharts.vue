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

const conditionStyles: Record<string, { color: string }> = {
  no_assistance: { color: '#64748b' },
  glasses: { color: '#3b82f6' },
  app_notification: { color: '#f97316' },
}

const BASELINE = 'no_assistance'
const MEAN_SCALE_MAX = 0.4
const DISTRIBUTION_SCALE_MAX = 0.5
const DELTA_SCALE_MAX = 8

function meanFor(metric: string, condition: string): number {
  return props.metrics
    .find((item) => item.metric === metric)
    ?.conditions.find((item) => item.condition === condition)
    ?.mean ?? 0
}

const meanRows = computed(() => phases.map(phase => ({
  ...phase,
  conditions: props.conditions.map(condition => ({
    condition,
    value: meanFor(phase.metric, condition),
  })),
})))

// 差值只用于描述变化方向和大小，不把它解释为统计显著性。
const deltaRows = computed(() => phases.map(phase => ({
  ...phase,
  comparisons: props.conditions
    .filter(condition => condition !== BASELINE)
    .map(condition => ({
      condition,
      delta: (meanFor(phase.metric, condition) - meanFor(phase.metric, BASELINE)) * 100,
    })),
})))

function valuesFor(key: keyof CoiCompositionObservation, condition: string): number[] {
  return props.observations
    .filter((item) => item.condition === condition)
    .map((item) => Number(item[key]))
    .filter(Number.isFinite)
    .sort((a, b) => a - b)
}

function quantile(values: number[], percentile: number): number {
  if (!values.length) return 0
  const index = (values.length - 1) * percentile
  const lower = Math.floor(index)
  const remainder = index - lower
  const lowerValue = values[lower] ?? 0
  const upperValue = values[lower + 1] ?? lowerValue
  return lowerValue + (upperValue - lowerValue) * remainder
}

const distributionRows = computed(() => phases.map(phase => ({
  ...phase,
  conditions: props.conditions.map(condition => {
    const values = valuesFor(phase.key, condition)
    return {
      condition,
      min: values[0] ?? 0,
      q1: quantile(values, 0.25),
      median: quantile(values, 0.5),
      q3: quantile(values, 0.75),
      max: values[values.length - 1] ?? 0,
      mean: meanFor(phase.metric, condition),
    }
  }),
})))

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function signedPoints(value: number): string {
  if (Math.abs(value) < 0.05) return '0.0'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}`
}

function meanWidth(value: number): number {
  return Math.min(100, Math.max(0, value / MEAN_SCALE_MAX * 100))
}

function distributionPosition(value: number): number {
  return Math.min(100, Math.max(0, value / DISTRIBUTION_SCALE_MAX * 100))
}

function deltaWidth(value: number): number {
  return Math.min(50, Math.abs(value) / (DELTA_SCALE_MAX * 2) * 100)
}

function deltaLeft(value: number): number {
  return value < 0 ? 50 - deltaWidth(value) : 50
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
          <span>条件内会话等权平均；所有阶段使用同一 0–40% 刻度</span>
        </div>
        <div class="condition-legend" aria-label="实验条件图例">
          <span v-for="condition in conditions" :key="condition">
            <i :style="{ background: conditionColor(condition) }" />{{ conditionLabel(condition) }}
          </span>
        </div>
      </div>
    </template>

    <div class="mean-chart" role="img" aria-label="四个 CoI 阶段在三个实验条件下的平均编码占比分组条形图">
      <section v-for="row in meanRows" :key="row.metric" class="mean-group">
        <div class="phase-name">
          <strong>{{ row.short }}</strong>
          <span>{{ row.label }}</span>
        </div>
        <div class="mean-lanes">
          <div v-for="entry in row.conditions" :key="entry.condition" class="mean-lane">
            <span class="condition-name">{{ conditionLabel(entry.condition) }}</span>
            <div class="bar-track">
              <i v-for="tick in 5" :key="tick" class="grid-line" :style="{ left: `${(tick - 1) * 25}%` }" />
              <span
                class="mean-bar"
                :style="{ width: `${meanWidth(entry.value)}%`, background: conditionColor(entry.condition) }"
              />
            </div>
            <strong class="mean-value">{{ percent(entry.value) }}</strong>
          </div>
        </div>
      </section>
      <div class="mean-axis" aria-hidden="true">
        <span>0%</span><span>10%</span><span>20%</span><span>30%</span><span>40%</span>
      </div>
    </div>
    <footer class="figure-caption">
      <strong>图 1　CoI 四阶段编码占比的分组水平条形图。</strong>
      <span>条形表示各实验条件内会话等权平均后的阶段占比；所有阶段使用相同的 0–40% 横轴，便于直接比较。</span>
    </footer>
  </el-card>

  <el-card class="chart-card" shadow="never">
    <template #header>
      <div class="card-heading">
        <div>
          <strong>相对无辅助的变化</strong>
          <span>正值表示高于无辅助，负值表示低于无辅助；单位为百分点（pp）</span>
        </div>
        <span class="descriptive-note">描述性差异，不代表统计显著</span>
      </div>
    </template>

    <div class="delta-chart" role="img" aria-label="智能眼镜和 APP 通知相对无辅助条件的四阶段百分点差异">
      <div class="delta-axis" aria-hidden="true">
        <span>−8</span><span>−4</span><span>0</span><span>+4</span><span>+8 pp</span>
      </div>
      <section v-for="row in deltaRows" :key="row.metric" class="delta-group">
        <div class="phase-name">
          <strong>{{ row.short }}</strong>
          <span>{{ row.label }}</span>
        </div>
        <div class="delta-lanes">
          <div v-for="entry in row.comparisons" :key="entry.condition" class="delta-lane">
            <span class="condition-name">{{ conditionLabel(entry.condition) }}</span>
            <div class="delta-track">
              <i class="zero-line" />
              <span
                class="delta-bar"
                :style="{
                  left: `${deltaLeft(entry.delta)}%`,
                  width: `${deltaWidth(entry.delta)}%`,
                  background: conditionColor(entry.condition),
                }"
              />
            </div>
            <strong class="delta-value" :class="{ positive: entry.delta > 0, negative: entry.delta < 0 }">
              {{ signedPoints(entry.delta) }} pp
            </strong>
          </div>
        </div>
      </section>
    </div>
    <footer class="figure-caption">
      <strong>图 2　相对无辅助条件的 CoI 阶段占比差异图。</strong>
      <span>横轴表示智能眼镜或 APP 通知相对无辅助条件的百分点变化（pp）；正值表示占比更高，负值表示占比更低。图中差异为描述性结果，不代表统计显著。</span>
    </footer>
  </el-card>

  <el-collapse class="detail-collapse">
    <el-collapse-item name="distribution">
      <template #title>
        <div class="collapse-title">
          <strong>查看 36 场会话的分布</strong>
          <span>箱线图显示中位数、四分位区间与全距；菱形表示均值</span>
        </div>
      </template>
      <div class="boxplot-grid">
        <section v-for="row in distributionRows" :key="row.metric" class="boxplot-panel">
          <header><strong>{{ row.short }}</strong><span>{{ row.label }}</span></header>
          <div v-for="entry in row.conditions" :key="entry.condition" class="boxplot-row">
            <span class="boxplot-label">{{ conditionLabel(entry.condition) }}</span>
            <div class="boxplot-track">
              <i v-for="tick in 6" :key="tick" class="grid-line" :style="{ left: `${(tick - 1) * 20}%` }" />
              <span
                class="whisker"
                :style="{
                  left: `${distributionPosition(entry.min)}%`,
                  width: `${distributionPosition(entry.max) - distributionPosition(entry.min)}%`,
                  borderColor: conditionColor(entry.condition),
                }"
              />
              <span
                class="quartile-box"
                :style="{
                  left: `${distributionPosition(entry.q1)}%`,
                  width: `${distributionPosition(entry.q3) - distributionPosition(entry.q1)}%`,
                  borderColor: conditionColor(entry.condition),
                  background: `${conditionColor(entry.condition)}22`,
                }"
              />
              <span class="median-line" :style="{ left: `${distributionPosition(entry.median)}%`, background: conditionColor(entry.condition) }" />
              <span class="mean-diamond" :style="{ left: `${distributionPosition(entry.mean)}%`, background: conditionColor(entry.condition) }" />
            </div>
            <strong class="boxplot-value">{{ percent(entry.mean) }}</strong>
          </div>
          <div class="boxplot-axis" aria-hidden="true">
            <span>0%</span><span>10%</span><span>20%</span><span>30%</span><span>40%</span><span>50%</span>
          </div>
        </section>
      </div>
    </el-collapse-item>
  </el-collapse>
</template>

<style scoped>
.chart-card { border: 1px solid #e3e9f2; border-radius: 10px; }
.card-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.card-heading > div:first-child { display: flex; flex-direction: column; gap: 4px; }
.card-heading strong { color: #26364b; }
.card-heading span { color: #718096; font-size: 12px; }
.condition-legend { display: flex; gap: 14px; flex-wrap: wrap; }
.condition-legend span { display: flex; align-items: center; gap: 5px; color: #475569; font-size: 12px; font-weight: 650; }
.condition-legend i { width: 9px; height: 9px; border-radius: 50%; }
.descriptive-note { padding: 5px 9px; border-radius: 5px; background: #fff7ed; color: #9a5b13 !important; white-space: nowrap; }
.phase-name { display: flex; flex-direction: column; align-items: flex-end; justify-content: center; }
.phase-name strong { color: #26364b; font-size: 15px; }
.phase-name span { color: #8a97aa; font-size: 10px; }
.condition-name { overflow: hidden; color: #64748b; font-size: 11px; text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.grid-line { position: absolute; z-index: 0; top: 0; bottom: 0; border-left: 1px dashed #e4eaf2; }

.mean-chart { padding: 4px 12px 0; }
.mean-group { display: grid; grid-template-columns: 116px minmax(0, 1fr); gap: 20px; padding: 17px 0; border-bottom: 1px solid #eef2f6; }
.mean-group:last-of-type { border-bottom: 0; }
.mean-lanes { display: flex; flex-direction: column; gap: 8px; }
.mean-lane { display: grid; grid-template-columns: 78px minmax(0, 1fr) 54px; align-items: center; gap: 10px; min-height: 23px; }
.bar-track { position: relative; height: 22px; }
.mean-bar { position: absolute; z-index: 1; top: 2px; left: 0; height: 18px; border-radius: 3px; }
.mean-value { color: #344054; font-size: 12px; font-variant-numeric: tabular-nums; }
.mean-axis { display: flex; justify-content: space-between; margin: 5px 66px 0 234px; color: #94a3b8; font-size: 11px; }
.figure-caption { display: flex; flex-direction: column; gap: 4px; margin: 18px 12px 2px 148px; padding-top: 12px; border-top: 1px solid #eef2f6; color: #66758a; font-size: 11px; line-height: 1.65; }
.figure-caption strong { color: #3f4f63; font-weight: 650; }

.delta-chart { padding: 4px 12px 0; }
.delta-axis { display: flex; justify-content: space-between; margin: 0 66px 2px 234px; color: #94a3b8; font-size: 11px; }
.delta-group { display: grid; grid-template-columns: 116px minmax(0, 1fr); gap: 20px; padding: 15px 0; border-top: 1px solid #eef2f6; }
.delta-lanes { display: flex; flex-direction: column; gap: 9px; }
.delta-lane { display: grid; grid-template-columns: 78px minmax(0, 1fr) 66px; align-items: center; gap: 10px; min-height: 24px; }
.delta-track { position: relative; height: 20px; background: linear-gradient(to right, transparent 24.8%, #e7ecf3 25%, transparent 25.2%, transparent 74.8%, #e7ecf3 75%, transparent 75.2%); }
.zero-line { position: absolute; z-index: 0; top: 0; bottom: 0; left: 50%; border-left: 1.5px solid #9aa7b8; }
.delta-bar { position: absolute; z-index: 1; top: 3px; height: 14px; border-radius: 2px; }
.delta-value { color: #475569; font-size: 12px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.delta-value.positive::before { content: '↑ '; }
.delta-value.negative::before { content: '↓ '; }

.detail-collapse { overflow: hidden; border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; }
.detail-collapse :deep(.el-collapse-item__header) { height: auto; min-height: 62px; padding: 0 20px; border-bottom: 0; }
.detail-collapse :deep(.el-collapse-item__wrap) { border-top: 1px solid #eef2f6; border-bottom: 0; }
.detail-collapse :deep(.el-collapse-item__content) { padding: 18px 20px 20px; }
.collapse-title { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; }
.collapse-title strong { color: #26364b; }
.collapse-title span { color: #7f8da1; font-size: 12px; font-weight: 400; }
.boxplot-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px 36px; }
.boxplot-panel header { display: flex; align-items: baseline; gap: 8px; margin-bottom: 10px; color: #26364b; }
.boxplot-panel header strong { display: grid; width: 31px; height: 27px; place-items: center; border-radius: 6px; background: #edf1f6; font-size: 12px; }
.boxplot-panel header span { color: #718096; font-size: 12px; }
.boxplot-row { display: grid; grid-template-columns: 72px minmax(0, 1fr) 48px; align-items: center; gap: 8px; min-height: 31px; }
.boxplot-label { color: #64748b; font-size: 10px; text-align: right; white-space: nowrap; }
.boxplot-track { position: relative; height: 22px; }
.whisker { position: absolute; z-index: 1; top: 10px; border-top: 1.5px solid; }
.whisker::before, .whisker::after { position: absolute; top: -4px; height: 8px; border-left: 1.5px solid; border-color: inherit; content: ''; }
.whisker::before { left: 0; }
.whisker::after { right: 0; }
.quartile-box { position: absolute; z-index: 2; top: 5px; height: 12px; border: 1.5px solid; border-radius: 2px; }
.median-line { position: absolute; z-index: 3; top: 5px; width: 2px; height: 12px; margin-left: -1px; }
.mean-diamond { position: absolute; z-index: 4; top: 8px; width: 7px; height: 7px; margin-left: -3.5px; transform: rotate(45deg); border: 1px solid white; }
.boxplot-value { color: #475569; font-size: 11px; font-variant-numeric: tabular-nums; }
.boxplot-axis { display: flex; justify-content: space-between; margin: 2px 56px 0 80px; color: #94a3b8; font-size: 9px; }

@media (max-width: 1100px) {
  .boxplot-grid { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .card-heading { flex-direction: column; }
  .mean-group, .delta-group { grid-template-columns: 52px minmax(0, 1fr); gap: 8px; }
  .phase-name span { display: none; }
  .condition-name { text-align: left; }
  .mean-lane, .delta-lane { grid-template-columns: 66px minmax(0, 1fr) 58px; gap: 6px; }
  .mean-axis, .delta-axis { margin-left: 132px; margin-right: 68px; }
  .figure-caption { margin-left: 12px; }
  .condition-legend { display: none; }
  .descriptive-note { white-space: normal; }
}
</style>
