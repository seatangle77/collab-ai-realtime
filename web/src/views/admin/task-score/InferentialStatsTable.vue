<script setup lang="ts">
import type { NormalityConditionResult, StatisticalTestResult } from '../../../api/admin/task-score-analysis'
import {
  conditionLabel,
  formatNumber,
  normalityStatusLabel,
  normalityTagType,
  pValueText,
  testLabel,
  testStatusLabel,
} from './reportHelpers'

defineProps<{
  loading: boolean
  primaryTests: StatisticalTestResult[]
  baselineTests: StatisticalTestResult[]
  baselineNormality: NormalityConditionResult[]
}>()
</script>

<template>
  <el-card class="analysis-card inference-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>推断统计结果</strong>
        <span>根据正态性自动选择检验，并报告 p 值与 effect size</span>
      </div>
    </template>
    <el-table v-loading="loading" :data="primaryTests" border class="compact-table">
      <el-table-column prop="label" label="主要结果指标" min-width="180" />
      <el-table-column label="检验" min-width="180">
        <template #default="{ row }"><strong>{{ testLabel(row.test) }}</strong></template>
      </el-table-column>
      <el-table-column label="统计量" min-width="110" align="center">
        <template #default="{ row }">{{ row.statistic_name || '—' }}={{ formatNumber(row.statistic) }}</template>
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

    <el-collapse class="baseline-collapse">
      <el-collapse-item title="AIS / Best IS 基线检查的正态性与推断统计" name="baseline">
        <el-table :data="baselineNormality" border class="compact-table">
          <el-table-column prop="label" label="基线指标" min-width="170" />
          <el-table-column label="条件" min-width="110">
            <template #default="{ row }">{{ conditionLabel(row.condition) }}</template>
          </el-table-column>
          <el-table-column prop="n" label="n" width="70" align="center" />
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
        <el-table :data="baselineTests" border class="compact-table baseline-recommendations">
          <el-table-column prop="label" label="基线指标" min-width="170" />
          <el-table-column label="检验" min-width="180">
            <template #default="{ row }">{{ testLabel(row.test) }}</template>
          </el-table-column>
          <el-table-column label="统计量" min-width="110" align="center">
            <template #default="{ row }">{{ row.statistic_name || '—' }}={{ formatNumber(row.statistic) }}</template>
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
          <el-table-column prop="note" label="说明" min-width="280" />
        </el-table>
      </el-collapse-item>
    </el-collapse>
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

.card-title strong {
  font-size: 14px;
  font-weight: 600;
  color: #1e2d40;
}

.card-title span {
  color: #64748b;
  font-size: 12px;
}

.compact-table :deep(.el-table__cell) {
  padding: 8px 10px;
}

.compact-table :deep(.el-table__header th) {
  background: #f8fafc;
  color: #324055;
  font-size: 13px;
  font-weight: 600;
}

.baseline-collapse {
  border-top: 1px solid #e3e9f2;
}

.baseline-collapse :deep(.el-collapse-item__header) {
  padding: 0 14px;
  color: #324055;
  font-weight: 700;
}

.baseline-collapse :deep(.el-collapse-item__content) {
  padding: 0;
}

.baseline-recommendations {
  margin-top: 12px;
}
</style>
