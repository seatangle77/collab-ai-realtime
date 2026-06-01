<script setup lang="ts">
import type { QMetricSummary, QuestionnaireScaleKind } from '../../../api/admin/questionnaire-analysis'
import { conditionLabel, formatNumber, statFor } from './reportHelpers'

const props = defineProps<{
  metrics: QMetricSummary[]
  conditionColumns: string[]
  scale: QuestionnaireScaleKind
  charts?: Record<string, string>
}>()

const CONDITION_COLORS: Record<string, string> = {
  no_assistance: '#64748b',
  glasses: '#2563eb',
  app_notification: '#16a34a',
}

function visibleMetrics(): QMetricSummary[] {
  return props.metrics.filter((metric) => metric.metric !== 'total_avg')
}

function conditionMean(metric: QMetricSummary, condition: string): number | null {
  return statFor(metric, condition)?.mean ?? null
}

function maxMean(): number {
  const values = visibleMetrics().flatMap((metric) =>
    props.conditionColumns
      .map((condition) => conditionMean(metric, condition))
      .filter((value): value is number => value !== null),
  )
  return Math.max(1, ...values)
}

function barStyle(metric: QMetricSummary, condition: string) {
  const value = conditionMean(metric, condition)
  if (value === null) return { height: '0%', background: CONDITION_COLORS[condition] ?? '#64748b' }
  return {
    height: `${Math.max(2, (value / maxMean()) * 100)}%`,
    background: CONDITION_COLORS[condition] ?? '#64748b',
  }
}
</script>

<template>
  <el-card class="analysis-card scale-chart-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>{{ scale === 'srcc' ? 'SRCC 四维度分组柱状图' : 'PCS 两维度分组柱状图' }}</strong>
        <span>每个维度按条件展示平均分</span>
      </div>
    </template>

    <!-- matplotlib 图（优先） -->
    <img
      v-if="charts?.['dimension_bars']"
      :src="charts['dimension_bars']"
      alt="量表维度分组柱状图"
      style="width: 100%; display: block; border-radius: 4px;"
    />

    <!-- 旧 CSS 兜底 -->
    <div v-else class="scale-chart">
      <div v-for="metric in visibleMetrics()" :key="metric.metric" class="dimension-group">
        <div class="bars">
          <div v-for="condition in conditionColumns" :key="condition" class="bar-wrap">
            <div class="bar-value">{{ formatNumber(conditionMean(metric, condition)) }}</div>
            <div class="bar" :style="barStyle(metric, condition)"></div>
          </div>
        </div>
        <div class="dimension-label">{{ metric.label }}</div>
      </div>
    </div>

    <div class="legend">
      <span v-for="condition in conditionColumns" :key="condition" class="legend-item">
        <i :style="{ background: CONDITION_COLORS[condition] ?? '#64748b' }"></i>{{ conditionLabel(condition) }}
      </span>
    </div>
  </el-card>
</template>

<style scoped>
.analysis-card {
  border: 1px solid #e3e9f2;
  border-radius: 8px;
}

.scale-chart-card :deep(.el-card__body) {
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

.scale-chart {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 14px;
  min-height: 260px;
}

.dimension-group {
  display: grid;
  grid-template-rows: 210px auto;
  gap: 8px;
  min-width: 0;
  padding: 12px;
  border: 1px solid #e3e9f2;
  border-radius: 8px;
  background: #f8fafc;
}

.bars {
  display: flex;
  align-items: end;
  justify-content: center;
  gap: 8px;
  height: 210px;
  border-bottom: 1px solid #cbd5e1;
}

.bar-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: end;
  width: 34px;
  height: 100%;
}

.bar {
  width: 24px;
  min-height: 2px;
  border-radius: 5px 5px 0 0;
}

.bar-value {
  margin-bottom: 4px;
  color: #172033;
  font-size: 11px;
  font-weight: 700;
}

.dimension-label {
  min-height: 34px;
  color: #172033;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
  text-align: center;
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
  font-size: 12px;
}

.legend-item i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
</style>
