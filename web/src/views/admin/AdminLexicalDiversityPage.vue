<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download, Refresh } from '@element-plus/icons-vue'
import { listAdminGroups } from '../../api/admin/groups'
import { analyzeLexical, conditions, type Report, type Selection } from '../../api/admin/lexical-diversity'
import type { AdminGroup } from '../../types/admin'
import SampleSelector from './task-score/SampleSelector.vue'
import LexicalChartPanel from './lexical-diversity/LexicalChartPanel.vue'
import { label, fmt, pval, chart, csv, download, reportHtml, testSummary, type Lang } from './lexical-diversity/presentation'
const groups=ref<AdminGroup[]>([]), loadingGroups=ref(false), loading=ref(false), error=ref('')
const selected=ref<Record<string,string[]>>({no_assistance:[],glasses:[],app_notification:[]})
const task=ref('all'), report=ref<Report|null>(null), savedSelection=ref('')
const columns=[...conditions]
const groupOptions=computed(()=>Object.fromEntries(conditions.map(c=>[c,groups.value.filter(g=>g.condition===c)])))
const selection=():Selection=>({group_ids_by_condition:Object.fromEntries(conditions.map(c=>[c,[...(selected.value[c]??[])].sort()])),task_id:task.value})
const stale=computed(()=>report.value && savedSelection.value!==JSON.stringify(selection()))
const canExport=computed(()=>!!report.value&&!stale.value&&!loading.value)
const primary=computed(()=>report.value?.summaries.filter(s=>s.metric==='mattr_100')??[])
const stamp=()=>report.value?.generated_at.replace(/[:.]/g,'-')??''
async function loadGroups(){loadingGroups.value=true;error.value='';try{let page=1;const all:AdminGroup[]=[];for(;;){const data=await listAdminGroups({page,page_size:200});all.push(...data.items);if(all.length>=data.meta.total || !data.items.length)break;page++}groups.value=all;selected.value=Object.fromEntries(conditions.map(c=>[c,all.filter(g=>g.condition===c).map(g=>g.id)]))}catch(e){error.value=e instanceof Error?e.message:'加载小组失败'}finally{loadingGroups.value=false}}
async function calculate(){loading.value=true;error.value='';const payload=selection();try{report.value=await analyzeLexical(payload);savedSelection.value=JSON.stringify(payload)}catch(e){error.value=e instanceof Error?e.message:'计算失败'}finally{loading.value=false}}
function exportReport(lang:Lang){if(canExport.value&&report.value)download(`lexical-diversity-${lang}-${stamp()}.html`,reportHtml(report.value,lang),'text/html;charset=utf-8')}
function exportCsv(){if(canExport.value&&report.value)download(`lexical-diversity-${stamp()}.csv`,csv(report.value),'text/csv;charset=utf-8')}
function exportSnapshot(){if(canExport.value&&report.value)download(`lexical-diversity-${stamp()}.json`,JSON.stringify(report.value,null,2),'application/json')}
onMounted(loadGroups)
</script>
<template>
  <main class="analysis-page lexical-page">
    <div class="page-header">
      <div>
        <div class="title-line"><h1>词汇多样性分析</h1><el-tag type="info" effect="plain">人工校正文本 · 只读分析</el-tag></div>
        <p>比较三种实验条件下小组讨论的词汇多样性，以每场讨论为一个观测值。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!canExport" @click="exportCsv">下载 CSV</el-button>
        <el-button :icon="Download" :disabled="!canExport" @click="exportReport('zh')">下载中文 HTML</el-button>
        <el-button :icon="Download" :disabled="!canExport" @click="exportReport('en')">Download English HTML</el-button>
        <el-button :icon="Refresh" type="primary" :loading="loading" :disabled="loadingGroups||!Object.values(selected).some(a=>a.length)" @click="calculate">生成分析</el-button>
      </div>
    </div>
    <el-card class="control-card controls" shadow="never">
      <el-form label-width="86px" class="control-form">
        <el-form-item label="比较条件"><el-tag size="large">无辅助 / 智能眼镜 / APP 通知</el-tag></el-form-item>
        <el-form-item label="任务"><el-select v-model="task"><el-option v-for="t in ['all','lost_at_sea','moon_survival','winter_survival']" :key="t" :value="t" :label="label(t)" /></el-select></el-form-item>
        <el-form-item label="当前口径"><span class="muted">MATTR：100 词窗口 · MTLD：稳健性核对</span></el-form-item>
      </el-form>
      <p class="muted small">计算不修改 CoI 文本。首次加载分词模型可能较慢；文本更新后需重新生成分析。</p>
    </el-card>
    <SampleSelector v-model="selected" :condition-columns="columns" :group-options-by-condition="groupOptions" :loading-groups="loadingGroups" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="stale" title="筛选已更改，下方为上次结果；重新计算后再导出。" type="warning" :closable="false" show-icon />
    <div v-if="loading" class="panel muted" role="status">正在读取人工校正文本、分词并进行任务分层统计…</div>
    <el-empty v-if="!report&&!loading" description="选择小组后，点击“生成分析”查看结果。" />
    <template v-if="report">
      <section class="result-heading"><div><strong>分析结果</strong><p class="muted small">{{ new Date(report.generated_at).toLocaleString() }} · {{ label(report.selection.task_id) }} · 纳入 {{ report.observations.length }} 场 · 未纳入 {{ report.excluded.length }} 条</p></div></section>
      <section class="panel significance-overview">
        <h2>显著性检验概览</h2>
        <div v-for="test in report.tests" :key="test.metric" class="significance-row">
          <strong>{{ label(test.metric) }}</strong>
          <span :class="{significant:test.p_value!=null&&test.p_value<.05}">{{ testSummary(test) }}</span>
        </div>
        <p class="muted small">以上为三条件总体检验。总体 p &lt; 0.05 时再做两两比较，并报告 Holm 校正后的 p 值；MTLD 仅用于稳健性核对。</p>
      </section>
      <div class="cards"><section v-for="s in primary" :key="s.condition" class="panel metric-card"><p>{{ label(s.condition) }}</p><strong>{{ fmt(s.mean) }}</strong><span>MATTR-100 均值</span><p class="muted small">n = {{ s.n }} · SD {{ fmt(s.sd) }} · 中位数 {{ fmt(s.median) }}</p></section></div>
      <LexicalChartPanel title="小组分布" subtitle="MATTR-100 · 主指标。三条件共用纵轴；按数据范围显示，便于查看小组差异。" :svg="chart(report,'mattr_100','zh')" :export-svg="chart(report,'mattr_100','en')" :filename="`lexical-diversity-mattr_100-${stamp()}.svg`" :disabled="!canExport" />
      <LexicalChartPanel title="MTLD 稳健性分布" subtitle="每个点代表一个小组，点形区分任务；词汇多样性不直接代表认知深度或协作质量。" :svg="chart(report,'mtld','zh')" :export-svg="chart(report,'mtld','en')" :filename="`lexical-diversity-mtld-${stamp()}.svg`" :disabled="!canExport" />
      <LexicalChartPanel title="文本长度检查" subtitle="查看 MATTR-100 与总词数的关系，颜色对应三种实验条件。" :svg="chart(report,'mattr_100','zh',true)" :export-svg="chart(report,'mattr_100','en',true)" :filename="`lexical-diversity-length-${stamp()}.svg`" :disabled="!canExport" />
      <section class="panel"><h2>三条件统计比较</h2><p class="muted">同任务内置换小组条件标签 4,999 次。MATTR-100 为主指标，MTLD 仅为稳健性核对，不作为独立确认性发现。</p><div v-for="test in report.tests" :key="test.metric" class="test-block"><h3>{{ label(test.metric) }}</h3><div class="test-stats"><span>n = {{ test.n }}</span><span>F = {{ fmt(test.statistic) }}</span><span :class="{significant:test.p_value!=null&&test.p_value<.05}">p = {{ pval(test.p_value) }}</span><span>η² = {{ fmt(test.eta_squared) }}</span></div><p class="muted small">{{ label(test.status) }}{{ test.status==='ok'&&test.p_value!=null&&test.p_value>=.05?'；总体差异未达显著，未执行两两检验。':'' }}</p><el-table v-if="test.pairs.length" :data="test.pairs" stripe><el-table-column label="比较（B − A）" min-width="210"><template #default="{row}">{{ label(row.condition_b) }} − {{ label(row.condition_a) }}</template></el-table-column><el-table-column label="均值差"><template #default="{row}">{{ fmt(row.difference) }}</template></el-table-column><el-table-column label="95% CI" min-width="150"><template #default="{row}">[{{ fmt(row.ci_low) }}, {{ fmt(row.ci_high) }}]</template></el-table-column><el-table-column label="原始 p"><template #default="{row}">{{ pval(row.p_value) }}</template></el-table-column><el-table-column label="Holm p"><template #default="{row}"><span :class="{significant:row.p_adjusted<.05}">{{ pval(row.p_adjusted) }}</span></template></el-table-column></el-table></div><p class="muted small">两两差异对任务等权，p 值在每项指标内进行 Holm 校正；置信区间采用任务与条件内的小组 Bootstrap，未做多重比较校正。η² 为未控制任务的描述性效应量。检验以同任务内条件标签可交换为前提。</p></section>
      <section class="panel"><h2>描述统计</h2><el-table :data="report.summaries" stripe><el-table-column label="指标" min-width="180"><template #default="{row}">{{ label(row.metric) }}</template></el-table-column><el-table-column label="条件" min-width="120"><template #default="{row}">{{ label(row.condition) }}</template></el-table-column><el-table-column prop="n" label="n" width="60"/><el-table-column v-for="k in ['mean','sd','median','min','max']" :key="k" :label="({mean:'均值',sd:'SD',median:'中位数',min:'最小值',max:'最大值'} as Record<string,string>)[k]"><template #default="{row}">{{ fmt(row[k]) }}</template></el-table-column></el-table></section>
      <section class="panel"><h2>会话数据检查</h2><p class="muted small">MTLD 为“—”表示文本未形成可估计的词汇变化因子，不按 0 处理。每个小组须只有一场会话；多场会话将列入待核验。</p><el-table :data="report.observations" stripe><el-table-column prop="group_name" label="小组" width="80"/><el-table-column label="条件" min-width="110"><template #default="{row}">{{ label(row.condition) }}</template></el-table-column><el-table-column label="任务" min-width="110"><template #default="{row}">{{ label(row.task_id) }}</template></el-table-column><el-table-column prop="token_count" label="总词数"/><el-table-column prop="type_count" label="不重复词"/><el-table-column prop="window_count" label="窗口数"/><el-table-column label="MATTR-100"><template #default="{row}">{{ fmt(row.mattr_100) }}</template></el-table-column><el-table-column label="MTLD"><template #default="{row}">{{ fmt(row.mtld) }}</template></el-table-column></el-table><h3>未纳入记录（{{ report.excluded.length }}）</h3><el-table v-if="report.excluded.length" :data="report.excluded"><el-table-column prop="group_name" label="小组"/><el-table-column prop="session_id" label="会话"/><el-table-column label="原因" min-width="260"><template #default="{row}">{{ label(row.reason) }}</template></el-table-column><el-table-column prop="token_count" label="有效词数"/></el-table><p v-else class="muted">没有被排除的记录。</p></section>
      <section class="panel"><details><summary>方法、文本指纹与分析参数</summary><el-button class="snapshot-download" :icon="Download" :disabled="!canExport" @click="exportSnapshot">下载 JSON 快照</el-button><p class="muted">保留正常单字词、功能词和真实重复；删除标点、固定非语言标记及填充词。逐条发言分词后按顺序连接。MTLD 为阈值 0.72 的双向均值。程序不根据 CoI 编码筛选，也不写回文本。</p><p class="hash">源文本 SHA-256：{{ report.source_hash }}</p><pre>{{ JSON.stringify(report.parameters,null,2) }}</pre></details></section>
    </template>
  </main>
