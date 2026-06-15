<script setup lang="ts">
import type { EnaStatTestResult } from '../../../api/admin/ena-analysis'
import { formatNumber, pValueText, testLabel, testStatusLabel } from './reportHelpers'

defineProps<{
  loading: boolean
  tests: EnaStatTestResult[]
}>()
</script>

<template>
  <el-card class="analysis-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>推断统计结果</strong>
        <span>根据正态性自动选择检验；p_adj 为 Benjamini-Hochberg FDR 校正值（跨指标多重比较）</span>
      </div>
    </template>
    <el-table v-loading="loading" :data="tests" border class="compact-table">
      <el-table-column prop="label" label="指标" min-width="220" />
      <el-table-column label="检验" min-width="200">
        <template #default="{ row }"><strong>{{ testLabel(row.test) }}</strong></template>
      </el-table-column>
      <el-table-column label="统计量" min-width="130" align="center">
        <template #default="{ row }">
          <span v-if="row.statistic_name">{{ row.statistic_name }}={{ formatNumber(row.statistic) }}</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="p" width="90" align="center">
        <template #default="{ row }">
          <span :class="{ significant: row.p_value !== null && row.p_value < 0.05 }">
            {{ pValueText(row.p_value) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="p_adj (BH)" width="110" align="center">
        <template #default="{ row }">
          <el-tooltip
            v-if="row.p_value !== null && row.p_value < 0.05 && row.p_value_adjusted !== null && row.p_value_adjusted >= 0.05"
            content="原始 p 显著但 FDR 校正后不显著，解释为趋势性结果"
            placement="top"
          >
            <span class="trend">{{ pValueText(row.p_value_adjusted) }} ↑趋势</span>
          </el-tooltip>
          <span
            v-else
            :class="{ significant: row.p_value_adjusted !== null && row.p_value_adjusted < 0.05 }"
          >
            {{ pValueText(row.p_value_adjusted) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="Effect size" min-width="190">
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
.analysis-card { border: 1px solid #e3e9f2; border-radius: 8px; }
.analysis-card :deep(.el-card__body) { padding: 0; }
.card-title { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.card-title span { color: #748197; font-size: 13px; }
.compact-table :deep(.el-table__cell) { padding: 8px 10px; }
.compact-table :deep(.el-table__header th) { background: #f8fafc; color: #324055; font-size: 13px; font-weight: 600; }
.significant { color: #c0392b; font-weight: 700; }
.trend { color: #d97706; font-weight: 600; }
</style>
