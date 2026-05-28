<script setup lang="ts">
import type { QCronbachAlphaResult } from '../../../api/admin/questionnaire-analysis'
import { cronbachStatusLabel, cronbachTagType, formatNumber } from './reportHelpers'

defineProps<{
  loading: boolean
  reliability: QCronbachAlphaResult[]
}>()
</script>

<template>
  <el-card class="analysis-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>内部一致性（Cronbach's α）</strong>
        <span>α ≥ 0.7 可接受；跨所有条件参与者计算</span>
      </div>
    </template>
    <el-table v-loading="loading" :data="reliability" border class="compact-table">
      <el-table-column prop="label" label="维度" min-width="180" />
      <el-table-column label="题项数" width="80" align="center">
        <template #default="{ row }">{{ row.n_items }}</template>
      </el-table-column>
      <el-table-column label="n（参与者）" width="110" align="center">
        <template #default="{ row }">{{ row.n_obs }}</template>
      </el-table-column>
      <el-table-column label="α" width="110" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'ok'" size="small" :type="cronbachTagType(row)">
            {{ formatNumber(row.alpha) }}
          </el-tag>
          <el-tag v-else size="small" type="info">{{ cronbachStatusLabel(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="note" label="说明" min-width="260" />
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
</style>
