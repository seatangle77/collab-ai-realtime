import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'

test('exports all agreement rows, including hidden matches and unsaved final codes', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('admin_api_key', 'test-key'))
  await page.route('**/api/admin/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.includes('/coi-units/sessions/s1/agreement')) {
      await route.fulfill({ json: [
        {
          unit: { id: 'u1', order_index: 1, content: '一致观点', start_time: 0 },
          coder_a: { coi_categories: ['TE'] }, coder_c: { coi_categories: ['TE'] }, final: null,
        },
        {
          unit: { id: 'u2', order_index: 2, content: '中文,"引号"\n第二行', start_time: 12.5 },
          coder_a: { coi_categories: ['EX', 'IN'] }, coder_c: { coi_categories: ['RE'] }, final: null,
        },
        {
          unit: { id: 'u3', order_index: 3, content: '未完成观点', start_time: null },
          coder_a: null, coder_c: null, final: null,
        },
      ] })
    } else if (path.includes('/chat-sessions')) {
      await route.fulfill({ json: { items: [{ id: 's1', session_title: '讨论会话' }] } })
    } else if (path.includes('/groups')) {
      await route.fulfill({ json: { items: [{ id: 'g1', name: '测试群组' }] } })
    } else {
      await route.fulfill({ json: { items: [], meta: { total: 0 } } })
    }
  })
  await page.goto('/admin/coi-agreement')
  const exportButton = page.getByRole('button', { name: '导出 CSV', exact: true })
  await expect(exportButton).toBeDisabled()
  await page.getByRole('combobox').first().click()
  await page.getByRole('option', { name: '测试群组', exact: true }).click()
  await expect(exportButton).toBeEnabled()
  await expect(page.locator('.agreement-row')).toHaveCount(2)
  const disagreement = page.locator('.agreement-row').filter({ hasText: '第二行' })
  await disagreement.getByRole('button', { name: 'IN 整合', exact: true }).click()
  await disagreement.getByRole('button', { name: 'RE 解决', exact: true }).click()
  const downloadPromise = page.waitForEvent('download')
  await exportButton.click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('CoI最终协商_测试群组_讨论会话_s1.csv')
  const bytes = await readFile((await download.path())!)
  expect([...bytes.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf])
  const csv = bytes.toString('utf8')
  expect(csv).toContain('最终编码（页面当前值）')
  expect(csv).toContain('u1,1,0,一致观点,TE,TE,一致,TE,已定')
  expect(csv).toContain('u2,2,12.5,"中文,""引号""\n第二行",EX;IN,RE,不一致,IN;RE,已定')
  expect(csv).toContain('u3,3,,未完成观点,,,未完成 A/C,,未定')
})
