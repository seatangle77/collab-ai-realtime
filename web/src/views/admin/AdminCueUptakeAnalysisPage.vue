<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { getCueAnalysis, type CueAnalysisReport, type Condition, type Metric, type AnalysisRequest } from '../../api/admin/cue-uptake-analysis'
import { conditionName, codeName, metricName, percent, points, pValue, isSignificant, tValue, statusName, compositionSvg, rateSvg, download, csv, summaryHeaders, summaryRow, reportHtml } from './cue-uptake/presentation'

const report = ref<CueAnalysisReport | null>(null)
const catalog = ref<CueAnalysisReport | null>(null)
const loading = ref(false)
const error = ref('')
const selectedConditions = ref<Condition[]>(['glasses', 'app_notification'])
const selectedGroups = ref<string[]>([])
const selectedSessions = ref<string[]>([])
const savedRequest = ref('')
const drawer = ref(false)
const detailGroup = ref('')
const detailCondition = ref('')
const detailCode = ref('all')
const metrics: Metric[] = ['adoption_rate','discussion_rate','conditional_adoption_rate']
const options = computed(() => catalog.value?.groups.filter(g => selectedConditions.value.includes(g.condition)) ?? [])
const sessionOptions = computed(() => catalog.value?.sessions.filter(g => selectedConditions.value.includes(g.condition) && selectedGroups.value.includes(g.group_id)) ?? [])
function request(): AnalysisRequest {
  return { conditions: [...selectedConditions.value], group_ids: selectedGroups.value.filter(id=>options.value.some(g=>g.group_id===id)), session_ids: [...selectedSessions.value], design: 'independent' }
}
const stale = computed(() => !!report.value && savedRequest.value !== JSON.stringify(request()))
const details = computed(() => (report.value?.events ?? []).filter(e => (!detailGroup.value || e.group_id===detailGroup.value) && (!detailCondition.value || e.condition===detailCondition.value) && (detailCode.value==='all' || (e.code||'uncoded')===detailCode.value)))
const charts = computed(() => report.value ? [
  {id:'composition',title:'三类编码构成',svg:compositionSvg(report.value)},
  {id:'adoption',title:'每组采纳率',svg:rateSvg(report.value,'adoption_rate')},
  {id:'discussion',title:'每组讨论率',svg:rateSvg(report.value,'discussion_rate')},
] : [])
const distributionRows = computed(() => report.value?.conditions.flatMap(c=>metrics.map(m=>({condition:c.condition,metric:m,...c.stats[m]}))) ?? [])
const stamp = computed(() => report.value?.generated_at.replace(/[:.]/g,'-') ?? '')
function resetGroups() { selectedGroups.value=options.value.map(g=>g.group_id); resetSessions() }
function resetSessions() { selectedSessions.value=sessionOptions.value.map(g=>g.session_id!) }
async function initialize() {
  loading.value=true; error.value=''
  try {
    const r=await getCueAnalysis({design:'independent'})
    selectedConditions.value=['glasses','app_notification']; catalog.value=r; resetGroups(); report.value=r; savedRequest.value=JSON.stringify(request())
  } catch(e:any) {error.value=e.message||'加载失败'} finally {loading.value=false}
}
async function calculate() {
  loading.value=true; error.value=''
  const payload=request()
  try { report.value=await getCueAnalysis(payload); savedRequest.value=JSON.stringify(payload) }
  catch(e:any) { error.value=e.message||'分析失败'; ElMessage.error('计算失败，请查看错误信息') }
  finally {loading.value=false}
}
function showDetails(group='', condition='') { detailGroup.value=group;detailCondition.value=condition;detailCode.value='all';drawer.value=true }
function chartClick(e:Event) {
  const target=(e.target as Element).closest('[data-group]')
  if(target) showDetails(target.getAttribute('data-group')||'',target.getAttribute('data-condition')||'')
}
async function exportChart(svg:string, id:string, format:'svg'|'png') {
  if(format==='svg') {download(`${id}-${stamp.value}.svg`,svg,'image/svg+xml');return}
  const url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}))
  try {
    const img=new Image();img.src=url;await img.decode()
    const canvas=document.createElement('canvas');canvas.width=2220;canvas.height=1050
    const ctx=canvas.getContext('2d');if(!ctx)throw Error('画布不可用');ctx.drawImage(img,0,0,2220,1050)
    const blob=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(Error('导出失败')),'image/png'))
    download(`${id}-${stamp.value}.png`,blob,'image/png')
  } catch { ElMessage.error('图片导出失败，请尝试 SVG') } finally {URL.revokeObjectURL(url)}
}
function exportData(kind:string) {
  const r=report.value;if(!r)return
  const file=(name:string)=>`${name}-${stamp.value}.csv`
  if(kind==='html-zh' || kind==='html-en') { const lang=kind==='html-en'?'en':'zh'; download(`cue-uptake-analysis-${lang}-${stamp.value}.html`,reportHtml(r,lang),'text/html;charset=utf-8');return}
  if(kind==='snapshot') {download(`提示采纳分析-${stamp.value}.json`,JSON.stringify(r,null,2),'application/json');return}
  if(kind==='groups'||kind==='sessions') {csv(file(kind==='groups'?'小组汇总':'会话汇总'),summaryHeaders,(kind==='groups'?r.groups:r.sessions).map(summaryRow));return}
  if(kind==='events') {csv(file('提示明细'),['小组ID','小组','会话ID','会话','条件','提示ID','接收成员','提示','触发类型','收到时间','标签','证据ID','证据','缺失证据数','理由','编码者','编码时间','疑似重复'],r.events.map(e=>[e.group_id,e.group_name,e.session_id,e.session_title,conditionName(e.condition),e.push_log_id,e.target_user_name,e.push_content,e.state_type,e.received_at,codeName(e.code),e.evidence_ids.join(';'),e.evidence_text,e.missing_evidence_count,e.coding_reason,e.coded_by,e.coded_at,e.possible_duplicate]));return}
  if(kind==='conditions') {csv(file('条件汇总'),['条件','小组数','会话数','总数','有效数','未讨论','讨论未采纳','讨论并采纳','无法判断','不纳入','未编码','疑似重复','总体采纳率_0至1','总体讨论率_0至1','总体讨论后采纳率_0至1'],r.conditions.map(c=>[conditionName(c.condition),c.group_count,c.session_count,c.total,c.valid,c.not_discussed,c.discussed_not_adopted,c.discussed_adopted,c.uncertain,c.not_included,c.uncoded,c.duplicate_count,c.adoption_rate,c.discussion_rate,c.conditional_adoption_rate]));return}
  if(kind==='distribution') {csv(file('小组比例分布'),['条件','指标','有效组数','均值_0至1','标准差','中位数','Q1','Q3'],distributionRows.value.map(d=>[conditionName(d.condition),metricName(d.metric),d.n,d.mean,d.sd,d.median,d.q1,d.q3]));return}
  csv(file('条件比较'),['指标','方法','设计','眼镜组数','App组数','差异_百分点','95%下限_百分点','95%上限_百分点','t值','自由度','p_未校正','状态'],r.comparisons.map(c=>[metricName(c.metric),c.method,c.design,c.n_glasses,c.n_app,c.difference==null?null:100*c.difference,c.ci_low==null?null:100*c.ci_low,c.ci_high==null?null:100*c.ci_high,c.t_statistic,c.degrees_of_freedom,c.p_value,statusName(c.status)]))
}
onMounted(initialize)
</script>

