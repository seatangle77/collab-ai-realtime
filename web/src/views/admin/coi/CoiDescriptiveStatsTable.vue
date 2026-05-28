<script setup lang="ts">
import type { CoiAnalysisMode, MetricSummary } from '../../../api/admin/coi-analysis'
import { conditionLabel, formatNumber, meanDiffText, statFor } from './reportHelpers'

defineProps<{
  loading: boolean
  metrics: MetricSummary[]
  conditionColumns: string[]
  mode: CoiAnalysisMode
}>()
</script>

<template>
  <el-card class="analysis-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>描述性统计</strong>
        <span>按所选样本即时计算，结果未入库</span>
      </div>
    </template>
    <el-table v-loading="loading" :data="metrics" border class="descriptive-table">
      <el-table-column label="指标" min-width="200" fixed>
        <template #default="{ row }">
          <strong class="metric-label">{{ row.label }}</strong>
        </template>
      </el-table-column>
      <el-table-column
        v-for="condition in conditionColumns"
        :key="condition"
        :label="conditionLabel(condition)"
        min-width="190"
      >
        <template #default="{ row }">
          <div v-if="statFor(row, condition)?.n" class="stat-cell">
            <div><span>n</span><strong>{{ statFor(row, condition)?.n }}</strong></div>
            <div><span>M</span><strong>{{ formatNumber(statFor(row, condition)?.mean) }}</strong></div>
            <div><span>SD</span><strong>{{ formatNumber(statFor(row, condition)?.sd) }}</strong></div>
            <div><span>Med</span><strong>{{ formatNumber(statFor(row, condition)?.median) }}</strong></div>
            <div class="stat-range">
              <span>Min-Max</span>
              <strong>{{ formatNumber(statFor(row, condition)?.min) }}–{{ formatNumber(statFor(row, condition)?.max) }}</strong>
            </div>
          </div>
          <span v-else class="empty-stat">n=0</span>
        </template>
      </el-table-column>
      <el-table-column v-if="mode === 'two_conditions'" label="均值差" min-width="140">
        <template #default="{ row }">
          <div class="diff-cell">
            <strong>{{ meanDiffText(row) }}</strong>
            <span>智能眼镜 - 无辅助</span>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.analysis-card {
  border: 1px solid #e3e9f2;
  border-radius: 8px;
}

.analysis-card :deep(.el-card__body) {
  padding: 0;
}

.card-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.card-title span {
  color: #748197;
  font-size: 13px;
}

.descriptive-table :deep(.el-table__cell) {
  padding: 8px 10px;
}

.descriptive-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #324055;
  font-size: 13px;
  font-weight: 750;
}

.metric-label {
  color: #172033;
  font-size: 13px;
}

.stat-cell {
  display: grid;
  grid-template-columns: repeat(2, minmax(56px, 1fr));
  gap: 4px 10px;
  font-size: 12px;
}

.stat-cell div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.stat-cell span {
  color: #748197;
}

.stat-cell strong {
  color: #172033;
  font-weight: 700;
}

.stat-range {
  grid-column: 1 / -1;
}

.diff-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diff-cell strong {
  color: #172033;
  font-size: 13px;
  font-weight: 760;
}

.diff-cell span {
  color: #748197;
  font-size: 12px;
}

.empty-stat {
  color: #9aa6b8;
  font-size: 12px;
}
</style>
