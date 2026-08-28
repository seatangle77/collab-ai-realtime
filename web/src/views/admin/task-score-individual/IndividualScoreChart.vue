<script setup lang="ts">
import { computed, ref } from 'vue'
import { Download, ZoomIn } from '@element-plus/icons-vue'
import type { IndividualScoreObservation } from '../../../api/admin/task-score-individual-analysis'
import { conditionLabelEn } from '../task-score/reportHelpers'
import { downloadSvgElement } from '../task-score/analysisExport'

const props = defineProps<{
  observations: IndividualScoreObservation[]
  conditions: string[]
}>()
const svgRef = ref<SVGElement | null>(null)
const previewVisible = ref(false)
const previewMarkup = ref('')

const width = 960
const height = 430
const margin = { top: 48, right: 28, bottom: 62, left: 64 }
const plotHeight = height - margin.top - margin.bottom
const panelWidth = computed(() => (width - margin.left - margin.right) / Math.max(1, props.conditions.length))
const maxScore = computed(() => {
  const values = props.observations.flatMap((item) => [item.individual_score, item.group_score])
  return Math.max(10, Math.ceil((Math.max(...values, 0) + 5) / 10) * 10)
})
const yFor = (score: number) => margin.top + (score / maxScore.value) * plotHeight
const ticks = computed(() => Array.from({ length: 6 }, (_, index) => Math.round((maxScore.value * index) / 5)))
const pairedLines = computed(() => props.conditions.flatMap((condition, conditionIndex) => {
  const rows = props.observations.filter((item) => item.condition === condition)
  const panelLeft = margin.left + panelWidth.value * conditionIndex
  return rows.map((item, index) => {
    const jitter = ((index * 13) % 25) - 12
    return {
      ...item,
      x1: panelLeft + panelWidth.value * 0.28 + jitter,
      x2: panelLeft + panelWidth.value * 0.72 + jitter,
      y1: yFor(item.individual_score),
      y2: yFor(item.group_score),
      color: item.improvement > 0 ? '#16a34a' : item.improvement < 0 ? '#dc2626' : '#64748b',
    }
  })
}))

function openPreview() {
  if (!svgRef.value) return
  previewMarkup.value = new XMLSerializer().serializeToString(svgRef.value)
  previewVisible.value = true
}

function downloadChart() {
  if (!svgRef.value) return
  downloadSvgElement(svgRef.value, `individual-to-group-paired-scores-${new Date().toISOString().slice(0, 10)}.svg`)
}
</script>

<template>
  <el-card class="analysis-card" shadow="never">
    <template #header>
      <div class="card-title">
        <div class="card-heading">
          <strong>Individual Score → Group Final Score</strong>
          <span>Green indicates improvement; red indicates a worse group result.</span>
        </div>
        <div class="chart-actions">
          <el-tooltip content="Enlarge chart" placement="top"><el-button :icon="ZoomIn" circle @click="openPreview" /></el-tooltip>
          <el-tooltip content="Download SVG" placement="top"><el-button :icon="Download" circle @click="downloadChart" /></el-tooltip>
        </div>
      </div>
    </template>
    <div v-if="observations.length" class="chart-shell">
      <svg ref="svgRef" :viewBox="`0 0 ${width} ${height}`" role="img" aria-label="Paired individual and group final scores">
        <g v-for="tick in ticks" :key="tick">
          <line :x1="margin.left" :x2="width - margin.right" :y1="yFor(tick)" :y2="yFor(tick)" stroke="#e2e8f0" />
          <text :x="margin.left - 10" :y="yFor(tick) + 4" text-anchor="end" class="tick-label">{{ tick }}</text>
        </g>
        <line :x1="margin.left" :x2="margin.left" :y1="margin.top" :y2="height - margin.bottom" stroke="#94a3b8" />
        <g v-for="(condition, index) in conditions" :key="condition">
          <line
            v-if="index > 0"
            :x1="margin.left + panelWidth * index"
            :x2="margin.left + panelWidth * index"
            :y1="margin.top - 18"
            :y2="height - margin.bottom + 12"
            stroke="#cbd5e1"
            stroke-dasharray="4 5"
          />
          <text :x="margin.left + panelWidth * (index + .5)" y="24" text-anchor="middle" class="condition-label">
            {{ conditionLabelEn(condition) }}
          </text>
          <text :x="margin.left + panelWidth * (index + .28)" :y="height - 28" text-anchor="middle" class="phase-label">Individual IS</text>
          <text :x="margin.left + panelWidth * (index + .72)" :y="height - 28" text-anchor="middle" class="phase-label">Group GS</text>
        </g>
        <g v-for="line in pairedLines" :key="`${line.group_id}-${line.participant_id}`">
          <line :x1="line.x1" :y1="line.y1" :x2="line.x2" :y2="line.y2" :stroke="line.color" stroke-width="1.7" stroke-opacity=".48" />
          <circle :cx="line.x1" :cy="line.y1" r="3.6" :fill="line.color"><title>{{ `${line.participant_id}: IS ${line.individual_score}` }}</title></circle>
          <circle :cx="line.x2" :cy="line.y2" r="3.6" :fill="line.color"><title>{{ `${line.group_id}: GS ${line.group_score}; improvement ${line.improvement}` }}</title></circle>
        </g>
        <text x="18" :y="height / 2" transform="rotate(-90 18 215)" text-anchor="middle" class="axis-label">Task Score (lower = better)</text>
      </svg>
      <div class="legend"><span><i class="green" />Group better (IS−GS&gt;0)</span><span><i class="red" />Group worse (IS−GS&lt;0)</span><span><i class="gray" />Unchanged</span></div>
    </div>
    <el-empty v-else description="生成分析后显示个人到小组的成绩变化" />
    <el-dialog v-model="previewVisible" title="Individual Score → Group Final Score" width="96vw" top="2vh" append-to-body>
      <div class="large-chart-preview" v-html="previewMarkup" />
    </el-dialog>
  </el-card>
</template>

<style scoped>
.analysis-card { border: 1px solid #e3e9f2; border-radius: 8px; }
.card-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.card-heading { display:flex; flex-direction:column; gap:3px; }
.card-title strong { color: #1e2d40; font-size: 14px; }
.card-title span { color: #64748b; font-size: 12px; }
.chart-actions { display:flex; gap:8px; }
.chart-shell { overflow-x: auto; }
svg { display: block; min-width: 820px; width: 100%; }
.tick-label, .axis-label, .phase-label { fill: #64748b; font-size: 12px; }
.condition-label { fill: #1e293b; font-size: 15px; font-weight: 700; }
.legend { display: flex; justify-content: center; gap: 22px; color: #526071; font-size: 12px; padding-bottom: 8px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 18px; height: 3px; border-radius: 2px; display: inline-block; }
.green { background: #16a34a; }.red { background: #dc2626; }.gray { background: #64748b; }
:global(.large-chart-preview) { overflow:auto; background:#fff; }
:global(.large-chart-preview svg) { display:block; width:1800px; max-width:none; height:auto; }
</style>
