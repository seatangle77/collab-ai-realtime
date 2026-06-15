<script setup lang="ts">
import { computed, ref } from 'vue'
import { Download, ZoomIn } from '@element-plus/icons-vue'
import type { MetricSummary } from '../../../api/admin/coi-analysis'
import { conditionLabel, formatNumber, statFor } from './reportHelpers'

const props = defineProps<{
  metrics: MetricSummary[]
  conditionColumns: string[]
  charts?: Record<string, string>
}>()

const CATEGORY_METRICS = [
  { key: 'te_ratio', label: 'Triggering', color: '#64748b' },
  { key: 'ex_ratio', label: 'Exploration', color: '#2563eb' },
  { key: 'in_ratio', label: 'Integration', color: '#16a34a' },
  { key: 're_ratio', label: 'Resolution', color: '#dc2626' },
]

const chartLanguage = ref<'zh' | 'en'>('zh')
const chartLabels = {
  zh: {
    cardTitle: 'CoI 话语结构与高阶认知参与',
    cardDesc: '比例按条件聚合展示',
    leftTitle: '四类 CoI 话语比例',
    rightTitle: '高阶认知参与比例（IN + RE）',
    alt: 'CoI 话语结构与高阶认知参与',
  },
  en: {
    cardTitle: 'CoI Discourse Structure and Higher-Order Cognitive Engagement',
    cardDesc: 'Proportions aggregated by condition',
    leftTitle: 'CoI Discourse Structure Proportions',
    rightTitle: 'Higher-Order Cognitive Engagement Proportions (IN + RE)',
    alt: 'CoI discourse structure and higher-order cognitive engagement',
  },
}
const CONDITION_LABELS_EN: Record<string, string> = {
  no_assistance: 'No Assistance',
  glasses: 'Smart Glasses',
  app_notification: 'App Notification',
}

const hasEnglishChart = computed(() => Boolean(props.charts?.['composition_en']))
const activeLabels = computed(() => chartLabels[chartLanguage.value])
const activeChartKey = computed(() => chartLanguage.value === 'en' && hasEnglishChart.value ? 'composition_en' : 'composition')
const activeChartSrc = computed(() => props.charts?.[activeChartKey.value] ?? '')
const previewVisible = ref(false)
const activeChartFileName = computed(() =>
  `coi-composition-${chartLanguage.value}-${new Date().toISOString().slice(0, 10)}.png`
)

function conditionLabelFor(condition: string): string {
  return chartLanguage.value === 'en' ? (CONDITION_LABELS_EN[condition] ?? condition) : conditionLabel(condition)
}

function downloadActiveChart() {
  if (!activeChartSrc.value) return
  const link = document.createElement('a')
  link.href = activeChartSrc.value
  link.download = activeChartFileName.value
  link.click()
}

function metricMean(metricKey: string, condition: string): number {
  const metric = props.metrics.find((item) => item.metric === metricKey)
  if (!metric) return 0
  return statFor(metric, condition)?.mean ?? 0
}

function higherOrderMean(condition: string): number {
  return metricMean('higher_order_ratio', condition)
}

function segmentStyle(metricKey: string, condition: string) {
  return { width: `${Math.max(0, metricMean(metricKey, condition) * 100)}%` }
}

function highOrderStyle(condition: string) {
  return { width: `${Math.max(1, higherOrderMean(condition) * 100)}%` }
}
</script>

