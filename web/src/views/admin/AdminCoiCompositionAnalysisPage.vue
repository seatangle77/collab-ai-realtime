<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { listAdminGroups } from '../../api/admin/groups'
import {
  createCoiCompositionAnalysis,
  type CoiCompositionAnalysisResult,
} from '../../api/admin/coi-composition-analysis'
import type { CoiAnalysisCoderRole, MetricSummary } from '../../api/admin/coi-analysis'
import type { AdminGroup } from '../../types/admin'
import SampleSelector from './task-score/SampleSelector.vue'
import CoiPostHocTable from './coi/CoiPostHocTable.vue'
import { coderRoleLabel, conditionLabel, formatNumber, pValueText, testLabel } from './coi/reportHelpers'
import CoiCodeCompositionCharts from './coi-composition/CoiCodeCompositionCharts.vue'

const conditionColumns = ['no_assistance', 'glasses', 'app_notification']
const coderRole = ref<CoiAnalysisCoderRole>('final')
const loading = ref(false)
const loadingGroups = ref(false)
const groups = ref<AdminGroup[]>([])
const report = ref<CoiCompositionAnalysisResult | null>(null)

const selectedGroupIdsByCondition = reactive<Record<string, string[]>>({
  no_assistance: [],
  glasses: [],
  app_notification: [],
})

const groupOptionsByCondition = computed(() => {
  const grouped: Record<string, AdminGroup[]> = {
    no_assistance: [], glasses: [], app_notification: [],
  }
  for (const group of groups.value) grouped[group.condition]?.push(group)
  return grouped
})

const globalSignificance = computed(() => {
  const test = report.value?.global_test
  if (!test || test.status !== 'ok' || test.p_value == null) return '尚未计算'
  return test.p_value < 0.05 ? '整体构成存在显著差异' : '整体构成未发现显著差异'
})

function statsFor(metric: MetricSummary, condition: string) {
  return metric.conditions.find((item) => item.condition === condition)
}

