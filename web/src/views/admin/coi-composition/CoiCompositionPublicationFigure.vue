<script setup lang="ts">
import { computed, ref } from 'vue'
import { Download, ZoomIn } from '@element-plus/icons-vue'
import type { PostHocResult, StatisticalTestResult } from '../../../api/admin/coi-analysis'
import type { CoiCompositionObservation } from '../../../api/admin/coi-composition-analysis'
import { downloadSvgElement, serializeSvgElement } from '../task-score/analysisExport'
import { buildCoiCompositionPublicationSvg } from './publicationFigure'

const props = defineProps<{
  observations: CoiCompositionObservation[]
  conditions: string[]
  tests: StatisticalTestResult[]
  postHocTests: PostHocResult[]
}>()

const figureContainer = ref<HTMLElement | null>(null)
const previewVisible = ref(false)
const previewSrc = ref('')
const figureMarkup = computed(() => buildCoiCompositionPublicationSvg({
  observations: props.observations,
  conditions: props.conditions,
  tests: props.tests,
  postHocTests: props.postHocTests,
}))

function figureSvg(): SVGElement | null {
  return figureContainer.value?.querySelector('svg') ?? null
}

function openPreview() {
  const svg = figureSvg()
  if (!svg) return
  previewSrc.value = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(serializeSvgElement(svg))}`
  previewVisible.value = true
}

function downloadFigure() {
  const svg = figureSvg()
  if (svg) downloadSvgElement(svg, 'coi-phase-proportions-publication.svg')
}
</script>

<template>
  <section class="publication-figure">
    <header>
      <div><strong>Publication Figure</strong><span>Four phases × three experimental conditions; significant results are shown in red.</span></div>
      <div class="chart-actions">
        <el-tooltip content="Enlarge chart"><el-button :icon="ZoomIn" circle size="small" @click="openPreview" /></el-tooltip>
        <el-tooltip content="Download combined SVG"><el-button :icon="Download" circle size="small" @click="downloadFigure" /></el-tooltip>
      </div>
    </header>
    <div ref="figureContainer" class="figure-svg" v-html="figureMarkup" @click="openPreview" />
    <el-dialog v-model="previewVisible" title="CoI Phase Proportions by Experimental Condition" width="96vw" top="2vh" append-to-body>
      <div class="publication-large"><img :src="previewSrc" alt="Enlarged CoI phase proportions" /></div>
      <template #footer><el-button :icon="Download" type="primary" @click="downloadFigure">Save SVG</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.publication-figure { margin-bottom: 18px; padding: 14px 16px 10px; border: 2px solid #cbd5e1; border-radius: 9px; background: #fff; }
.publication-figure header { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
.publication-figure header > div:first-child { display: flex; flex-direction: column; gap: 3px; }
.publication-figure header strong { color: #172033; font-size: 16px; font-weight: 800; }
.publication-figure header span { color: #526071; font-size: 13px; font-weight: 550; }
.chart-actions { display: flex; gap: 7px; flex-shrink: 0; }
.figure-svg { cursor: zoom-in; }
.figure-svg :deep(svg) { display: block; width: 100%; height: auto; }
:global(.publication-large) { overflow: auto; background: #fff; }
:global(.publication-large img) { display: block; width: 2000px; max-width: none; height: auto; }
</style>
