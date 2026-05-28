<script setup lang="ts">
import type { QStatisticalTestResult } from '../../../api/admin/questionnaire-analysis'
import { formatNumber, pValueText, testLabel, testStatusLabel } from './reportHelpers'

defineProps<{
  loading: boolean
  tests: QStatisticalTestResult[]
}>()
</script>

<template>
  <el-card class="analysis-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>推断统计结果</strong>
        <span>根据正态性自动选择检验，并报告 p 值与 effect size</span>
      </div>
    </template>
    <el-table v-loading="loading" :data="tests" border class="compact-table">
      <el-table-column prop="label" label="维度" min-width="180" />
      <el-table-column label="检验" min-width="200">
        <template #default="{ row }"><strong>{{ testLabel(row.test) }}</strong></template>
      </el-table-column>
      <el-table-column label="统计量" min-width="120" align="center">
        <template #default="{ row }">
          <span v-if="row.statistic !== null">{{ row.statistic_name || '' }}={{ formatNumber(row.statistic) }}</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="p" width="90" align="center">
        <template #default="{ row }">{{ pValueText(row.p_value) }}</template>
      </el-table-column>
      <el-table-column label="Effect size" min-width="170">
        <template #default="{ row }">
          <span v-if="row.effect_size_name">{{ row.effect_size_name }}={{ formatNumber(row.effect_size) }}</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="100">
        <template #default="{ row }">{{ testStatusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column prop="note" label="说明" min-width="280" />
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
