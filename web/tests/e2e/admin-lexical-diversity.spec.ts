import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import type { Report } from '../../src/api/admin/lexical-diversity'
const fixture: Report = JSON.parse(readFileSync(new URL('./fixtures/lexical-diversity.json', import.meta.url), 'utf8'))

const groups=[...fixture.observations,...fixture.excluded].map(o=>({id:o.group_id,name:o.group_name,condition:o.condition}))
test.beforeEach(async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('admin_api_key','fixture-only'))
  await page.route('**/api/admin/groups/**',route=>route.fulfill({json:{items:groups,meta:{total:groups.length,page:1,page_size:200}}}))
})
test('analyzes, renders and exports a reproducible report without mutating data',async({page})=>{
  const writes:string[]=[]
  page.on('request',r=>{if(r.url().includes('/api/')&&r.method()!=='GET')writes.push(r.url())})
  await page.route('**/api/admin/lexical-diversity/',route=>{
    const body=route.request().postDataJSON()
    expect(Object.keys(body.group_ids_by_condition)).toHaveLength(3)
    return route.fulfill({json:{...fixture,selection:body}})
  })
  await page.goto('/admin/lexical-diversity')
  await expect(page.getByRole('heading',{name:'词汇多样性分析',exact:true})).toBeVisible()
  await page.getByRole('button',{name:'生成分析',exact:true}).click()
  await expect(page.getByText('纳入 36 场',{exact:false})).toBeVisible()
  await expect(page.getByRole('heading',{name:'未纳入记录（1）'})).toBeVisible()
  await expect(page.locator('svg[aria-label="MATTR-100 · 主指标"]').first()).toBeVisible()
  const htmlWait=page.waitForEvent('download')
  await page.getByRole('button',{name:'Download English HTML',exact:true}).click()
  const html=await htmlWait; const content=readFileSync((await html.path())!,'utf8')
  expect(content).toContain('Lexical Diversity Analysis Report')
  expect(content).toContain(fixture.source_hash)
  expect(content).toContain('Holm')
  expect(content).toContain('No corrected transcript')
  const csvWait=page.waitForEvent('download');await page.getByRole('button',{name:'下载 CSV',exact:true}).click()
  const exportedCsv=readFileSync((await (await csvWait).path())!,'utf8')
  expect(exportedCsv).toContain('"excluded"');expect(exportedCsv).toContain('token_hash');expect(exportedCsv).toContain('mattr_100')
  expect(writes).toHaveLength(1);expect(writes[0]).toContain('/lexical-diversity/')
  await page.screenshot({path:'/tmp/lexical-diversity-page.png',fullPage:true})
  await page.getByRole('heading',{name:'小组分布',exact:true}).scrollIntoViewIfNeeded()
  await page.screenshot({path:'/tmp/lexical-diversity-chart.png'})
  await page.locator('.controls .el-select').click();await page.getByRole('option',{name:'月球求生',exact:true}).click()
  await expect(page.getByText('筛选已更改，下方为上次结果；重新计算后再导出。')).toBeVisible()
  await expect(page.getByRole('button',{name:'Download English HTML',exact:true})).toBeDisabled()
})
test('failed analysis shows an error and permits retry',async({page})=>{
  await page.route('**/api/admin/lexical-diversity/',route=>route.fulfill({status:503,json:{detail:'分词模型不可用；未修改源数据'}}))
  await page.goto('/admin/lexical-diversity');await page.getByRole('button',{name:'生成分析',exact:true}).click()
  await expect(page.getByRole('alert')).toContainText('分词模型不可用')
  await expect(page.getByRole('button',{name:'生成分析',exact:true})).toBeEnabled()
})
test('empty analysis retains exclusions and offers export',async({page})=>{
  await page.route('**/api/admin/lexical-diversity/',route=>route.fulfill({json:{...fixture,selection:route.request().postDataJSON(),observations:[],summaries:fixture.summaries.map(s=>({...s,n:0,mean:null,sd:null,median:null,min:null,max:null})),tests:fixture.tests.map(t=>({...t,n:0,status:'insufficient_data',p_value:null,statistic:null,eta_squared:null,pairs:[]}))}}))
  await page.goto('/admin/lexical-diversity');await page.getByRole('button',{name:'生成分析',exact:true}).click()
  await expect(page.getByText('纳入 0 场',{exact:false})).toBeVisible()
  await expect(page.getByText('没有人工校正文本',{exact:true})).toBeVisible()
  await expect(page.getByRole('button',{name:'下载 CSV',exact:true})).toBeEnabled()
})

 test('English export safely renders complete charts and source metadata',async({page})=>{
  const copy=structuredClone(fixture)
  copy.observations[0]!.group_name='<script>window.injected=true</script>'
  await page.route('**/api/admin/lexical-diversity/',route=>route.fulfill({json:{...copy,selection:route.request().postDataJSON()}}))
  await page.goto('/admin/lexical-diversity')
  await page.getByRole('button',{name:'生成分析',exact:true}).click()
  const waiting=page.waitForEvent('download')
  await page.getByRole('button',{name:'Download English HTML',exact:true}).click()
  const exported=await waiting
  await page.setContent(readFileSync((await exported.path())!,'utf8'))
  expect(await page.evaluate(()=>('injected' in window))).toBe(false)
  await expect(page.getByRole('heading',{name:'Lexical Diversity Analysis Report'})).toBeVisible()
  await expect(page.locator('svg')).toHaveCount(3)
  await page.getByRole('heading',{name:'Distributions and text length'}).scrollIntoViewIfNeeded()
  await page.screenshot({path:'/tmp/lexical-diversity-export.png'})
})
