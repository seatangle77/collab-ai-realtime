<script setup lang="ts">
import { computed, ref } from 'vue'
import { Download, ZoomIn } from '@element-plus/icons-vue'
import type { EnaNetworkCondition } from '../../../api/admin/ena-analysis'
import { conditionLabel } from './reportHelpers'

const props = defineProps<{
  networks: EnaNetworkCondition[]   // one or two condition networks
  diffNetwork: EnaNetworkCondition | null
  charts?: Record<string, string>
}>()

const chartLanguage = ref<'zh' | 'en'>('zh')
const previewVisible = ref(false)
const chartLabels = {
  zh: {
    title: 'ENA 认知过程网络图',
    desc: '线条粗细 = 共现强度；差异图中蓝色表示条件B更强，红色表示条件A更强',
    alt: 'ENA 认知过程网络图',
  },
  en: {
    title: 'ENA Cognitive Process Network',
    desc: 'Line thickness = co-occurrence strength; blue indicates condition B is stronger, red indicates condition A is stronger',
    alt: 'ENA cognitive process network',
  },
}
const hasEnglishChart = computed(() => Boolean(props.charts?.['networks_en']))
const activeLabels = computed(() => chartLabels[chartLanguage.value])
const activeChartKey = computed(() => chartLanguage.value === 'en' && hasEnglishChart.value ? 'networks_en' : 'networks')
const activeChartSrc = computed(() => props.charts?.[activeChartKey.value] ?? '')
const activeChartFileName = computed(() =>
  `ena-network-${chartLanguage.value}-${new Date().toISOString().slice(0, 10)}.png`
)

// Fixed node positions in a diamond layout (cx, cy) within a 300×300 viewport
const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  TE: { x: 150, y: 40  },
  EX: { x: 40,  y: 160 },
  IN: { x: 260, y: 160 },
  RE: { x: 150, y: 280 },
}

const NODE_RADIUS = 28
const MAX_STROKE = 18   // px at weight=1
const MIN_STROKE = 0.5  // minimum visible line

// Blue-to-red scale for diff network
function diffColor(diff: number): string {
  if (diff > 0.01) return '#2563eb'   // blue: B stronger
  if (diff < -0.01) return '#dc2626'  // red: A stronger
  return '#d1d5db'                     // grey: no difference
}

function edgeStroke(weight: number, maxWeight: number): number {
  if (maxWeight === 0) return MIN_STROKE
  return Math.max(MIN_STROKE, (weight / maxWeight) * MAX_STROKE)
}

function networkEdges(net: EnaNetworkCondition, isDiff = false) {
  const weights = net.edges.map((e) => Math.abs(isDiff ? (e.weight_diff ?? 0) : e.weight))
  const maxW = Math.max(...weights, 0.001)
  return net.edges.map((e) => {
    const src = NODE_POSITIONS[e.source]!
    const tgt = NODE_POSITIONS[e.target]!
    const w = isDiff ? Math.abs(e.weight_diff ?? 0) : e.weight
    const stroke = edgeStroke(w, maxW)
    const color = isDiff
      ? diffColor(e.weight_diff ?? 0)
      : w < 0.01 ? '#e5e7eb' : '#6b7280'
    return { ...e, x1: src.x, y1: src.y, x2: tgt.x, y2: tgt.y, stroke, color }
  })
}

function nodePos(node: string): { x: number; y: number } {
  return NODE_POSITIONS[node] ?? { x: 150, y: 150 }
}

const conditionNetworks = computed(() =>
  props.networks.map((net) => ({
    net,
    edges: networkEdges(net),
  })),
)

const diffEdges = computed(() =>
  props.diffNetwork ? networkEdges(props.diffNetwork, true) : [],
)

const COI_NODE_COLORS: Record<string, string> = {
  TE: '#f59e0b',
  EX: '#3b82f6',
  IN: '#8b5cf6',
  RE: '#10b981',
}

const COI_LABELS: Record<string, string> = {
  TE: 'TE\n触发事件',
  EX: 'EX\n探索',
  IN: 'IN\n整合',
  RE: 'RE\n解决',
}

function downloadActiveChart() {
  if (!activeChartSrc.value) return
  const link = document.createElement('a')
  link.href = activeChartSrc.value
  link.download = activeChartFileName.value
  link.click()
}
</script>