</template>
<style>
@import './admin-analysis.css';
</style>
<style scoped>
.lexical-page{color:#25364a}.significance-row{display:flex;align-items:baseline;flex-wrap:wrap;gap:12px 28px;padding:10px 0;border-bottom:1px solid #edf0f4;font-size:14px}.significance-row strong{min-width:190px}.title-line{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.control-form{grid-template-columns:repeat(3,minmax(0,1fr))}.snapshot-download{margin-top:16px}@media(max-width:1100px){.control-form{grid-template-columns:1fr}}.heading,.result-heading,.toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}.eyebrow{font-size:12px;letter-spacing:1px;color:#638178;margin:0 0 7px}h2{font-size:18px;margin:0 0 12px}h3{font-size:14px;margin:18px 0 12px}.muted{color:#748094;line-height:1.6;margin:6px 0}.small{font-size:12px}.panel{background:#fff;border:1px solid #e2e8ef;border-radius:10px;padding:22px}.controls .el-checkbox{margin-top:14px;white-space:normal;height:auto}.toolbar label{display:flex;gap:10px;align-items:center;font-size:13px}.exports{display:flex;gap:8px;flex-wrap:wrap}.exports .el-button{margin-left:0}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.metric-card{border-top:3px solid #75879d}.metric-card:nth-child(2){border-top-color:#2a827c}.metric-card:nth-child(3){border-top-color:#b2814d}.metric-card>p:first-child{margin:0 0 14px}.metric-card strong{display:block;font-size:34px;font-variant-numeric:tabular-nums}.metric-card>span{font-size:12px;color:#7b8796}.chart{overflow:auto}.chart :deep(svg){width:100%;min-width:600px;display:block}.test-block{border-bottom:1px solid #edf0f4;padding-bottom:14px}.test-stats{display:flex;flex-wrap:wrap;gap:26px;font-variant-numeric:tabular-nums}.significant{color:#ae422e;font-weight:650}details{margin-top:16px}summary{cursor:pointer;font-size:14px;color:#396c6b}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f9fb;padding:16px;max-height:300px;overflow:auto}.hash{font-size:12px;overflow-wrap:anywhere}@media(max-width:760px){.cards{grid-template-columns:1fr}.panel{padding:16px}}
</style>