<template>
  <main class="cue-analysis">
    <header class="page-heading">
      <div><div class="eyebrow">讨论数据 · 已保存标签</div><h1>提示采纳分析</h1><p>查看提示进入讨论和被用于小组判断的情况，比较智能眼镜与 App。</p></div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!report || loading || stale" @click="exportData('groups')">下载 CSV</el-button>
        <el-button :icon="Download" :disabled="!report || loading || stale" @click="exportData('html-zh')">下载中文 HTML</el-button>
        <el-button :icon="Download" :disabled="!report || loading || stale" @click="exportData('html-en')">Download English HTML</el-button>
      </div>
    </header>
    <section class="panel filters">
      <div class="section-heading"><h2>分析范围</h2><el-button text :disabled="loading" @click="initialize">重新加载全部数据</el-button></div>
      <el-checkbox-group v-model="selectedConditions" @change="resetGroups"><el-checkbox value="glasses">智能眼镜</el-checkbox><el-checkbox value="app_notification">App</el-checkbox></el-checkbox-group>
      <div class="filter-grid">
        <label>小组<el-select v-model="selectedGroups" multiple filterable collapse-tags collapse-tags-tooltip placeholder="选择小组" @change="resetSessions"><el-option v-for="g in options" :key="`${g.condition}:${g.group_id}`" :label="`${g.group_name} · ${conditionName(g.condition)}`" :value="g.group_id" /></el-select></label>
        <label>会话<el-select v-model="selectedSessions" multiple filterable collapse-tags collapse-tags-tooltip placeholder="选择会话"><el-option v-for="s in sessionOptions" :key="s.session_id" :label="`${s.group_name} · ${s.session_title || s.session_id}`" :value="s.session_id!" /></el-select></label>
        <el-button type="primary" :loading="loading" @click="calculate">计算分析</el-button>
      </div>
      <p class="muted">眼镜与 App 为不同参与者的小组，按独立小组比较；同组同条件的会话合并计数。</p>
    </section>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="notice"/>
    <el-alert v-if="stale" title="筛选已修改，下方仍是上次结果。点击“计算分析”更新。" type="warning" :closable="false" class="notice"/>
    <div v-if="loading" class="muted loading-note">正在读取标签并计算…</div>
    <template v-if="report">
      <p class="snapshot">计算时间 {{new Date(report.generated_at).toLocaleString('zh-CN')}} · {{report.groups.length}} 个小组条件 · {{report.sessions.length}} 场会话 · {{report.version}}</p>
      <div class="summary-cards">
        <div v-for="card in [{label:'提示总数',value:report.totals.total},{label:'有效标签',value:report.totals.valid},{label:'未编码',value:report.totals.uncoded},{label:'无法判断',value:report.totals.uncertain},{label:'不纳入',value:report.totals.not_included}]" :key="card.label" class="stat-card"><span>{{card.label}}</span><strong>{{card.value}}</strong></div>
      </div>
      <p class="muted">有效标签 = 未讨论 + 讨论未采纳 + 讨论并采纳。各项比例均使用有效标签计算。</p>
      <el-alert v-if="report.totals.uncoded" :title="`当前还有 ${report.totals.uncoded} 条未编码，以下为已完成标签的阶段性结果。`" type="info" :closable="false" class="notice"/>
      <el-alert v-if="report.totals.duplicate_count" :title="`${report.totals.duplicate_count} 条记录被原接口标记为疑似重复，已保留，请在明细中核对。`" type="warning" :closable="false" class="notice"/>
      <el-alert v-if="report.events.some(e=>e.missing_evidence_count)" title="部分已保存证据未找到，明细和导出中已标注。" type="warning" :closable="false" class="notice"/>
      <el-empty v-if="!report.totals.total" description="当前范围内没有符合条件的提示"/>
      <section class="panel">
        <div class="section-heading"><div><h2>条件汇总</h2><p class="muted">全部提示合并计算，小组提示越多，对总体比例的贡献越大。</p></div></div>
        <el-table :data="report.conditions" stripe>
          <el-table-column label="条件" min-width="100"><template #default="{row}">{{conditionName(row.condition)}}</template></el-table-column>
          <el-table-column prop="group_count" label="组数" width="65"/><el-table-column prop="valid" label="有效数" width="80"/>
          <el-table-column prop="not_discussed" label="未讨论"/><el-table-column prop="discussed_not_adopted" label="讨论未采纳"/><el-table-column prop="discussed_adopted" label="讨论并采纳"/>
          <el-table-column v-for="m in metrics" :key="m" :label="metricName(m)" min-width="115"><template #default="{row}">{{percent(row[m])}}</template></el-table-column>
        </el-table>
        <div class="formula">采纳率 = 已采纳 ÷ 有效标签　·　讨论率 = 两类已讨论 ÷ 有效标签　·　讨论后采纳率 = 已采纳 ÷ 两类已讨论</div>
      </section>
      <section class="chart-grid">
        <article v-for="chart in charts" :key="chart.id" class="panel chart-card" :class="{wide:chart.id==='composition'}">
          <div class="chart-actions"><el-button size="small" :disabled="stale || loading" @click="exportChart(chart.svg,chart.id,'svg')">SVG</el-button><el-button size="small" :disabled="stale || loading" @click="exportChart(chart.svg,chart.id,'png')">PNG</el-button></div>
          <div class="chart" v-html="chart.svg" @click="chartClick" @keydown.enter="chartClick" @keydown.space.prevent="chartClick" />
        </article>
      </section>
      <section class="panel"><h2>小组比例分布</h2><p class="muted">每个小组权重相同；分母为零的小组不进入该指标的分布。均值和标准差以百分比显示。</p>
        <el-table :data="distributionRows" stripe><el-table-column label="条件"><template #default="{row}">{{conditionName(row.condition)}}</template></el-table-column><el-table-column label="指标" min-width="130"><template #default="{row}">{{metricName(row.metric)}}</template></el-table-column><el-table-column prop="n" label="有效组数"/>
        <el-table-column v-for="[key,label] in [['mean','均值'],['sd','标准差'],['median','中位数'],['q1','Q1'],['q3','Q3']]" :key="key" :label="label"><template #default="{row}">{{percent(row[key!])}}</template></el-table-column></el-table>
      </section>
      <section class="panel"><h2>条件比较 <span class="muted">眼镜 − App</span></h2>
        <p class="muted">比较小组等权均值。采纳率为主要指标；讨论率为探索性指标，p 值未作多重校正。检验未调整任务或实验顺序。红色表示 p＜0.05；t 值方向为眼镜减 App。</p>
        <el-table :data="report.comparisons" stripe><el-table-column label="指标" width="100"><template #default="{row}">{{metricName(row.metric)}}</template></el-table-column><el-table-column label="差异" width="145"><template #default="{row}">{{points(row.difference)}}</template></el-table-column><el-table-column label="95% 区间" min-width="230"><template #default="{row}">{{row.ci_low==null?'—':`${points(row.ci_low)} 至 ${points(row.ci_high)}`}}</template></el-table-column><el-table-column label="t (df)" width="145"><template #default="{row}">{{tValue(row.t_statistic,row.degrees_of_freedom)}}</template></el-table-column><el-table-column label="p" width="85"><template #default="{row}"><span :class="{significant:isSignificant(row.p_value)}">{{pValue(row.p_value)}}</span></template></el-table-column><el-table-column label="有效组数（眼镜 / App）" min-width="180"><template #default="{row}">{{row.n_glasses}} / {{row.n_app}}</template></el-table-column><el-table-column label="方法 / 状态" min-width="230"><template #default="{row}">{{row.method}}<br/><span class="muted">{{statusName(row.status)}}</span></template></el-table-column></el-table>
      </section>
      <section class="panel"><div class="section-heading"><h2>每组数据</h2><div class="page-actions"><el-button @click="showDetails()">查看全部提示</el-button>      <el-dropdown @command="exportData" :disabled="loading || stale">
        <el-button :disabled="loading || stale">更多数据 ▾</el-button>
        <template #dropdown><el-dropdown-menu>
          <el-dropdown-item command="events">提示明细 CSV</el-dropdown-item>
          <el-dropdown-item command="groups">小组汇总 CSV</el-dropdown-item>
          <el-dropdown-item command="sessions">会话汇总 CSV</el-dropdown-item>
          <el-dropdown-item command="conditions">条件汇总 CSV</el-dropdown-item>
          <el-dropdown-item command="distribution">小组比例分布 CSV</el-dropdown-item>
          <el-dropdown-item command="comparison">条件比较 CSV</el-dropdown-item>
          <el-dropdown-item command="snapshot">完整数据快照 JSON</el-dropdown-item>
        </el-dropdown-menu></template>
      </el-dropdown>
