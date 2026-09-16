import { academicConditionColor, academicConditionLabel } from '../task-score/academicChartStyle'
import type { CueAnalysisReport, Metric, GroupSummary } from '../../../api/admin/cue-uptake-analysis'
export type ReportLanguage = 'zh' | 'en'
export const conditionName = (v: string, lang:ReportLanguage='zh') => lang==='en' ? academicConditionLabel(v) : ({ glasses: '智能眼镜', app_notification: 'App' }[v] || v)
export const codeName = (v: string | null, lang:ReportLanguage='zh') => (lang==='en' ? { not_discussed: 'Not discussed', discussed_not_adopted: 'Discussed, not adopted', discussed_adopted: 'Discussed and adopted', uncertain: 'Uncertain', not_included: 'Excluded' } : { not_discussed: '未讨论', discussed_not_adopted: '讨论未采纳', discussed_adopted: '讨论并采纳', uncertain: '无法判断', not_included: '不纳入' })[v || ''] || (lang==='en'?'Uncoded':'未编码')
export const metricName = (v: Metric, lang:ReportLanguage='zh') => (lang==='en' ? { adoption_rate: 'Adoption rate', discussion_rate: 'Discussion rate', conditional_adoption_rate: 'Adoption among discussed cues' } : { adoption_rate: '采纳率', discussion_rate: '讨论率', conditional_adoption_rate: '讨论后采纳率' })[v]
export const percent = (v: number | null | undefined) => v == null ? '—' : `${(100 * v).toFixed(1)}%`
export const points = (v: number | null | undefined) => v == null ? '—' : `${(100 * v).toFixed(1)} 个百分点`
export const isSignificant = (v:number|null|undefined) => v != null && Number.isFinite(v) && v < .05
export const tValue = (t:number|null|undefined, df:number|null|undefined) => t == null || df == null ? '—' : `${t.toFixed(3)} (${df.toFixed(2)})`
export const pValue = (v: number | null) => v == null ? '—' : v < .001 ? '< 0.001' : v.toFixed(3)
export const statusName = (v: string) => ({ descriptive: '选择实验设计后计算区间和检验', ok: '已计算', insufficient_data: '至少需要每条件 2 个有效小组／2 对小组', zero_variance: '组间差异无变异，无法估计检验' }[v] || v)
export const escapeHtml = (v: unknown) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!))
const colors = ['#4B5563', '#E69F00', '#009E73']
const head = (title: string) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 740 350" role="img" aria-label="${escapeHtml(title)}" style="font-family:Arial,'Microsoft YaHei',sans-serif;background:white"><rect width="740" height="350" fill="white"/><text x="28" y="30" font-size="18" font-weight="bold" fill="#203443">${title}</text>`
export function compositionSvg(report: CueAnalysisReport) {
  const lang:ReportLanguage='en'
  const en=true
  let s = head(en?'Cue discussion and adoption':'提示讨论与采纳构成')
  const labels = ['not_discussed','discussed_not_adopted','discussed_adopted'].map(c=>codeName(c,lang))
  labels.forEach((label, i) => { s += `<rect x="${30+i*205}" y="53" width="12" height="12" rx="3" fill="${colors[i]}"/><text x="${49+i*205}" y="64" font-size="13" fill="#475569">${label}</text>` })
  report.conditions.forEach((c, i) => {
    const y = 107 + i * 90
    s += `<text x="28" y="${y+22}" font-size="12" fill="#334155">${conditionName(c.condition,lang)}</text><text x="28" y="${y+43}" font-size="12" fill="#64748b">N = ${c.valid}</text><rect x="135" y="${y}" width="565" height="48" rx="4" fill="#f1f5f9"/>`
    let x = 135
    const counts = [c.not_discussed, c.discussed_not_adopted, c.discussed_adopted]
    if (!c.valid) s += `<text x="320" y="${y+29}" font-size="14" fill="#64748b">${en?'No valid labels':'暂无有效标签'}</text>`
    counts.forEach((count, j) => {
      const w = c.valid ? count / c.valid * 565 : 0
      if (!w) return
      s += `<rect x="${x}" y="${y}" width="${w}" height="48" fill="${colors[j]}"><title>${labels[j]}：${count} (${percent(count/c.valid)})</title></rect>`
      const label = en ? `${count} (${percent(count/c.valid)})` : `${count} 条（${percent(count/c.valid)}）`
      if (w > label.length * 7 + 12) s += `<text x="${x+w/2}" y="${y+28}" text-anchor="middle" fill="white" font-size="12">${label}</text>`
      x += w
    })
  })
  return s + `<text x="28" y="318" font-size="12" fill="#64748b">${en?'Pooled valid cues; hover over segments to view counts.':'按全部有效提示计算比例；悬停色块查看数量。'}</text></svg>`
}
export function rateSvg(report: CueAnalysisReport, metric: Metric) {
  const lang:ReportLanguage='en'
  const en=true
  let s = head(en?`${metricName(metric,lang)} by group`:`每组${metricName(metric)}`)
  const comparison = report.comparisons.find(c=>c.metric===metric)
  const t = comparison?.t_statistic, df = comparison?.degrees_of_freedom
  const testName=report.design==='paired'?'Paired t':'Welch t'
  if (t != null && df != null && comparison?.p_value != null) {
    s += `<text x="90" y="60" font-size="13" fill="#475569">${testName}(${df.toFixed(2)}) = ${t.toFixed(3)}<tspan dx="16" fill="${isSignificant(comparison.p_value)?'#c81e1e':'#475569'}" font-weight="${isSignificant(comparison.p_value)?'700':'400'}">${escapeHtml(`p ${comparison.p_value<.001?'< 0.001':`= ${pValue(comparison.p_value)}`}`)}</tspan>${metric==='discussion_rate'?'<tspan dx="10">(exploratory, unadjusted)</tspan>':''}</text>`
  } else {
    s += '<text x="90" y="60" font-size="12" fill="#64748b">t and p unavailable for this sample</text>'
  }
  const xPos: Record<string, number> = { glasses: 265, app_notification: 530 }
  const y = (v: number) => 278-v*190
  for (let v=0; v<=1.001; v+=.25) s += `<line x1="90" x2="690" y1="${y(v)}" y2="${y(v)}" stroke="#e2e8f0"/><text x="74" y="${y(v)+4}" text-anchor="end" font-size="12" fill="#64748b">${Math.round(v*100)}%</text>`
  const position = new Map<string, {x:number;y:number}>()
  report.conditions.forEach(c => {
    const gs = report.groups.filter(g => g.condition === c.condition && g[metric] != null)
    gs.forEach((g, i) => position.set(`${g.condition}:${g.group_id}`, {x: xPos[g.condition]! + ((i % 7)-3)*12, y:y(g[metric]!)}))
    s += `<text x="${xPos[c.condition]}" y="302" text-anchor="middle" font-size="14" fill="#334155">${conditionName(c.condition,lang)} · ${gs.length} ${en?'groups':'组'}</text>`
  })
  if (report.design === 'paired') for (const pair of report.pairs) {
    const a=position.get(`glasses:${pair.glasses}`), b=position.get(`app_notification:${pair.app_notification}`)
    if(a && b) s += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#b6c8cc" stroke-width="1"/>`
  }
  report.groups.forEach(g => {
    const p=position.get(`${g.condition}:${g.group_id}`)
    if (!p) return
    s += `<circle data-group="${escapeHtml(g.group_id)}" data-condition="${g.condition}" tabindex="0" role="button" aria-label="${en?'View':'查看'} ${escapeHtml(g.group_name)}" cx="${p.x}" cy="${p.y}" r="6" fill="${academicConditionColor(g.condition)}" stroke="white" style="cursor:pointer"><title>${escapeHtml(g.group_name)} · N=${g.valid} · ${en?'Adopted':'采纳'}=${g.discussed_adopted} · ${metricName(metric,lang)}=${percent(g[metric])}</title></circle>`
  })
  report.conditions.forEach(c => {
    const mean=c.stats[metric].mean, x=xPos[c.condition]!
    if(mean!=null) s += `<line x1="${x-50}" x2="${x+50}" y1="${y(mean)}" y2="${y(mean)}" stroke="#192f3c" stroke-width="3" pointer-events="none"><title>${en?'Equal-weight group mean':'小组等权均值'} ${percent(mean)}</title></line>`
  })
  return s + `<text x="28" y="335" font-size="12" fill="#64748b">${en?'Each dot is a group; horizontal marks show equal-weight group means.':'每点一个小组，短横线为小组等权均值；点击数据点查看提示。'}</text></svg>`
}
export function download(name: string, content: BlobPart, type: string) {
  const url=URL.createObjectURL(new Blob([content], {type}))
  const a=document.createElement('a'); a.href=url; a.download=name; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function csv(name: string, headers: string[], rows: unknown[][]) {
  const cell=(v:unknown) => {
    let s=String(v??'')
    if (/^[\s]*[=+@-]/.test(s) && typeof v !== 'number') s="'"+s
    return '"'+s.replace(/"/g,'""')+'"'
  }
  download(name, '\uFEFF'+[headers,...rows].map(row=>row.map(cell).join(',')).join('\r\n'), 'text/csv;charset=utf-8')
}
export const summaryHeaders=['小组ID','小组','条件','会话ID','会话','会话数','提示总数','有效标签数','未讨论','讨论未采纳','讨论并采纳','无法判断','不纳入','未编码','疑似重复数','采纳率_0至1','讨论率_0至1','讨论后采纳率_0至1']
export const summaryRow=(g:GroupSummary) => [g.group_id,g.group_name,conditionName(g.condition),g.session_id,g.session_title,g.session_count,g.total,g.valid,g.not_discussed,g.discussed_not_adopted,g.discussed_adopted,g.uncertain,g.not_included,g.uncoded,g.duplicate_count,g.adoption_rate,g.discussion_rate,g.conditional_adoption_rate]
const table=(headers:string[],rows:unknown[][], cellClass:(row:number,column:number)=>string=()=> '') => `<table><thead><tr>${headers.map(x=>`<th>${escapeHtml(x)}</th>`).join('')}</tr></thead><tbody>${rows.map((row,i)=>`<tr>${row.map((x,j)=>`<td class="${cellClass(i,j)}">${escapeHtml(x)}</td>`).join('')}</tr>`).join('')}</tbody></table>`
export function reportHtml(r:CueAnalysisReport, lang:ReportLanguage='zh') {
  const en=lang==='en'
  const t=(zh:string,english:string)=>en?english:zh
  const cn=(v:string)=>conditionName(v,lang)
  const mn=(v:Metric)=>metricName(v,lang)
  const pp=(v:number|null)=>v==null?'—':`${(v*100).toFixed(1)} ${en?'pp':'个百分点'}`
  const headers=(zh:string[],english:string[])=>en?english:zh
  const method=(design:string)=>design==='paired'?t('小组比例配对 t 检验','Paired t-test on group proportions'):design==='independent'?t('小组比例 Welch t 检验','Welch t-test on group proportions'):t('小组等权均值差','Difference in equal-weight group means')
  const status=(v:string)=>en?({descriptive:'Select a study design for inference',ok:'Calculated',insufficient_data:'At least 2 valid groups per condition / 2 pairs required',zero_variance:'Zero variance; inference unavailable'}[v]||v):statusName(v)
  const section=(title:string,body:string)=>`<h2>${title}</h2><div class="scroll">${body}</div>`
  const summary=table(headers(['条件','组数','会话数','总数','有效数','未讨论','讨论未采纳','讨论并采纳','无法判断','不纳入','未编码','总体采纳率','总体讨论率','讨论后采纳率'],['Condition','Groups','Sessions','Total cues','Valid labels','Not discussed','Discussed, not adopted','Discussed and adopted','Uncertain','Excluded','Uncoded','Pooled adoption rate','Pooled discussion rate','Adoption among discussed cues']),r.conditions.map(c=>[cn(c.condition),c.group_count,c.session_count,c.total,c.valid,c.not_discussed,c.discussed_not_adopted,c.discussed_adopted,c.uncertain,c.not_included,c.uncoded,percent(c.adoption_rate),percent(c.discussion_rate),percent(c.conditional_adoption_rate)]))
  const distribution=table(headers(['条件','指标','有效组数','均值','标准差','中位数','Q1','Q3'],['Condition','Metric','Valid groups','Mean','SD','Median','Q1','Q3']),r.conditions.flatMap(c=>(['adoption_rate','discussion_rate','conditional_adoption_rate'] as Metric[]).map(m=>{const s=c.stats[m];return [cn(c.condition),mn(m),s.n,percent(s.mean),percent(s.sd),percent(s.median),percent(s.q1),percent(s.q3)]})))
  const comparisons=table(headers(['指标','方法','眼镜组数','App组数','差异','95%区间','t (df)','p','状态'],['Metric','Method','Glasses groups','App groups','Difference','95% CI','t (df)','p','Status']),r.comparisons.map(c=>[mn(c.metric),method(c.design),c.n_glasses,c.n_app,pp(c.difference),c.ci_low==null?'—':`${pp(c.ci_low)} ${en?'to':'至'} ${pp(c.ci_high)}`,tValue(c.t_statistic,c.degrees_of_freedom),pValue(c.p_value),status(c.status)]),(i,j)=>j===7 && isSignificant(r.comparisons[i]?.p_value)?'significant':'')
  const groupHeaders=headers(summaryHeaders,['Group ID','Group','Condition','Session ID','Session','Session count','Total cues','Valid labels','Not discussed','Discussed, not adopted','Discussed and adopted','Uncertain','Excluded','Uncoded','Possible duplicates','Adoption rate (0–1)','Discussion rate (0–1)','Adoption among discussed cues (0–1)'])
  const groupTable=table(groupHeaders,r.groups.map(g=>{const row=summaryRow(g);row[2]=cn(g.condition);return row}))
  const sessionTable=table(groupHeaders,r.sessions.map(g=>{const row=summaryRow(g);row[2]=cn(g.condition);return row}))
  const evidence=table(headers(['提示ID','小组','会话','条件','提示','标签','证据','理由'],['Cue ID','Group','Session','Condition','Cue text','Label','Evidence','Reason']),r.events.map(e=>[e.push_log_id,e.group_name,e.session_title||e.session_id,cn(e.condition),e.push_content,codeName(e.code,lang),e.evidence_text,e.coding_reason]))
  const title=t('提示采纳分析','Cue Uptake Analysis')
  const scope=r.groups.map(g=>`${g.group_name} (${cn(g.condition)})`).join(', ') || t('无数据','No data')
  const missing=r.events.reduce((n,e)=>n+e.missing_evidence_count,0)
  const pairs=r.design==='paired'?section(t('小组配对','Group pairs'),table(headers(['眼镜组ID','App组ID'],['Glasses group ID','App group ID']),r.pairs.map(p=>[p.glasses,p.app_notification]))):''
  return `<!doctype html><html lang="${en?'en':'zh-CN'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>body{max-width:1200px;margin:40px auto;padding:0 24px;font:14px/1.7 Arial,sans-serif;color:#243b4a}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{border:1px solid #ddd;padding:8px;text-align:left;min-width:80px}td{white-space:pre-wrap;overflow-wrap:anywhere}th{background:#eff5f4}svg{max-width:760px;width:100%;display:block;margin:20px auto}h2{margin-top:35px}.scroll{overflow:auto}.significant{color:#c81e1e;font-weight:700}@media print{.scroll{overflow:visible}table{font-size:10px}svg{break-inside:avoid}}</style></head><body>
  <h1>${title}</h1><p>${t('计算时间','Generated')}: ${escapeHtml(r.generated_at)} · ${t('版本','Version')}: ${escapeHtml(r.version)} · ${t('编码来源','Label source')}: primary</p>
  <p>${t('分析范围','Scope')}: ${escapeHtml(scope)} · ${r.sessions.length} ${t('场会话','sessions')}</p>
  <p>${t('疑似重复记录（保留，待人工核对）','Possible duplicate records (retained for review)')}: ${r.totals.duplicate_count}; ${t('未找到的证据引用','Unresolved evidence references')}: ${missing}.</p>
  <p>${t('使用当前已保存标签；有效标签为三个正式类别之和。无法判断、不纳入和未编码另列，零分母显示 —。','This snapshot uses saved labels. Valid labels comprise the three substantive categories. Uncertain, excluded and uncoded records are listed separately; a zero denominator is shown as —.')}</p>
  <p>${t('采纳率 = 已采纳 / 有效标签；讨论率 = 两类已讨论 / 有效标签；讨论后采纳率 = 已采纳 / 两类已讨论。','Adoption rate = adopted / valid labels; discussion rate = both discussed categories / valid labels; adoption among discussed cues = adopted / both discussed categories.')}</p>
  <p>${t('组级检验未调整任务或顺序。采纳率为主要指标，讨论率为探索性指标（p 值未校正）。区间基于组级 t 分布估计，小样本及偏态分布需谨慎解释。','Group-level tests are unadjusted for task or order. Adoption is the primary outcome; discussion is exploratory (unadjusted p-values). Intervals use group-level t approximations; small samples and skewed proportions warrant caution.')}</p>
  <p>${t('红色表示 p < 0.05；图中 t 值方向为眼镜减 App。','Red indicates p < 0.05; t statistics use glasses minus App.').replace(/</g,'&lt;')}</p>
  <p>${t('提示正文、证据及研究者填写内容保留原文。','Cue text, evidence and researcher-entered content are preserved in their original language.')}</p>
  ${section(t('条件汇总','Condition summary'),summary)}${section(t('小组比例分布','Distribution of group proportions'),distribution)}${section(t('条件比较：眼镜 − App','Condition comparison: glasses − App'),comparisons)}${pairs}
  ${compositionSvg(r)}${rateSvg(r,'adoption_rate')}${rateSvg(r,'discussion_rate')}
  ${section(t('小组汇总','Group summary'),groupTable)}${section(t('会话汇总','Session summary'),sessionTable)}${section(t('提示与证据','Cues and evidence'),evidence)}
  </body></html>`
}
