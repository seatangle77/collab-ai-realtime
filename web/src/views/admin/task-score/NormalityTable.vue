<script setup lang="ts">
import type { NormalityConditionResult } from '../../../api/admin/task-score-analysis'
import { conditionLabel, formatNumber, normalityStatusLabel, normalityTagType } from './reportHelpers'

defineProps<{
  loading: boolean
  items: NormalityConditionResult[]
}>()
</script>

<template>
  <el-card class="analysis-card inference-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>正态性检查</strong>
        <span>Shapiro-Wilk test，主要结果优先用于后续检验选择</span>
      </div>
    </template>
    <el-table v-loading="loading" :data="items" border class="compact-table">
      <el-table-column prop="label" label="主要结果指标" min-width="180" />
      <el-table-column label="条件" min-width="110">
        <template #default="{ row }">{{ conditionLabel(row.condition) }}</template>
      </el-table-column>
      <el-table-column prop="n" label="n" width="70" align="center" />
      <el-table-column label="W" width="90" align="center">
        <template #default="{ row }">{{ formatNumber(row.statistic) }}</template>
      </el-table-column>
      <el-table-column label="p" width="90" align="center">
        <template #default="{ row }">{{ formatNumber(row.p_value) }}</template>
      </el-table-column>
      <el-table-column label="判断" min-width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="normalityTagType(row)">
            {{ normalityStatusLabel(row) }}
          </el-tag>
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

.inference-card :deep(.el-card__body) {
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

.compact-table :deep(.el-table__cell) {
  padding: 8px 10px;
}

.compact-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #324055;
  font-size: 13px;
  font-weight: 750;
}
</style>