<template>
  <el-card class="analysis-card composition-card" shadow="never">
    <template #header>
      <div class="card-title">
        <div class="card-heading">
          <strong>{{ activeLabels.cardTitle }}</strong>
          <span>{{ activeLabels.cardDesc }}</span>
        </div>
        <el-segmented
          v-if="charts?.['composition_en']"
          v-model="chartLanguage"
          size="small"
          :options="[
            { label: '中文', value: 'zh' },
            { label: 'English', value: 'en' },
          ]"
        />
      </div>
    </template>

    <!-- matplotlib 图（优先） -->
    <div v-if="activeChartSrc" class="chart-image-shell">
      <div class="chart-image-actions">
        <el-tooltip content="放大预览" placement="top">
          <el-button :icon="ZoomIn" class="chart-tool-button" circle @click="previewVisible = true" />
        </el-tooltip>
        <el-tooltip content="下载 PNG" placement="top">
          <el-button :icon="Download" class="chart-tool-button" circle @click="downloadActiveChart" />
        </el-tooltip>
      </div>
      <img
        :src="activeChartSrc"
        :alt="activeLabels.alt"
        class="chart-image"
        @click="previewVisible = true"
      />
      <el-image-viewer
        v-if="previewVisible"
        :url-list="[activeChartSrc]"
        :initial-index="0"
        :hide-on-click-modal="true"
        @close="previewVisible = false"
      />
    </div>

    <!-- 旧 CSS 兜底 -->
    <div v-else class="composition-grid">
      <section class="chart-panel">
        <div class="chart-title">{{ activeLabels.leftTitle }}</div>
        <div class="stacked-chart">
          <div v-for="condition in conditionColumns" :key="condition" class="stacked-row">
            <div class="chart-label">{{ conditionLabelFor(condition) }}</div>
            <div class="stacked-track">
              <div
                v-for="category in CATEGORY_METRICS"
                :key="category.key"
                class="stacked-segment"
                :style="{ ...segmentStyle(category.key, condition), background: category.color }"
                :title="`${category.label}: ${formatNumber(metricMean(category.key, condition))}`"
              />
            </div>
          </div>
        </div>
        <div class="legend">
          <span v-for="category in CATEGORY_METRICS" :key="category.key" class="legend-item">
            <i :style="{ background: category.color }"></i>{{ category.label }}
          </span>
        </div>
      </section>

      <section class="chart-panel">
        <div class="chart-title">{{ activeLabels.rightTitle }}</div>
        <div class="bar-chart">
          <div v-for="condition in conditionColumns" :key="condition" class="bar-row">
            <div class="chart-label">{{ conditionLabelFor(condition) }}</div>
            <div class="bar-track">
              <div class="bar-fill" :style="highOrderStyle(condition)"></div>
            </div>
            <div class="bar-value">{{ formatNumber(higherOrderMean(condition)) }}</div>
          </div>
        </div>
      </section>
    </div>
  </el-card>
</template>

<style scoped>
.analysis-card {
  border: 1px solid #e3e9f2;
  border-radius: 8px;
}

.composition-card :deep(.el-card__body) {
  padding: 14px;
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-heading {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.card-heading strong {
  color: #1e2d40;
  font-size: 14px;
  font-weight: 600;
}

.card-heading span {
  color: #64748b;
  font-size: 12px;
}

.chart-image-shell {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.chart-image-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 2px 4px 0;
}

.chart-tool-button {
  width: 32px;
  height: 32px;
  border-color: #d6e0ec;
  color: #475569;
  background: #fff;
}

.chart-tool-button:hover,
.chart-tool-button:focus {
  border-color: #9db4d1;
  color: #1d4ed8;
  background: #f8fbff;
}

.chart-image {
  width: 100%;
  display: block;
  cursor: zoom-in;
  border-radius: 4px;
}

.composition-grid {
  display: grid;
  grid-template-columns: minmax(320px, 1.3fr) minmax(280px, 1fr);
  gap: 14px;
}

.chart-panel {
  min-width: 0;
  padding: 12px;
  border: 1px solid #e3e9f2;
  border-radius: 8px;
  background: #f8fafc;
}

.chart-title {
  margin-bottom: 12px;
  color: #172033;
  font-size: 13px;
  font-weight: 700;
}

.stacked-chart,
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.stacked-row,
.bar-row {
  display: grid;
  grid-template-columns: 74px minmax(130px, 1fr) 44px;
  align-items: center;
  gap: 8px;
}

.stacked-row {
  grid-template-columns: 74px minmax(130px, 1fr);
}

.chart-label {
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stacked-track,
.bar-track {
  display: flex;
  height: 18px;
  overflow: hidden;
  border-radius: 999px;
  background: #e8eef7;
}

.stacked-segment {
  min-width: 1px;
}

.bar-fill {
  border-radius: 999px;
  background: #16a34a;
}

.bar-value {
  color: #172033;
  font-size: 12px;
  font-weight: 600;
  text-align: right;
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
  font-size: 11px;
}

.legend-item i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

@media (max-width: 1100px) {
  .composition-grid {
    grid-template-columns: 1fr;
  }
}
</style>
