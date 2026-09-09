import {test,expect} from '@playwright/test'

test('original switch reloads original search and never shows revised body',async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('admin_api_key','mock'))
  const queries:string[]=[]
  let sourceCalls=0
  const group={group_id:'g',group_name:'测试组',condition:'glasses',transcript_count:1,corrected_count:1}
  await page.route('**/api/admin/**',async route=>{
    const url=new URL(route.request().url()),path=url.pathname
    if(!path.startsWith('/api/admin/'))return route.continue()
    let json:unknown={}
    if(path.endsWith('/final-version/source')){sourceCalls++;throw new Error('Saved result must not reload full alignment source')}
    if(path.endsWith('/groups'))json=[group]
    else if(path.endsWith('/sessions'))json=[{...group,session_id:'s',created_at:'2026-09-08T00:00:00Z'}]
    else if(path.endsWith('/utterances'))json={session_id:'s',group_id:'g',utterances:[]}
    else if(path.endsWith('/final-version'))json=null
    else if(path.endsWith('/transcripts')){
      queries.push(url.search)
      json={items:[{transcript_id:'t',speaker_name:'甲',original_text:'最初识别的原文',effective_text:'修订后的正文',is_corrected:true,correction_id:'c',source_transcript_ids:['t']}],meta:{total:1,page:1,page_size:500}}
    }
    await route.fulfill({json})
  })
  await page.goto('/admin/assisted-transcript-corrections')
  const list=page.locator('.transcript-list')
  await expect(list.getByText('修订后的正文',{exact:true})).toBeVisible()
  await page.getByRole('button',{name:'修订前实时转写',exact:true}).click()
  await expect(list.getByText('最初识别的原文',{exact:true})).toBeVisible()
  await expect(list.getByText('修订后的正文',{exact:true})).toHaveCount(0)
  await expect(list.locator('.inline-ai-match')).toHaveCount(0)
  expect(queries.at(-1)).toContain('content_view=original')
  await page.getByPlaceholder('搜索转写内容').fill('最初')
  await page.getByRole('button',{name:'查询',exact:true}).click()
  await expect.poll(()=>queries.at(-1)).toContain('keyword=')
  expect(queries.at(-1)).toContain('content_view=original')
  expect(sourceCalls).toBe(0)
})
