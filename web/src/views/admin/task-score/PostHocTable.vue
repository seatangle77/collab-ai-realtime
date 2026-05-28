<script setup lang="ts">
import type { PostHocResult } from '../../../api/admin/task-score-analysis'
import { conditionLabel, formatNumber, pValueText } from './reportHelpers'

defineProps<{
  loading: boolean
  postHocTests: PostHocResult[]
}>()

function methodLabel(method: PostHocResult['method']): string {
  if (method === 'tukey_hsd') return 'Tukey HSD'
  if (method === 'dunn_bonferroni') return 'Dunn + Bonferroni'
  return '—'
}

function statusLabel(status: PostHocResult['status']): string {
  const labels: Record<PostHocResult['status'], string> = {
    ok: '已计算',
    not_applicable: '不适用',
    insufficient_data: '样本不足',
    dependency_missing: '缺少依赖',
    calculation_error: '无法计算',
  }
  return labels[status]
}
</script>

<template>
  <el-card class="analysis-card post-hoc-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>事后检验（Post-hoc）</strong>
        <span>仅三条件且全局检验 p &lt; 0.05 时执行；Tukey HSD 用于 ANOVA，Dunn + Bonferroni 用于 Kruskal-Wallis</span>
      </div>
    </template>

    <div v-for="item in postHocTests.filter(t => t.role === 'primary')" :key="item.metric" class="post-hoc-section">
      <div class="section-header">
        <span class="metric-label">{{ item.label }}</span>
        <el-tag v-if="item.status === 'ok'" size="small" type="success">{{ methodLabel(item.method) }}</el-tag>
        <el-tag v-else size="small" type="info">{{ statusLabel(item.status) }}</el-tag>
        <span class="section-note">{{ item.note }}</span>
      </div>

      <el-table v-if="item.status === 'ok' && item.pairs.length > 0" :data="item.pairs" border class="compact-table pair-table">
        <el-table-column label="条件 A" min-width="120">
          <template #default="{ row }">{{ conditionLabel(row.condition_a) }}</template>
        </el-table-column>
        <el-table-column label="条件 B" min-width="120">
          <template #default="{ row }">{{ conditionLabel(row.condition_b) }}</template>
        </el-table-column>
        <el-table-column label="均值差 (B − A)" min-width="130" align="center">
          <template #default="{ row }">{{ formatNumber(row.mean_diff) }}</template>
        </el-table-column>
        <el-table-column label="p (校正后)" width="110" align="center">
          <template #default="{ row }">{{ pValueText(row.p_value_adjusted) }}</template>
        </el-table-column>
        <el-table-column label="显著" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.significant === true" size="small" type="danger">*</el-tag>
            <el-tag v-else-if="row.significant === false" size="small" type="info">ns</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-card>
</template>

<style scoped>
.analysis-card {
  border: 1px solid #e3e9f2;
  border-radius: 8px;
}

.post-hoc-card :deep(.el-card__body) {
  padding: 0;
}

.card-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.card-title span {
  color: #748197;
  font-size: 13px;
}

.post-hoc-section {
  padding: 12px 14px;
  border-bottom: 1px solid #f0f4f9;
}

.post-hoc-section:last-child {
  border-bottom: 0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.metric-label {
  font-size: 14px;
  font-weight: 700;
  color: #1f2a3d;
}

.section-note {
  color: #748197;
  font-size: 12px;
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

.pair-table {
  max-width: 600px;
}
</style>