<template>
  <el-card class="analysis-card" shadow="never">
    <template #header>
      <div class="card-title">
        <div class="card-heading">
          <strong>{{ activeLabels.title }}</strong>
          <span>{{ activeLabels.desc }}</span>
        </div>
        <div class="card-controls">
          <el-segmented
            v-if="charts?.['networks_en']"
            v-model="chartLanguage"
            size="small"
            :options="[
              { label: '中文', value: 'zh' },
              { label: 'English', value: 'en' },
            ]"
          />
        </div>
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

    <!-- 旧 SVG 兜底 -->
    <div v-else class="networks-row">
      <!-- Per-condition networks -->
      <div
        v-for="{ net, edges } in conditionNetworks"
        :key="net.condition"
        class="network-wrap"
        :data-testid="`network-${net.condition}`"
      >
        <div class="network-title">{{ conditionLabel(net.condition) }}</div>
        <svg viewBox="0 0 300 320" class="network-svg" role="img" :aria-label="`${conditionLabel(net.condition)} 网络图`">
          <!-- Edges -->
          <line
            v-for="(e, i) in edges"
            :key="i"
            :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
            :stroke="e.color"
            :stroke-width="e.stroke"
            stroke-linecap="round"
            opacity="0.85"
          />
          <!-- Edge weight labels for key connections -->
          <text
            v-for="(e, i) in edges.filter(e => e.weight >= 0.05)"
            :key="`lbl-${i}`"
            :x="(e.x1 + e.x2) / 2"
            :y="(e.y1 + e.y2) / 2 - 4"
            text-anchor="middle"
            font-size="9"
            fill="#374151"
            class="edge-label"
          >{{ e.weight.toFixed(2) }}</text>
          <!-- Nodes -->
          <g v-for="node in net.nodes" :key="node">
            <circle
              :cx="nodePos(node).x"
              :cy="nodePos(node).y"
              :r="NODE_RADIUS"
              :fill="COI_NODE_COLORS[node]"
              fill-opacity="0.15"
              :stroke="COI_NODE_COLORS[node]"
              stroke-width="2"
            />
            <text
              :x="nodePos(node).x"
              :y="nodePos(node).y - 5"
              text-anchor="middle"
              font-size="12"
              font-weight="700"
              :fill="COI_NODE_COLORS[node]"
            >{{ node }}</text>
            <text
              :x="nodePos(node).x"
              :y="nodePos(node).y + 10"
              text-anchor="middle"
              font-size="9"
              fill="#6b7280"
            >{{ COI_LABELS[node]?.split('\n')[1] }}</text>
          </g>
        </svg>
        <!-- Legend table below each network -->
        <div class="weight-legend">
          <div v-for="e in edges.filter(e => e.weight > 0)" :key="`${e.source}-${e.target}`" class="legend-row">
            <span class="legend-pair">{{ e.source }}–{{ e.target }}</span>
            <div class="legend-bar-wrap">
              <div class="legend-bar" :style="{ width: `${e.weight * 100}%`, background: e.color }" />
            </div>
            <span class="legend-val">{{ e.weight.toFixed(3) }}</span>
          </div>
        </div>
      </div>

      <!-- Difference network -->
      <div v-if="diffNetwork" class="network-wrap" data-testid="network-diff">
        <div class="network-title">差异图（条件B − 条件A）</div>
        <svg viewBox="0 0 300 320" class="network-svg" role="img" aria-label="差异网络图">
          <line
            v-for="(e, i) in diffEdges"
            :key="i"
            :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
            :stroke="e.color"
            :stroke-width="e.stroke"
            stroke-linecap="round"
            opacity="0.85"
          />
          <text
            v-for="(e, i) in diffEdges.filter(e => Math.abs(e.weight_diff ?? 0) >= 0.05)"
            :key="`dlbl-${i}`"
            :x="(e.x1 + e.x2) / 2"
            :y="(e.y1 + e.y2) / 2 - 4"
            text-anchor="middle"
            font-size="9"
            fill="#374151"
            class="edge-label"
          >{{ (e.weight_diff ?? 0) > 0 ? '+' : '' }}{{ (e.weight_diff ?? 0).toFixed(2) }}</text>
          <g v-for="node in diffNetwork.nodes" :key="node">
            <circle
              :cx="nodePos(node).x"
              :cy="nodePos(node).y"
              :r="NODE_RADIUS"
              :fill="COI_NODE_COLORS[node]"
              fill-opacity="0.15"
              :stroke="COI_NODE_COLORS[node]"
              stroke-width="2"
            />
            <text
              :x="nodePos(node).x"
              :y="nodePos(node).y - 5"
              text-anchor="middle"
              font-size="12"
              font-weight="700"
              :fill="COI_NODE_COLORS[node]"
            >{{ node }}</text>
            <text
              :x="nodePos(node).x"
              :y="nodePos(node).y + 10"
              text-anchor="middle"
              font-size="9"
              fill="#6b7280"
            >{{ COI_LABELS[node]?.split('\n')[1] }}</text>
          </g>
        </svg>
        <!-- Diff legend -->
        <div class="diff-legend">
          <span class="diff-legend-item blue">■ 蓝色：条件B 连接更强</span>
          <span class="diff-legend-item red">■ 红色：条件A 连接更强</span>
          <span class="diff-legend-item grey">■ 灰色：差异 &lt; 0.01</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<style scoped>
.analysis-card { border: 1px solid #e3e9f2; border-radius: 8px; }
.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
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

.card-heading span { color: #748197; font-size: 13px; }

.card-controls {
  display: flex;
  align-items: center;
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

.networks-row {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding: 16px;
}

.network-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  min-width: 220px;
  flex: 1 1 220px;
}

.network-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e2d40;
}

.network-svg {
  width: 100%;
  max-width: 280px;
  height: auto;
}

.edge-label {
  pointer-events: none;
  user-select: none;
  font-family: monospace;
}

/* Weight legend */
.weight-legend {
  width: 100%;
  max-width: 280px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.legend-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.legend-pair {
  width: 36px;
  color: #374151;
  font-weight: 600;
  flex-shrink: 0;
}

.legend-bar-wrap {
  flex: 1;
  height: 6px;
  background: #f3f4f6;
  border-radius: 3px;
  overflow: hidden;
}

.legend-bar {
  height: 100%;
  border-radius: 3px;
  min-width: 2px;
}

.legend-val {
  width: 36px;
  text-align: right;
  color: #6b7280;
  font-family: monospace;
}

/* Diff legend */
.diff-legend {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
}

.diff-legend-item { display: flex; align-items: center; gap: 4px; }
.diff-legend-item.blue { color: #2563eb; }
.diff-legend-item.red  { color: #dc2626; }
.diff-legend-item.grey { color: #9ca3af; }
</style>
