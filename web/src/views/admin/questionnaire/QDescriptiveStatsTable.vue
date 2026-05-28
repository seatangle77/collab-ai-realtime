<script setup lang="ts">
import type { QMetricSummary } from '../../../api/admin/questionnaire-analysis'
import { conditionLabel, formatNumber, statFor } from './reportHelpers'

defineProps<{
  loading: boolean
  metrics: QMetricSummary[]
  conditionColumns: string[]
  mode: string
}>()
</script>

<template>
  <el-card class="analysis-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>描述性统计</strong>
        <span>M = 均值；SD = 标准差；Med = 中位数</span>
      </div>
    </template>
    <el-table v-loading="loading" :data="metrics" border class="descriptive-table">
      <el-table-column label="维度" min-width="180" fixed>
        <template #default="{ row }">
          <strong>{{ row.label }}</strong>
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
            <div><span>M</span><strong>{{ formatNumber(statFor(row, condition)?.mean ?? null) }}</strong></div>
            <div><span>SD</span><strong>{{ formatNumber(statFor(row, condition)?.sd ?? null) }}</strong></div>
            <div><span>Med</span><strong>{{ formatNumber(statFor(row, condition)?.median ?? null) }}</strong></div>
            <div class="stat-range">
              <span>Min–Max</span>
              <strong>{{ formatNumber(statFor(row, condition)?.min ?? null) }}–{{ formatNumber(statFor(row, condition)?.max ?? null) }}</strong>
            </div>
          </div>
          <span v-else class="empty-stat">n=0</span>
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
  font-size: 12px;
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
  font-size: 13px;
  font-weight: 760;
}

.stat-range {
  grid-column: 1 / -1;
}

.empty-stat {
  color: #9aa6b8;
  font-size: 12px;
}
</style>