</div></div>
        <el-table :data="report.groups" stripe><el-table-column label="小组" min-width="130"><template #default="{row}"><el-button link type="primary" @click="showDetails(row.group_id,row.condition)">{{row.group_name}}</el-button></template></el-table-column><el-table-column label="条件" width="110"><template #default="{row}">{{conditionName(row.condition)}}</template></el-table-column><el-table-column prop="total" label="总数"/><el-table-column prop="valid" label="有效"/><el-table-column prop="not_discussed" label="未讨论"/><el-table-column prop="discussed_not_adopted" label="讨论未采纳" min-width="110"/><el-table-column prop="discussed_adopted" label="讨论并采纳" min-width="110"/><el-table-column prop="uncertain" label="无法判断" min-width="90"/><el-table-column prop="not_included" label="不纳入"/><el-table-column prop="uncoded" label="未编码"/><el-table-column v-for="m in metrics" :key="m" :label="metricName(m)" min-width="115"><template #default="{row}">{{percent(row[m])}}</template></el-table-column></el-table>
      </section>
    </template>
    <el-drawer v-model="drawer" title="提示与判断证据" size="min(900px, 95vw)">
      <el-select v-model="detailCode" class="detail-filter"><el-option label="全部标签" value="all"/><el-option v-for="code in ['not_discussed','discussed_not_adopted','discussed_adopted','uncertain','not_included','uncoded']" :key="code" :label="codeName(code)" :value="code"/></el-select><p class="muted">{{details.length}} 条提示 · 本次计算快照</p>
      <article v-for="e in details" :key="e.push_log_id" class="evidence-card"><div class="section-heading"><strong>{{e.group_name}} · {{conditionName(e.condition)}}</strong><el-tag>{{codeName(e.code)}}</el-tag></div><p class="muted">{{e.session_title||e.session_id}} · {{e.target_user_name}} · {{new Date(e.received_at).toLocaleString('zh-CN')}}</p><el-tag v-if="e.possible_duplicate" type="warning">疑似重复记录</el-tag><h3>提示</h3><p>{{e.push_content}}</p><h3>所选证据</h3><p class="evidence-text">{{e.evidence_text||'未选择证据'}}</p><h3>判断理由</h3><p>{{e.coding_reason||'未填写'}}</p><small class="muted">{{e.push_log_id}}</small></article>
    </el-drawer>
  </main>
