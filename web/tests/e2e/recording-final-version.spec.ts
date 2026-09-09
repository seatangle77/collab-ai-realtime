import {test, expect} from '@playwright/test'

test('all recording paragraphs save and reopen even without AI correspondence',async({page})=>{
  await page.addInitScript(()=>{
    localStorage.setItem('admin_api_key','mock')
    localStorage.setItem('assisted-transcript-alignment:s',JSON.stringify({sessionId:'s',transcriptId:'t1',transcriptRelativeSeconds:10,referenceOrder:1,referenceStartTime:10}))
    localStorage.setItem('assisted-transcript-ai-run:v2:s','run1')
  })
  const input={recording:[{order_index:1,content:'录音第一段完整正文。',start_time:10},{order_index:2,content:'录音第二段完整正文。',start_time:20}],transcripts:['范围前原文','替换开始','中间胡乱转写','替换结束','范围后原文'].map((text,i)=>({transcript_id:`t${i}`,text,speaker_name:'甲',relative_seconds:i*10})),source_hash:'source'}
  const segments=[{id:'t0',kind:'before',text:'范围前原文',time:0,speaker_name:'甲',correspondence_status:'original'},...input.recording.map(r=>({id:`recording-${r.order_index}`,kind:'recording',recording_order:r.order_index,text:r.content,time:r.start_time,speaker_name:null,correspondence_status:'pending'})),{id:'t4',kind:'after',text:'范围后原文',time:40,speaker_name:'甲',correspondence_status:'original'}]
  const document={session_id:'s',start_transcript_id:'t1',end_transcript_id:'t3',segments,recording_count:2,pending_count:2,replaced_count:3,before_count:1,after_count:1,source_hash:'source',preview_hash:'preview'}
  let saved: unknown=null
  let aiCalls=0
  let saveCalls=0
  await page.route('**/api/admin/**',async route=>{
    const path=new URL(route.request().url()).pathname
    if(!path.startsWith('/api/admin/'))return route.continue()
    let json: unknown={}
    if(path.includes('ai-match-runs')){
      if(route.request().method()!=='GET'){aiCalls++;throw new Error('No live AI call expected')}
      return route.fulfill({json:{run_id:'run1',session_id:'s',status:'completed_with_errors',model:'qwen3-max',matches:[],summary:{unmatched_references:2,review_required:0},completed_chunks:1,total_chunks:1,failed_chunks:[],out_of_scope_transcript_ids:[],message:'整理完成'}})
    }
    if(path.endsWith('/final-version/source'))json=input
    else if(path.endsWith('/final-version/preview')){
      expect(route.request().postDataJSON()).toMatchObject({alignment_run_id:'run1',alignment_offset_seconds:0})
      expect(route.request().postDataJSON()).not.toHaveProperty('end_transcript_id')
      json=document
    }else if(path.endsWith('/final-version')){
      if(route.request().method()==='POST'){
        saveCalls++
        expect(route.request().postDataJSON()).toMatchObject({boundary_confirmed:true,preview_hash:'preview',base_version_id:null})
        saved={id:'v1',document,created_at:'2026-09-08T00:00:00Z',created_by:null}
      }
      json=saved
    }else if(path.endsWith('/groups'))json=[{group_id:'g',group_name:'测试组',condition:'glasses',transcript_count:5,corrected_count:0}]
    else if(path.endsWith('/sessions'))json=[{session_id:'s',group_id:'g',group_name:'测试组',condition:'glasses',transcript_count:5,corrected_count:0,created_at:'2026-09-08T00:00:00Z'}]
    else if(path.endsWith('/transcripts'))json={items:input.transcripts.map(t=>({...t,original_text:t.text,effective_text:t.text,is_corrected:false,source_transcript_ids:[t.transcript_id]})),meta:{total:5,page:1,page_size:500}}
    else if(path.endsWith('/utterances'))json={session_id:'s',group_id:'g',utterances:input.recording}
    await route.fulfill({json})
  })
  await page.goto('/admin/assisted-transcript-corrections')
  const panel=page.locator('.recording-final-panel')
  await expect(panel.locator('article')).toHaveCount(0)
  await expect(page.getByText('正文预览',{exact:true})).toHaveCount(0)
  await expect(page.getByRole('button',{name:'生成完整预览'})).toHaveCount(0)
  const controls=page.locator('#recording-save-controls')
  await expect(controls.locator('.el-select')).toHaveCount(0)
  await controls.getByRole('button',{name:'确认并保存整理结果'}).click()

  await expect(panel.getByText('已保存',{exact:true})).toBeVisible()
  await expect(panel.getByText('录音第一段完整正文。',{exact:true})).toBeVisible()
  await page.reload()
  await expect(panel.getByText('已保存',{exact:true})).toBeVisible()
  await expect(panel.locator('article')).toHaveCount(4)
  await expect(panel.getByText('范围前原文',{exact:true}).last()).toBeVisible()
  await expect(panel.getByText('范围后原文',{exact:true}).last()).toBeVisible()
  await expect(panel.getByText('中间胡乱转写',{exact:true})).toHaveCount(0)
  await page.screenshot({path:'/tmp/recording-final-version.png',fullPage:true})
  expect(aiCalls).toBe(0);expect(saveCalls).toBe(1)
})
