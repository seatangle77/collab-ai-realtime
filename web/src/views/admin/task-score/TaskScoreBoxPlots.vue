<script setup lang="ts">
import { computed } from 'vue'
import type { TaskScoreObservation } from '../../../api/admin/task-score-analysis'
import { conditionLabel, formatNumber } from './reportHelpers'

type PlotMetricKey = 'gs' | 'weak_synergy' | 'strong_synergy'

const props = defineProps<{
  observations: TaskScoreObservation[]
  conditionColumns: string[]
  charts?: Record<string, string>
}>()

const PLOT_METRICS: Array<{ key: PlotMetricKey; label: string; note: string }> = [
  { key: 'gs', label: 'GS 小组最终分数', note: '任务分数越低表示小组最终表现越好' },
  { key: 'weak_synergy', label: '弱协同值（AIS - GS）', note: '正值表示小组表现优于成员平均个人水平' },
  { key: 'strong_synergy', label: '强协同值（Best IS - GS）', note: '正值表示小组表现优于组内最佳个人水平' },
]

interface BoxStats {
  condition: string
  n: number
  min: number
  q1: number
  median: number
  q3: number
  max: number
}

interface BoxPlot {
  key: PlotMetricKey
  label: string
  note: string
  min: number
  max: number
  ticks: number[]
  boxes: BoxStats[]
}

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0
  if (sorted.length === 1) return sorted[0]!
  const pos = (sorted.length - 1) * p
  const lower = Math.floor(pos)
  const upper = Math.ceil(pos)
  if (lower === upper) return sorted[lower]!
  return sorted[lower]! + (sorted[upper]! - sorted[lower]!) * (pos - lower)
}

function statsFor(values: number[], condition: string): BoxStats | null {
  const sorted = [...values].sort((a, b) => a - b)
  if (sorted.length === 0) return null
  return {
    condition,
    n: sorted.length,
    min: sorted[0]!,
    q1: percentile(sorted, 0.25),
    median: percentile(sorted, 0.5),
    q3: percentile(sorted, 0.75),
    max: sorted[sorted.length - 1]!,
  }
}

function paddedDomain(values: number[]): { min: number; max: number } {
  if (values.length === 0) return { min: 0, max: 1 }
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const span = rawMax - rawMin || Math.max(1, Math.abs(rawMax) || 1)
  const pad = span * 0.12
  return { min: rawMin - pad, max: rawMax + pad }
}

function ticksFor(min: number, max: number): number[] {
  const mid = (min + max) / 2
  return [max, mid, min]
}

const plots = computed<BoxPlot[]>(() => PLOT_METRICS.map((metric) => {
  const boxes = props.conditionColumns
    .map((condition) => statsFor(
      props.observations
        .filter((obs) => obs.condition === condition)
        .map((obs) => obs[metric.key]),
      condition,
    ))
    .filter((box): box is BoxStats => box !== null)
  const allValues = boxes.flatMap((box) => [box.min, box.q1, box.median, box.q3, box.max])
  const domain = paddedDomain(allValues)
  return {
    key: metric.key,
    label: metric.label,
    note: metric.note,
    min: domain.min,
    max: domain.max,
    ticks: ticksFor(domain.min, domain.max),
    boxes,
  }
}))

function yFor(value: number, plot: BoxPlot): number {
  const top = 24
  const bottom = 180
  const span = plot.max - plot.min || 1
  return bottom - ((value - plot.min) / span) * (bottom - top)
}

function xFor(index: number, total: number): number {
  if (total <= 1) return 240
  return 96 + index * (288 / (total - 1))
}

function conditionColor(condition: string): string {
  if (condition === 'glasses') return '#2563eb'
  if (condition === 'app_notification') return '#16a34a'
  return '#64748b'
}
</script>

