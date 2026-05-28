<script setup lang="ts">
import type { MetricSummary } from '../../../api/admin/coi-analysis'
import { conditionLabel, formatNumber, statFor } from './reportHelpers'

const props = defineProps<{
  metrics: MetricSummary[]
  conditionColumns: string[]
}>()

function conditionMean(metric: MetricSummary, condition: string): number | null {
  return statFor(metric, condition)?.mean ?? null
}

function chartScale(metric: MetricSummary): { min: number; max: number; span: number } {
  const means = props.conditionColumns
    .map((c) => conditionMean(metric, c))
    .filter((v): v is number => v !== null)
  if (means.length === 0) return { min: 0, max: 1, span: 1 }
  const min = Math.min(0, ...means)
  const max = Math.max(...means)
  return { min, max, span: max - min || 1 }
}

function barStyle(metric: MetricSummary, condition: string) {
  const value = conditionMean(metric, condition)
  const scale = chartScale(metric)
  if (value === null) return { left: '0%', width: '0%' }
  const start = Math.min(0, value)
  const end = Math.max(0, value)
  return {
    left: `${((start - scale.min) / scale.span) * 100}%`,
    width: `${Math.max(2, ((end - start) / scale.span) * 100)}%`,
  }
}
</script>

<template>
  <el-card class="analysis-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>各指标均值对比</strong>
        <span>条形长度按当前指标各条件均值缩放</span>
      </div>
    </template>
    <div class="metric-charts">
      <div v-for="metric in metrics" :key="metric.metric" class="metric-chart">
        <div class="metric-chart-title">{{ metric.label }}</div>
        <div v-for="condition in conditionColumns" :key="condition" class="chart-row">
          <div class="chart-label">{{ conditionLabel(condition) }}</div>
          <div class="chart-track">
            <div class="chart-zero"></div>
            <div class="chart-bar" :class="`condition-${condition}`" :style="barStyle(metric, condition)"></div>
          </div>
          <div class="chart-value">{{ formatNumber(conditionMean(metric, condition)) }}</div>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.analysis-card {
  border: 1px solid #e3e9f2;
  border-radius: 8px;
}

.card-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.card-title span {
  color: #748197;
  font-size: 12px;
}

.metric-charts {
  display: grid;
  grid-template-columns: repeat(3, minmax(240px, 1fr));
  gap: 14px;
}

.metric-chart {
  min-width: 0;
  padding: 12px;
  border: 1px solid #e3e9f2;
  border-radius: 8px;
  background: #f8fafc;
}

.metric-chart-title {
  margin-bottom: 10px;
  color: #172033;
  font-size: 13px;
  font-weight: 700;
}

.chart-row {
  display: grid;
  grid-template-columns: 72px minmax(100px, 1fr) 52px;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.chart-label {
  color: #748197;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chart-track {
  position: relative;
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #e8eef7;
}

.chart-zero {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 1px;
  background: rgba(23, 32, 51, 0.28);
}

.chart-bar {
  position: absolute;
  top: 0;
  bottom: 0;
  min-width: 2px;
  border-radius: 999px;
}

.condition-no_assistance { background: #64748b; }
.condition-glasses { background: #2563eb; }
.condition-app_notification { background: #16a34a; }

.chart-value {
  color: #172033;
  font-size: 12px;
  font-weight: 600;
  text-align: right;
}

@media (max-width: 1100px) {
  .metric-charts {
    grid-template-columns: 1fr;
  }
}
</style>
