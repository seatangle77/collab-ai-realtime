// Fast, local report checks. No browser, network, database or AI calls.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const chartSource=readFileSync(new URL('../../src/views/admin/task-score/academicChartStyle.ts',import.meta.url),'utf8')
const chartCode=ts.transpileModule(chartSource,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const chartUrl=`data:text/javascript;base64,${Buffer.from(chartCode).toString('base64')}`
const source=readFileSync(new URL('../../src/views/admin/cue-uptake/presentation.ts',import.meta.url),'utf8').replace("'../task-score/academicChartStyle'", JSON.stringify(chartUrl))
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const presentation=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const fixture=JSON.parse(readFileSync(new URL('./fixtures/cue-analysis.json',import.meta.url),'utf8'))

test('Chinese and English reports share data, with translated labels and charts',()=>{
  const zh=presentation.reportHtml(fixture,'zh'),en=presentation.reportHtml(fixture,'en')
  assert.match(zh,/<html lang="zh-CN">/)
  assert.match(en,/<html lang="en">/)
  assert.match(zh,/提示采纳分析/)
  assert.match(en,/Cue Uptake Analysis/)
  for(const text of ['Condition summary','Group summary','Session summary','Cues and evidence','Adoption rate by group','Discussion rate by group','Discussed and adopted']) assert.ok(en.includes(text),text)
  assert.equal((zh.match(/<svg /g)||[]).length,3)
  assert.equal((en.match(/<svg /g)||[]).length,3)
  assert.ok(en.includes('33.3%') && zh.includes('33.3%'))
  assert.ok(!en.includes('小组等权均值'))
})
test('original evidence is escaped and preserved in both languages',()=>{
  for(const lang of ['zh','en']) {
    const html=presentation.reportHtml(fixture,lang)
    assert.ok(html.includes('&lt;script&gt;不执行&lt;/script&gt;'))
    assert.ok(!html.includes('<script>不执行'))
    assert.ok(html.includes('离线证据文本'))
  }
})
test('empty samples render missing values without NaN or Infinity',()=>{
  const r=structuredClone(fixture)
  r.events=[];r.groups=[];r.sessions=[]
  for(const c of r.conditions){c.valid=0;c.adoption_rate=null;c.discussion_rate=null;c.conditional_adoption_rate=null;for(const s of Object.values(c.stats)){s.n=0;s.mean=null;s.sd=null;s.median=null;s.q1=null;s.q3=null}}
  const html=presentation.reportHtml(r,'en')
  assert.ok(html.includes('No valid labels'))
  assert.ok(!/NaN|Infinity/.test(html))
})
test('mean lines cannot block clicking chart points',()=>{
  const svg=presentation.rateSvg(fixture,'adoption_rate')
  assert.ok(svg.includes('data-group="offline-g"'))
  assert.ok(svg.includes('pointer-events="none"'))
})
test('CSV output escapes spreadsheet formulas and preserves numeric values',async()=>{
  let blob
  const originalURL=globalThis.URL,originalDocument=globalThis.document,originalTimer=globalThis.setTimeout
  globalThis.URL={createObjectURL:b=>{blob=b;return 'offline'},revokeObjectURL:()=>{}}
  globalThis.document={createElement:()=>({click(){}})}
  globalThis.setTimeout=()=>0
  try {
    presentation.csv('offline.csv',['文本','数值'],[['=FORMULA',-.25],['a,"b"\nc',.5]])
    const text=await blob.text()
    assert.ok(text.includes('"\'=FORMULA"'))
    assert.ok(text.includes('"-0.25"'))
    assert.ok(text.includes('"a,""b""\nc"'))
  } finally {globalThis.URL=originalURL;globalThis.document=originalDocument;globalThis.setTimeout=originalTimer}
})

test('all figures use English and shared condition colors',()=>{
  for(const lang of ['zh','en']) {
    const html=presentation.reportHtml(fixture,lang)
    const figures=html.match(/<svg[\s\S]*?<\/svg>/g)
    assert.equal(figures.length,3)
    for(const fig of figures) assert.ok(!/[\u4e00-\u9fff]/.test(fig))
    assert.ok(figures[1].includes('#0072B2'))
    assert.ok(figures[1].includes('#D55E00'))
  }
})
test('t and df appear in tables and charts; only p below .05 is red',()=>{
  const r=structuredClone(fixture)
  r.design='independent'
  Object.assign(r.comparisons[0],{design:'independent',status:'ok',t_statistic:2.345,degrees_of_freedom:20.123,p_value:.049})
  Object.assign(r.comparisons[1],{design:'independent',status:'ok',t_statistic:-1.23,degrees_of_freedom:18,p_value:.05})
  for(const lang of ['zh','en']) {
    const html=presentation.reportHtml(r,lang)
    assert.ok(html.includes('2.345 (20.12)'))
    assert.ok(html.includes('Welch t(20.12) = 2.345'))
    assert.ok(html.includes('<td class="significant">0.049</td>'))
    assert.ok(html.includes('<td class="">0.050</td>'))
    assert.ok(html.includes('Welch t(18.00) = -1.230'))
  }
  assert.equal(presentation.isSignificant(null),false)
  assert.equal(presentation.isSignificant(.05),false)
})