</template>

<style scoped>
.significant{color:#c81e1e;font-weight:700}.cue-analysis{max-width:1440px;margin:0 auto;padding:26px 28px 50px;color:#263b49;background:#f6f8fa;min-height:100vh}.page-heading,.section-heading{display:flex;justify-content:space-between;align-items:center;gap:16px}.page-heading{margin-bottom:24px;flex-wrap:wrap}.page-actions{display:flex;gap:10px;flex-wrap:wrap}.page-actions .el-button+.el-button{margin-left:0}.eyebrow{color:#278269;font-size:12px;letter-spacing:1px;font-weight:600}h1{font-size:28px;margin:8px 0}h2{font-size:18px;margin:0 0 8px}h3{font-size:13px;color:#64748b;margin-bottom:5px}p{line-height:1.7;margin:8px 0}.page-heading p,.muted{font-size:13px;color:#71808d}.panel{background:#fff;border:1px solid #e2e8ee;border-radius:12px;padding:22px;margin-bottom:20px}.filter-grid{display:grid;grid-template-columns:1fr 1fr auto;gap:16px;align-items:end;margin-top:15px}.filter-grid label{display:flex;flex-direction:column;gap:8px;font-size:13px}.filter-grid .el-select{width:100%}.summary-cards{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}.stat-card{padding:18px 20px;background:white;border:1px solid #e2e8ee;border-radius:10px}.stat-card span{font-size:13px;color:#71808d}.stat-card strong{display:block;font-size:29px;margin-top:9px;font-variant-numeric:tabular-nums}.stat-card:nth-child(2){border-top:3px solid #278269}.snapshot{font-size:12px;color:#71808d;margin:18px 0 12px}.notice{margin:12px 0}.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.chart-card{margin:0;min-width:0;padding:12px}.chart-card.wide{grid-column:1/-1}.chart-card.wide .chart{max-width:950px;margin:auto}.chart :deep(svg){width:100%;display:block}.chart-actions{display:flex;justify-content:flex-end;padding:6px 8px}.chart-grid{margin-bottom:20px}.formula{margin-top:14px;padding:12px;background:#f4f8f7;border-radius:6px;font-size:12px;line-height:1.8;color:#48655c}.evidence-card{border:1px solid #e2e8ee;border-radius:10px;padding:18px;margin-bottom:16px}.evidence-card p{white-space:pre-wrap;overflow-wrap:anywhere}.evidence-text{background:#f3f8f5;padding:12px;border-radius:6px}.detail-filter{width:220px}.loading-note{padding:10px 0}@media(max-width:1000px){.filter-grid{grid-template-columns:1fr 1fr}.chart-grid{grid-template-columns:1fr}.summary-cards{grid-template-columns:repeat(3,1fr)}}@media(max-width:650px){.cue-analysis{padding:16px}.page-heading{align-items:flex-start}.filter-grid{grid-template-columns:1fr}.summary-cards{grid-template-columns:1fr 1fr}.panel{padding:16px}}
</style>
