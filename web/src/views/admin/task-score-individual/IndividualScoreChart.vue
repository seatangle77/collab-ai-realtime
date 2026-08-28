<script setup lang="ts">
import { computed } from 'vue'
import type { IndividualScoreObservation } from '../../../api/admin/task-score-individual-analysis'
import { conditionLabel } from '../task-score/reportHelpers'

const props = defineProps<{
  observations: IndividualScoreObservation[]
  conditions: string[]
}>()

const width = 900
const height = 390
const margin = { top: 34, right: 34, bottom: 70, left: 68 }
const plotHeight = height - margin.top - margin.bottom
const colors: Record<string, string> = {
  no_assistance: '#475569',
  glasses: '#2563eb',
  app_notification: '#ea580c',
}

const maxScore = computed(() => {
  const values = props.observations.map((item) => item.score)
  return Math.max(10, Math.ceil((Math.max(...values, 0) + 5) / 10) * 10)
})
const xFor = (index: number) => margin.left + ((width - margin.left - margin.right) * (index + 0.5)) / props.conditions.length
const yFor = (score: number) => margin.top + (score / maxScore.value) * plotHeight
const ticks = computed(() => Array.from({ length: 6 }, (_, index) => Math.round((maxScore.value * index) / 5)))
const points = computed(() => props.conditions.flatMap((condition, conditionIndex) => {
  const rows = props.observations.filter((item) => item.condition === condition)
  return rows.map((item, index) => ({
    ...item,
    x: xFor(conditionIndex) + ((index * 17) % 41) - 20,
    y: yFor(item.score),
    color: colors[condition] ?? '#64748b',
  }))
}))
</script>

<template>
  <el-card class="analysis-card" shadow="never">
    <template #header>
      <div class="card-title">
        <strong>个人分数分布</strong>
        <span>每个点代表一名参与者；纵轴越低表示表现越好</span>
      </div>
    </template>
    <div v-if="observations.length" class="chart-shell">
      <svg :viewBox="`0 0 ${width} ${height}`" role="img" aria-label="各实验条件个人任务分数分布">
        <g v-for="tick in ticks" :key="tick">
          <line
            :x1="margin.left"
            :x2="width - margin.right"
            :y1="yFor(tick)"
            :y2="yFor(tick)"
            stroke="#e2e8f0"
          />
          <text :x="margin.left - 12" :y="yFor(tick) + 4" text-anchor="end" class="tick-label">{{ tick }}</text>
        </g>
        <line :x1="margin.left" :x2="margin.left" :y1="margin.top" :y2="height - margin.bottom" stroke="#94a3b8" />
        <g v-for="(condition, index) in conditions" :key="condition">
          <line
            :x1="xFor(index) - 75"
            :x2="xFor(index) + 75"
            :y1="yFor(observations.filter(item => item.condition === condition).reduce((sum, item) => sum + item.score, 0) / Math.max(1, observations.filter(item => item.condition === condition).length))"
            :y2="yFor(observations.filter(item => item.condition === condition).reduce((sum, item) => sum + item.score, 0) / Math.max(1, observations.filter(item => item.condition === condition).length))"
            :stroke="colors[condition] ?? '#64748b'"
            stroke-width="4"
            stroke-linecap="round"
          />
          <text :x="xFor(index)" :y="height - 32" text-anchor="middle" class="condition-label">
            {{ conditionLabel(condition) }}
          </text>
        </g>
        <circle
          v-for="point in points"
          :key="`${point.group_id}-${point.participant_id}`"
          :cx="point.x"
          :cy="point.y"
          r="4.5"
          :fill="point.color"
          fill-opacity="0.72"
          stroke="white"
          stroke-width="1"
        >
          <title>{{ `${point.group_id} · ${point.participant_id} · ${point.score}` }}</title>
        </circle>
        <text x="18" :y="height / 2" transform="rotate(-90 18 195)" text-anchor="middle" class="axis-label">
          个人任务分数（越低越好）
        </text>
      </svg>
    </div>
    <el-empty v-else description="生成分析后显示个人分数分布" />
  </el-card>
</template>

<style scoped>
.analysis-card { border: 1px solid #e3e9f2; border-radius: 8px; }
.card-title { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.card-title strong { color: #1e2d40; font-size: 14px; }
.card-title span { color: #64748b; font-size: 12px; }
.chart-shell { overflow-x: auto; }
svg { display: block; min-width: 760px; width: 100%; }
.tick-label, .axis-label { fill: #64748b; font-size: 12px; }
.condition-label { fill: #1e293b; font-size: 14px; font-weight: 700; }
</style>
