<script setup lang="ts">
import { computed } from 'vue'
import type { MetricSummary } from '../../../api/admin/coi-analysis'
import type { CoiCompositionObservation } from '../../../api/admin/coi-composition-analysis'
import CoiSessionBoxplot from '../coi/CoiSessionBoxplot.vue'

const props = defineProps<{
  metrics: MetricSummary[]
  observations: CoiCompositionObservation[]
  conditions: string[]
}>()

const panels = [
  { metric: 'te_ratio', key: 'te_ratio', title: 'TE · Triggering Event', subtitle: '触发事件占四阶段编码的比例' },
  { metric: 'ex_ratio', key: 'ex_ratio', title: 'EX · Exploration', subtitle: '探索占四阶段编码的比例' },
  { metric: 'in_ratio', key: 'in_ratio', title: 'IN · Integration', subtitle: '整合占四阶段编码的比例' },
  { metric: 're_ratio', key: 're_ratio', title: 'RE · Resolution', subtitle: '解决占四阶段编码的比例' },
] as const

function valuesFor(key: keyof CoiCompositionObservation): Record<string, number[]> {
  return Object.fromEntries(props.conditions.map(condition => [
    condition,
    props.observations
      .filter(item => item.condition === condition)
      .map(item => Number(item[key]))
      .filter(Number.isFinite),
  ]))
}

const panelRows = computed(() => panels.map(panel => ({
  ...panel,
  values: valuesFor(panel.key),
})))
const compositionMaximum = computed(() => {
  const maximum = Math.max(...props.observations.flatMap(item => [item.te_ratio, item.ex_ratio, item.in_ratio, item.re_ratio]), 0)
  return Math.min(1, Math.max(0.5, Math.ceil(maximum * 10) / 10))
})
const scaleLabel = computed(() => `四个阶段使用共同的0–${(compositionMaximum.value * 100).toFixed(0)}%纵轴，便于直接比较`)
</script>

<template>
  <el-card class="academic-chart-card" shadow="never">
    <template #header>
      <div class="chart-heading">
        <strong>会话级CoI四阶段构成分布</strong>
        <span>{{ scaleLabel }}</span>
      </div>
    </template>

    <div class="boxplot-layout">
      <CoiSessionBoxplot
        v-for="panel in panelRows"
        :key="panel.metric"
        :title="panel.title"
        :subtitle="panel.subtitle"
        :conditions="conditions"
        :values-by-condition="panel.values"
        :maximum="compositionMaximum"
        percent
        unit-label="阶段占比"
      />
    </div>

    <footer class="figure-caption">
      <strong>图 1　三种实验条件下CoI四阶段编码占比的会话级分布。</strong>
      <span>每场会话先分别计算TE、EX、IN和RE在四阶段编码中的占比。箱体表示中位数和四分位区间，须线延伸至1.5倍四分位距内的最远值，圆点为每场会话；右侧菱形与误差线表示均值及其95%置信区间。各条件的分布大量重叠时，不应仅凭均值高低判断存在稳定差异。</span>
    </footer>
  </el-card>
</template>

<style scoped>
.academic-chart-card { border:1px solid #e3e9f2; border-radius:10px; }
.chart-heading { display:flex; flex-direction:column; gap:4px; }
.chart-heading strong { color:#26364b; }
.chart-heading span { color:#718096; font-size:12px; }
.boxplot-layout { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; }
.figure-caption { display:flex; flex-direction:column; gap:4px; margin:18px 4px 2px; padding-top:12px; border-top:1px solid #eef2f6; color:#66758a; font-size:11px; line-height:1.65; }
.figure-caption strong { color:#3f4f63; font-weight:650; }
@media(max-width:900px){.boxplot-layout{grid-template-columns:1fr}}
</style>