<template>
  <el-card class="analysis-card boxplot-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>主要结果箱线图</strong>
        <span>GS、弱协同值、强协同值按条件展示分布</span>
      </div>
    </template>

    <!-- matplotlib 图（优先） -->
    <img
      v-if="charts?.['box_plots']"
      :src="charts['box_plots']"
      alt="主要结果箱线图"
      style="width: 100%; display: block; border-radius: 4px;"
    />

    <!-- 旧 SVG 兜底 -->
    <div v-else class="boxplot-grid">
      <div v-for="plot in plots" :key="plot.key" class="boxplot-panel">
        <div class="boxplot-title">{{ plot.label }}</div>
        <svg class="boxplot-svg" viewBox="0 0 420 230" role="img" :aria-label="plot.label">
          <line x1="62" y1="24" x2="62" y2="180" class="axis-line" />
          <line x1="62" y1="180" x2="390" y2="180" class="axis-line" />

          <g v-for="tick in plot.ticks" :key="tick">
            <line x1="58" x2="390" :y1="yFor(tick, plot)" :y2="yFor(tick, plot)" class="grid-line" />
            <text x="52" :y="yFor(tick, plot) + 4" text-anchor="end" class="tick-label">
              {{ formatNumber(tick) }}
            </text>
          </g>

          <g v-for="(box, index) in plot.boxes" :key="box.condition">
            <line
              :x1="xFor(index, plot.boxes.length)"
              :x2="xFor(index, plot.boxes.length)"
              :y1="yFor(box.min, plot)"
              :y2="yFor(box.max, plot)"
              class="whisker"
            />
            <line
              :x1="xFor(index, plot.boxes.length) - 18"
              :x2="xFor(index, plot.boxes.length) + 18"
              :y1="yFor(box.min, plot)"
              :y2="yFor(box.min, plot)"
              class="whisker"
            />
            <line
              :x1="xFor(index, plot.boxes.length) - 18"
              :x2="xFor(index, plot.boxes.length) + 18"
              :y1="yFor(box.max, plot)"
              :y2="yFor(box.max, plot)"
              class="whisker"
            />
            <rect
              :x="xFor(index, plot.boxes.length) - 24"
              :y="yFor(box.q3, plot)"
              width="48"
              :height="Math.max(4, yFor(box.q1, plot) - yFor(box.q3, plot))"
              rx="4"
              :fill="conditionColor(box.condition)"
              class="box"
            />
            <line
              :x1="xFor(index, plot.boxes.length) - 24"
              :x2="xFor(index, plot.boxes.length) + 24"
              :y1="yFor(box.median, plot)"
              :y2="yFor(box.median, plot)"
              class="median-line"
            />
            <text :x="xFor(index, plot.boxes.length)" y="202" text-anchor="middle" class="condition-label">
              {{ conditionLabel(box.condition) }}
            </text>
            <text :x="xFor(index, plot.boxes.length)" y="218" text-anchor="middle" class="n-label">
              n={{ box.n }}
            </text>
          </g>
        </svg>
        <div class="boxplot-note">{{ plot.note }}</div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.analysis-card {
  border: 1px solid #e3e9f2;
  border-radius: 8px;
}

.boxplot-card :deep(.el-card__body) {
  padding: 14px;
}

.card-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.card-title strong {
  color: #1e2d40;
  font-size: 14px;
  font-weight: 600;
}

.card-title span {
  color: #64748b;
  font-size: 12px;
}

.boxplot-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(260px, 1fr));
  gap: 14px;
}

.boxplot-panel {
  min-width: 0;
  padding: 12px;
  border: 1px solid #e3e9f2;
  border-radius: 8px;
  background: #f8fafc;
}

.boxplot-title {
  color: #172033;
  font-size: 13px;
  font-weight: 700;
}

.boxplot-svg {
  display: block;
  width: 100%;
  height: 230px;
}

.axis-line,
.whisker {
  stroke: #64748b;
  stroke-width: 1.4;
}

.grid-line {
  stroke: #d9e2ef;
  stroke-width: 1;
}

.box {
  fill-opacity: 0.78;
}

.median-line {
  stroke: #111827;
  stroke-width: 2;
}

.tick-label,
.condition-label,
.n-label {
  fill: #64748b;
  font-size: 11px;
}

.condition-label {
  fill: #172033;
  font-weight: 600;
}

.boxplot-note {
  color: #64748b;
  font-size: 12px;
}

@media (max-width: 1100px) {
  .boxplot-grid {
    grid-template-columns: 1fr;
  }
}
</style>
