<script setup lang="ts">
import type { MetricSummary } from '../../../api/admin/coi-analysis'
import { conditionLabel, formatNumber, statFor } from './reportHelpers'

const props = defineProps<{
  metrics: MetricSummary[]
  conditionColumns: string[]
}>()

const CATEGORY_METRICS = [
  { key: 'te_ratio', label: 'Triggering', color: '#64748b' },
  { key: 'ex_ratio', label: 'Exploration', color: '#2563eb' },
  { key: 'in_ratio', label: 'Integration', color: '#16a34a' },
  { key: 're_ratio', label: 'Resolution', color: '#dc2626' },
]

function metricMean(metricKey: string, condition: string): number {
  const metric = props.metrics.find((item) => item.metric === metricKey)
  if (!metric) return 0
  return statFor(metric, condition)?.mean ?? 0
}

function higherOrderMean(condition: string): number {
  return metricMean('higher_order_ratio', condition)
}

function segmentStyle(metricKey: string, condition: string) {
  return { width: `${Math.max(0, metricMean(metricKey, condition) * 100)}%` }
}

function highOrderStyle(condition: string) {
  return { width: `${Math.max(1, higherOrderMean(condition) * 100)}%` }
}
</script>

<template>
  <el-card class="analysis-card composition-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>CoI 话语结构与高阶认知参与</strong>
        <span>比例按条件聚合展示</span>
      </div>
    </template>

    <div class="composition-grid">
      <section class="chart-panel">
        <div class="chart-title">四类 CoI 话语比例</div>
        <div class="stacked-chart">
          <div v-for="condition in conditionColumns" :key="condition" class="stacked-row">
            <div class="chart-label">{{ conditionLabel(condition) }}</div>
            <div class="stacked-track">
              <div
                v-for="category in CATEGORY_METRICS"
                :key="category.key"
                class="stacked-segment"
                :style="{ ...segmentStyle(category.key, condition), background: category.color }"
                :title="`${category.label}: ${formatNumber(metricMean(category.key, condition))}`"
              />
            </div>
          </div>
        </div>
        <div class="legend">
          <span v-for="category in CATEGORY_METRICS" :key="category.key" class="legend-item">
            <i :style="{ background: category.color }"></i>{{ category.label }}
          </span>
        </div>
      </section>

      <section class="chart-panel">
        <div class="chart-title">高阶认知参与比例（IN + RE）</div>
        <div class="bar-chart">
          <div v-for="condition in conditionColumns" :key="condition" class="bar-row">
            <div class="chart-label">{{ conditionLabel(condition) }}</div>
            <div class="bar-track">
              <div class="bar-fill" :style="highOrderStyle(condition)"></div>
            </div>
            <div class="bar-value">{{ formatNumber(higherOrderMean(condition)) }}</div>
          </div>
        </div>
      </section>
    </div>
  </el-card>
</template>

<style scoped>
.analysis-card {
  border: 1px solid #e3e9f2;
  border-radius: 8px;
}

.composition-card :deep(.el-card__body) {
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

.composition-grid {
  display: grid;
  grid-template-columns: minmax(320px, 1.3fr) minmax(280px, 1fr);
  gap: 14px;
}

.chart-panel {
  min-width: 0;
  padding: 12px;
  border: 1px solid #e3e9f2;
  border-radius: 8px;
  background: #f8fafc;
}

.chart-title {
  margin-bottom: 12px;
  color: #172033;
  font-size: 13px;
  font-weight: 700;
}

.stacked-chart,
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stacked-row,
.bar-row {
  display: grid;
  grid-template-columns: 74px minmax(130px, 1fr) 44px;
  align-items: center;
  gap: 8px;
}

.stacked-row {
  grid-template-columns: 74px minmax(130px, 1fr);
}

.chart-label {
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stacked-track,
.bar-track {
  display: flex;
  height: 18px;
  overflow: hidden;
  border-radius: 999px;
  background: #e8eef7;
}

.stacked-segment {
  min-width: 1px;
}

.bar-fill {
  border-radius: 999px;
  background: #16a34a;
}

.bar-value {
  color: #172033;
  font-size: 12px;
  font-weight: 600;
  text-align: right;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #64748b;
  font-size: 11px;
}

.legend-item i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

@media (max-width: 1100px) {
  .composition-grid {
    grid-template-columns: 1fr;
  }
}
</style>