function percent(value: number | null | undefined): string {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

async function fetchGroupsAndReport() {
  loadingGroups.value = true
  try {
    const response = await listAdminGroups({ page: 1, page_size: 200 })
    groups.value = response.items
    for (const condition of conditionColumns) {
      selectedGroupIdsByCondition[condition] = response.items
        .filter((group) => group.condition === condition)
        .map((group) => group.id)
    }
    if (conditionColumns.every((condition) => (selectedGroupIdsByCondition[condition]?.length ?? 0) > 0)) {
      await fetchReport()
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
}

async function fetchReport() {
  const missing = conditionColumns.filter((condition) => (selectedGroupIdsByCondition[condition]?.length ?? 0) === 0)
  if (missing.length) {
    ElMessage.warning(`请为 ${missing.map(conditionLabel).join('、')} 选择小组`)
    return
  }
  loading.value = true
  try {
    report.value = await createCoiCompositionAnalysis({
      mode: 'three_conditions',
      coder_role: coderRole.value,
      group_ids_by_condition: Object.fromEntries(
        conditionColumns.map((condition) => [condition, selectedGroupIdsByCondition[condition] ?? []]),
      ),
    })
  } catch (error: any) {
    ElMessage.error(error?.message || '生成 CoI 编码构成分析失败')
  } finally {
    loading.value = false
  }
}

onMounted(fetchGroupsAndReport)
</script>

<template>
  <div class="analysis-page composition-page">
    <div class="page-header">
      <div>
        <div class="title-line"><h1>CoI 编码构成分析</h1><el-tag type="success" effect="plain">新方案</el-tag></div>
        <p>只比较 TE、EX、IN、RE 四阶段编码构成；原“认知参与度分析”页面保持不变。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Refresh" :loading="loading" type="primary" @click="fetchReport">重新生成</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon>
      <template #title>统计口径</template>
      每个观点单元可保留多个 CoI 编码。每场会话分别计算“该阶段编码次数 ÷ 四阶段全部编码次数”，四项合计100%；条件均值对每场会话等权。
    </el-alert>

    <el-card class="control-card" shadow="never">
      <el-form label-width="86px" class="control-form">
        <el-form-item label="比较条件">
          <el-tag size="large">无辅助 / 智能眼镜 / APP 通知</el-tag>
        </el-form-item>
        <el-form-item label="编码来源">
          <el-select v-model="coderRole" style="width: 210px" @change="report = null">
            <el-option label="最终协商编码" value="final" />
            <el-option label="研究员 A 独立编码" value="coder_a" />
            <el-option label="研究员 B 独立编码" value="coder_b" />
            <el-option label="AI 编码员 C" value="coder_c" />
          </el-select>
          <el-tag size="large" type="info" style="margin-left: 8px">{{ coderRoleLabel(coderRole) }}</el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <SampleSelector
      v-model="selectedGroupIdsByCondition"
      :condition-columns="conditionColumns"
      :group-options-by-condition="groupOptionsByCondition"
      :loading-groups="loadingGroups"
    />

    <el-row :gutter="16">
      <el-col :xs="24" :md="6">
        <el-card class="summary-card" shadow="never"><div class="summary-label">完整会话</div><div class="summary-value">{{ report?.total_sessions ?? 0 }}</div></el-card>
      </el-col>
      <el-col v-for="condition in conditionColumns" :key="condition" :xs="24" :md="6">
        <el-card class="summary-card" shadow="never"><div class="summary-label">{{ conditionLabel(condition) }}</div><div class="summary-value">{{ report?.sessions_by_condition[condition] ?? 0 }}</div></el-card>
      </el-col>
    </el-row>

    <el-card class="analysis-card global-card" shadow="never">
      <template #header>
        <div class="card-title"><strong>第一步：整体构成检验</strong><span>先判断四阶段整体结构是否因条件而不同</span></div>
      </template>
      <div v-loading="loading" class="global-result">
        <div>
          <span class="result-kicker">{{ report?.global_test.method ?? 'Aitchison-distance PERMANOVA' }}</span>
          <strong>{{ globalSignificance }}</strong>
          <p>{{ report?.global_test.note ?? '生成分析后显示结果。' }}</p>
        </div>
        <dl>
          <div><dt>pseudo-F</dt><dd>{{ formatNumber(report?.global_test.statistic) }}</dd></div>
          <div><dt>p</dt><dd>{{ pValueText(report?.global_test.p_value ?? null) }}</dd></div>
          <div><dt>R²</dt><dd>{{ formatNumber(report?.global_test.effect_size) }}</dd></div>
          <div><dt>置换次数</dt><dd>{{ report?.global_test.permutations ?? '—' }}</dd></div>
        </dl>
      </div>
    </el-card>

    <CoiCodeCompositionCharts
      v-if="report"
      :metrics="report.metrics"
      :observations="report.observations"
      :conditions="conditionColumns"
    />

    <el-card class="analysis-card" shadow="never">
      <template #header><div class="card-title"><strong>四阶段描述性统计</strong><span>数值均为组级编码占比</span></div></template>
      <el-table v-loading="loading" :data="report?.metrics ?? []" border>
        <el-table-column prop="label" label="阶段" min-width="190" />
        <el-table-column v-for="condition in conditionColumns" :key="condition" :label="conditionLabel(condition)" min-width="190">
          <template #default="{ row }">
            <div class="metric-summary"><strong>{{ percent(statsFor(row, condition)?.mean) }}</strong><span>SD {{ percent(statsFor(row, condition)?.sd) }} · Med {{ percent(statsFor(row, condition)?.median) }}</span></div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="analysis-card" shadow="never">
      <template #header><div class="card-title"><strong>第二步：阶段层面的跟进检验</strong><span>仅在 TE/EX/IN/RE 四项之间进行 BH 校正</span></div></template>
      <el-table v-loading="loading" :data="report?.statistical_tests ?? []" border>
        <el-table-column prop="label" label="阶段" min-width="190" />
        <el-table-column label="检验" min-width="180"><template #default="{ row }">{{ testLabel(row.test) }}</template></el-table-column>
        <el-table-column label="统计量" width="120" align="center"><template #default="{ row }">{{ row.statistic_name || '—' }}={{ formatNumber(row.statistic) }}</template></el-table-column>
        <el-table-column label="p" width="90" align="center"><template #default="{ row }">{{ pValueText(row.p_value) }}</template></el-table-column>
        <el-table-column label="p_adj (BH)" width="120" align="center"><template #default="{ row }"><strong>{{ pValueText(row.p_value_adjusted) }}</strong></template></el-table-column>
        <el-table-column label="Effect size" min-width="170"><template #default="{ row }">{{ row.effect_size_name || '—' }}={{ formatNumber(row.effect_size) }}</template></el-table-column>
        <el-table-column prop="note" label="说明" min-width="300" />
      </el-table>
    </el-card>

    <CoiPostHocTable
      v-if="report"
      :loading="loading"
      :post-hoc-tests="report.post_hoc_tests"
    />
  </div>
</template>

<style>
@import './admin-analysis.css';
</style>

<style scoped>
.title-line { display: flex; align-items: center; gap: 9px; }
.title-line h1 { margin: 0; }
.control-form { grid-template-columns: minmax(320px, 1fr) minmax(320px, 1fr); }
.analysis-card { border: 1px solid #e3e9f2; border-radius: 10px; }
.card-title { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.card-title span { color: #748197; font-size: 12px; }
.global-card { border-color: #d9e8df; background: linear-gradient(135deg, #fff, #f7fbf8); }
.global-result { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 28px; }
.global-result > div { display: flex; flex-direction: column; align-items: flex-start; gap: 5px; }
.result-kicker { color: #668173; font-size: 12px; font-weight: 700; text-transform: uppercase; }
.global-result strong { color: #1f3b2d; font-size: 20px; }
.global-result p { margin: 0; color: #6d7c73; font-size: 12px; }
.global-result dl { display: grid; grid-template-columns: repeat(4, minmax(82px, 1fr)); gap: 10px; margin: 0; }
.global-result dl div { padding: 10px 14px; border: 1px solid #dce8e0; border-radius: 8px; background: white; }
.global-result dt { color: #84928a; font-size: 10px; }
.global-result dd { margin: 4px 0 0; color: #254231; font-size: 16px; font-weight: 750; }
.metric-summary { display: flex; flex-direction: column; gap: 3px; }
.metric-summary strong { color: #1f2e43; font-size: 14px; }
.metric-summary span { color: #7b899d; font-size: 11px; }
@media (max-width: 1000px) { .global-result { grid-template-columns: 1fr; } .global-result dl { width: 100%; } }
</style>
