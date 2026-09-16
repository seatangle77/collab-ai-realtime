import { conditions, type Report, type Test } from '../../../api/admin/lexical-diversity'
export type Lang = 'zh' | 'en'
export const names: Record<string, [string, string]> = {
  no_assistance: ['无辅助', 'No Assistance'], glasses: ['智能眼镜', 'Smart Glasses'], app_notification: ['App 通知', 'App Notification'],
  all: ['全部任务', 'All tasks'], lost_at_sea: ['海上求生', 'Lost at Sea'], moon_survival: ['月球求生', 'Moon Survival'], winter_survival: ['冬季求生', 'Winter Survival'],
  mattr_100: ['MATTR-100 · 主指标', 'MATTR-100 · Primary'], mtld: ['MTLD · 稳健性', 'MTLD · Robustness'], token_count: ['总词数', 'Tokens'], type_count: ['不重复词数', 'Types'], ttr: ['普通 TTR（描述）', 'TTR (descriptive)'],
  missing_session: ['没有会话', 'No session'], multiple_sessions: ['同组多场会话，需核验分析单位', 'Multiple sessions per group; verify independent units'],
  missing_text: ['没有人工校正文本', 'No corrected transcript'], ambiguous_task: ['任务缺失或对应不唯一', 'Missing or ambiguous task mapping'], short_text: ['有效词数不足 100', 'Fewer than 100 tokens'],
  insufficient_data: ['每个纳入任务需每条件至少 2 个有效小组，当前不满足', 'Each included task requires at least 2 valid groups per condition'],
  zero_within_variance: ['组内零方差，F 为无穷大；请核验数据', 'Zero within-condition variance; F is infinite; verify data'], ok: ['已计算', 'Calculated'],
}
export const label = (key: string | null, lang: Lang = 'zh') => key == null ? '—' : names[key]?.[lang === 'zh' ? 0 : 1] ?? key
export const fmt = (n: number | null | undefined, digits = 3) => n == null ? '—' : n.toFixed(digits)
export const pval = (n: number | null) => n == null ? '—' : n < .001 ? '< .001' : n.toFixed(4)
export const escape = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!))
export function download(filename: string, content: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], {type:mime})); const a = document.createElement('a'); a.href=url; a.download=filename; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000)
}
export function testSummary(test: Test | undefined, lang: Lang = 'zh'): string {
  if (!test || test.p_value == null) return lang === 'zh' ? '未计算 p 值：' + (test ? label(test.status, lang) : '暂无检验结果') : 'p unavailable: ' + (test ? label(test.status, lang) : 'No test result')
  const p = test.p_value < .001 ? 'p < .001' : `p = ${test.p_value.toFixed(4)}`
  const verdict = lang === 'zh' ? (test.p_value < .05 ? '总体差异显著' : '总体差异未显著') : (test.p_value < .05 ? 'Significant omnibus difference' : 'Omnibus difference not significant')
  return `${p} · ${verdict}`
}
function quantile(v: number[], q: number) { const p=(v.length-1)*q, lo=Math.floor(p), a=v[lo] ?? 0; return a+((v[Math.ceil(p)] ?? a)-a)*(p-lo) }
const colors = ['#74839a','#2a827c','#b2814d']
export function chart(report: Report, metric: 'mattr_100' | 'mtld', lang: Lang = 'en', lengthPlot = false): string {
  const test=report.tests.find(t=>t.metric===metric)
  const pairs=lengthPlot?[]:test?.pairs??[]
  const rows=report.observations.filter(r=>r[metric]!=null), W=940,H=440+pairs.length*24,L=75,R=45,T=95,B=75+pairs.length*24
  const values=rows.map(r=>r[metric] as number)
  const low=values.length?Math.min(...values):0, high=values.length?Math.max(...values):1
  const span=Math.max(high-low,metric==='mattr_100'?.1:1)
  const rawStep=span*1.4/5, magnitude=10**Math.floor(Math.log10(rawStep))
  const step=([1,2,2.5,5,10].find(n=>n*magnitude>=rawStep)??10)*magnitude
  const minimum=Math.max(0,Math.floor((low-span*.2)/step)*step)
  const maximum=metric==='mattr_100'?Math.min(1,Math.ceil((high+span*.2)/step)*step):Math.ceil((high+span*.2)/step)*step
  const axisSpan=Math.max(step,maximum-minimum)
  const y=(v:number)=>H-B-(v-minimum)/axisSpan*(H-T-B), maxTokens=Math.max(1,...rows.map(r=>r.token_count))*1.1
  const x=(n:number)=>L+n/maxTokens*(W-L-R)
  let body=`<rect width="${W}" height="${H}" fill="white"/><text x="${L}" y="24" font-size="15" font-weight="600">${escape(label(metric,lang))}${lengthPlot ? (lang==='zh'?' · 文本长度检查':' · Text length check'):''}</text>`
  body+=`<text x="${W-R}" y="24" text-anchor="end" font-size="11" fill="#748094">${lang==='zh'?'纵轴按数据范围显示':'Y-axis fitted to observed range'}</text>`
  const summary=lengthPlot?(lang==='zh'?'描述性检查；本图未进行相关性显著性检验':'Descriptive check; no correlation significance test'):testSummary(test,lang)
  body+=`<text x="${L}" y="50" font-size="13" font-weight="600" fill="${!lengthPlot&&test?.p_value!=null&&test.p_value<.05?'#ae422e':'#334155'}">${escape(summary)}</text>`
  const method=lengthPlot?'':(lang==='zh'?`任务内置换检验 · ${test?.permutations??4999} 次 · η² = ${fmt(test?.eta_squared)}${metric==='mtld'?' · 稳健性核对（未跨指标校正）':''}`:`Within-task permutation test · ${test?.permutations??4999} permutations · η² = ${fmt(test?.eta_squared)}${metric==='mtld'?' · Robustness (no cross-metric adjustment)':''}`)
  body+=`<text x="${L}" y="72" font-size="11" fill="#748094">${escape(method)}</text>`
  for(let i=0;i<=Math.round(axisSpan/step);i++){const v=minimum+i*step;body+=`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#e7ecf1"/><text x="${L-10}" y="${y(v)+4}" text-anchor="end" font-size="11">${v.toFixed(metric==='mattr_100'?2:Math.max(0,-Math.floor(Math.log10(step))))}</text>`}
  const dot=(cx:number,cy:number,task:string|null,color:string,title:string)=>{
    const shape=task==='moon_survival'?`<path d="M${cx},${cy-5} l5,9 h-10 Z"/>`:task==='winter_survival'?`<rect x="${cx-4}" y="${cy-4}" width="8" height="8"/>`:`<circle cx="${cx}" cy="${cy}" r="4"/>`
    return `<g fill="${color}" fill-opacity=".8" stroke="white" stroke-width=".7"><title>${escape(title)}</title>${shape}</g>`
  }
  conditions.forEach((condition,i)=>{
    const data=rows.filter(r=>r.condition===condition), cx=L+(i+.5)*(W-L-R)/3,color=colors[i]!
    if(!lengthPlot){
      const sorted=data.map(r=>r[metric] as number).sort((a,b)=>a-b)
      if(sorted.length){const q1=quantile(sorted,.25),q3=quantile(sorted,.75),med=quantile(sorted,.5),iqr=q3-q1;const lo=sorted.find(v=>v>=q1-1.5*iqr)!,hi=[...sorted].reverse().find(v=>v<=q3+1.5*iqr)!;
        body+=`<path d="M${cx},${y(lo)} V${y(hi)} M${cx-14},${y(lo)} h28 M${cx-14},${y(hi)} h28" stroke="${color}" fill="none"/><rect x="${cx-36}" y="${y(q3)}" width="72" height="${Math.max(1,y(q1)-y(q3))}" fill="${color}" fill-opacity=".12" stroke="${color}"/><line x1="${cx-36}" x2="${cx+36}" y1="${y(med)}" y2="${y(med)}" stroke="${color}" stroke-width="2"/>`
      }
      body+=`<text x="${cx}" y="${H-B+24}" text-anchor="middle" font-size="12">${escape(label(condition,lang))}</text><text x="${cx}" y="${H-B+41}" text-anchor="middle" font-size="11">n = ${data.length}</text>`
    }
    const placed: {x:number;y:number}[]=[]
    const offsets=[0,...Array.from({length:8},(_,j)=>[(j+1)*11,-(j+1)*11]).flat()]
    // Horizontal offsets separate neighboring points without changing observed values.
    ;[...data].sort((a,b)=>(a[metric] as number)-(b[metric] as number)||a.group_id.localeCompare(b.group_id)).forEach(r=>{
      const cy=y(r[metric] as number)
      const offset=offsets.find(dx=>placed.every(p=>Math.hypot(cx+dx-p.x,cy-p.y)>=11))??offsets[placed.length%offsets.length]!
      const px=lengthPlot?x(r.token_count):cx+offset
      placed.push({x:px,y:cy})
      body+=dot(px,cy,r.task_id,color,`${r.group_name} · ${label(r.task_id,lang)} · ${fmt(r[metric])} · ${r.token_count} tokens`)
    })
  })
  if(lengthPlot){for(let i=0;i<=4;i++){const v=maxTokens*i/4;body+=`<text x="${x(v)}" y="${H-B+20}" text-anchor="middle" font-size="11">${Math.round(v)}</text>`}body+=`<text x="${W/2}" y="${H-27}" text-anchor="middle" font-size="12">${lang==='zh'?'总词数':'Total tokens'}</text>`}
  pairs.forEach((pair,index)=>{
    const description=`${label(pair.condition_a,lang)} vs ${label(pair.condition_b,lang)} · Holm ${pair.p_adjusted<.001?'p < .001':`p = ${pair.p_adjusted.toFixed(4)}`}`
    body+=`<text x="${L}" y="${H-B+66+index*24}" font-size="12" fill="${pair.p_adjusted<.05?'#ae422e':'#64748b'}">${escape(description)}</text>`
  })
  body+=`<text x="${L}" y="${H-8}" font-size="11">${lang==='zh'?'● 海上求生   ▲ 月球求生   ■ 冬季求生；每个点代表一个小组':'● Lost at Sea   ▲ Moon Survival   ■ Winter Survival; each point represents one group'}</text>`
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${escape(label(metric,lang))}" style="font-family:Arial,sans-serif;fill:#334155">${body}</svg>`
}
export function reportHtml(r: Report, lang: Lang): string {
  const en=lang==='en', t=(zh:string,english:string)=>en?english:zh
  const table=(headers:string[], rows:unknown[][])=>`<div class="scroll"><table><thead><tr>${headers.map(h=>`<th>${escape(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${escape(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`
  const title=t('词汇多样性分析报告','Lexical Diversity Analysis Report')
  const summary=table([t('指标','Metric'),t('条件','Condition'),'n','M','SD','Median','Min','Max'],r.summaries.map(s=>[label(s.metric,lang),label(s.condition,lang),s.n,fmt(s.mean),fmt(s.sd),fmt(s.median),fmt(s.min),fmt(s.max)]))
  const tests=r.tests.map(test=>`<h3>${escape(label(test.metric,lang))}</h3>${table(['n','F','p','η²',t('状态','Status')],[[test.n,fmt(test.statistic),pval(test.p_value),fmt(test.eta_squared),label(test.status,lang)]])}${test.pairs.length?table([t('条件 A','Condition A'),t('条件 B','Condition B'),'B − A','95% CI','p','Holm p'],test.pairs.map(p=>[label(p.condition_a,lang),label(p.condition_b,lang),fmt(p.difference),`[${fmt(p.ci_low)}, ${fmt(p.ci_high)}]`,pval(p.p_value),pval(p.p_adjusted)])):`<p>${t('总体未显著或不可计算，未执行两两检验。','Omnibus test not significant or unavailable; no pairwise tests run.')}</p>`}`).join('')
  const notes=t('只读人工校正文本。每场小组讨论为一个观测值；保留正常单字词、功能词和真实重复，移除标点及固定填充词。MATTR 使用 100 词窗口、步长 1；MTLD 为阈值 0.72 的双向均值，仅作为稳健性核对。任务内置换小组条件标签 4,999 次；总体显著后进行三对比较并在各指标内 Holm 校正。两两差异为各任务均值差的等权平均，95% 区间采用任务×条件内小组 Bootstrap（1,999 次），区间未做多重比较校正。η² 为未控制任务的描述性组间效应量。MTLD 未做跨指标校正，不作为第二项确认性发现。分析以同任务内条件标签可交换为前提。文本已人工校正不代表程序验证过完整性。词汇多样性不等于认知深度或协作质量。',
    'Corrected transcripts are read only. Each group discussion is one observation. Single-character words, function words and genuine repetitions are retained; punctuation and a fixed filler list are removed. MATTR uses 100-token windows with stride 1. MTLD is bidirectional with threshold 0.72 and is a robustness check only. Condition labels are permuted within tasks 4,999 times; significant omnibus tests are followed by three pairwise tests with Holm correction within each metric. Pairwise differences equally weight task-specific mean differences. Intervals use group bootstrap within task × condition cells (1,999 draws) and are not multiplicity adjusted. Eta squared is an unadjusted descriptive condition effect size. MTLD has no cross-metric correction and is not a second confirmatory finding. Inference assumes condition labels are exchangeable within tasks. Transcript completeness has not been automatically verified. Lexical diversity does not measure cognitive depth or collaboration quality.')
  return `<!doctype html><html lang="${en?'en':'zh-CN'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>body{font:14px/1.65 Arial,sans-serif;color:#26374b;max-width:1100px;margin:32px auto;padding:0 24px}h1{font-size:26px}h2{margin-top:32px}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border:1px solid #dce3ea;padding:8px;text-align:left}th{background:#f1f5f9}.scroll{overflow:auto}svg{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fa;padding:16px}small{overflow-wrap:anywhere}</style></head><body><h1>${title}</h1><p>${escape(r.generated_at)} · ${escape(label(r.selection.task_id,lang))}</p><small>SHA-256: ${escape(r.source_hash)}</small><h2>${t('方法与解释范围','Method and interpretation')}</h2><p>${notes}</p><h2>${t('描述统计','Descriptive statistics')}</h2>${summary}<h2>${t('分布与文本长度','Distributions and text length')}</h2>${chart(r,'mattr_100',lang)}${chart(r,'mtld',lang)}${chart(r,'mattr_100',lang,true)}<h2>${t('统计比较','Statistical comparisons')}</h2>${tests}<h2>${t('会话明细','Session data')}</h2>${table([t('小组','Group'),t('会话','Session'),t('条件','Condition'),t('任务','Task'),'Tokens','Types','MATTR-100','MTLD','TTR',t('文本指纹','Source hash')],r.observations.map(o=>[o.group_name,o.session_id,label(o.condition,lang),label(o.task_id,lang),o.token_count,o.type_count,fmt(o.mattr_100),fmt(o.mtld),fmt(o.ttr),o.source_hash]))}<h2>${t('未纳入记录','Excluded records')} (${r.excluded.length})</h2>${table([t('小组','Group'),t('会话','Session'),t('原因','Reason'),'Tokens'],r.excluded.map(e=>[e.group_name,e.session_id,label(e.reason,lang),e.token_count]))}<h2>${t('分析参数与样本快照','Parameters and selection snapshot')}</h2><pre>${escape(JSON.stringify({parameters:r.parameters,selection:r.selection},null,2))}</pre></body></html>`
}
export function csv(r: Report): string {
  const headers=['status','group_id','group_name','condition','session_id','task_id','token_count','type_count','window_count','mattr_100','mtld','ttr','source_hash','token_hash','reason','generated_at','analysis_source_hash','parameters']
  const records=[...r.observations.map(o=>({...o,status:'included',reason:''})),...r.excluded.map(e=>({...e,status:'excluded'}))]
  const cell=(v:unknown)=>`"${String(v??'').replace(/^[=+@\-]/,"'$&").replace(/"/g,'""')}"`
  return '\uFEFF'+[headers.map(cell).join(','),...records.map(o=>{const row:Record<string,unknown>={...o,generated_at:r.generated_at,analysis_source_hash:r.source_hash,parameters:JSON.stringify(r.parameters)};return headers.map(h=>cell(row[h])).join(',')})].join('\r\n')
}
