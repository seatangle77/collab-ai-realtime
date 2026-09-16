<script setup lang="ts">
import { ref } from 'vue'
import { Download, ZoomIn } from '@element-plus/icons-vue'
import { download } from './presentation'
const props=defineProps<{title:string;subtitle:string;svg:string;exportSvg:string;filename:string;disabled?:boolean}>()
const preview=ref(false)
function save(){if(!props.disabled)download(props.filename,props.exportSvg,'image/svg+xml')}
</script>
<template>
  <el-card class="lexical-chart-card" shadow="never">
    <template #header>
      <div class="chart-heading">
        <div><h2>{{ title }}</h2><p>{{ subtitle }}</p></div>
        <div class="chart-actions">
          <el-tooltip content="放大图表"><el-button :icon="ZoomIn" circle aria-label="放大图表" @click="preview=true" /></el-tooltip>
          <el-tooltip content="下载英文 SVG"><el-button :icon="Download" circle aria-label="下载英文 SVG" :disabled="disabled" @click="save" /></el-tooltip>
        </div>
      </div>
    </template>
    <div class="chart-markup" @click="preview=true" v-html="svg" />
    <el-dialog v-model="preview" :title="title" width="92%" append-to-body>
      <div class="chart-preview" v-html="svg" />
      <template #footer><el-button :icon="Download" :disabled="disabled" @click="save">下载英文 SVG</el-button></template>
    </el-dialog>
  </el-card>
</template>
<style scoped>
.lexical-chart-card{border:1px solid #e2e8ef;border-radius:10px}.chart-heading{display:flex;align-items:center;justify-content:space-between;gap:20px}.chart-heading h2{margin:0;font-size:17px;color:#25364a}.chart-heading p{margin:6px 0 0;color:#748094;font-size:12px;line-height:1.6}.chart-actions{display:flex;align-items:center;gap:8px;flex-shrink:0}.chart-actions .el-button{margin:0}.chart-markup{cursor:zoom-in;overflow:auto}.chart-markup :deep(svg){width:100%;min-width:560px;display:block}.chart-preview{overflow:auto}.chart-preview :deep(svg){width:100%;min-width:720px;display:block}
</style>
