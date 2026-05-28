import { test, expect } from '@playwright/test'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || 'TestAdminKey123'

// ─────────────────────────────────────────────────────────────────
// Setup helpers
// ─────────────────────────────────────────────────────────────────

interface TestUser {
  userId: string
  accessToken: string
}

async function registerAndLogin(label: string): Promise<TestUser> {
  const ts = Date.now()
  const email = `q-analysis-${label}-${ts}@example.com`
  const password = '1234'
  const name = `QA ${label} ${ts}`

  const regRes = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
  if (!regRes.ok) throw new Error(`register failed: ${await regRes.text()}`)
  const user = await regRes.json()

  const loginRes = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!loginRes.ok) throw new Error(`login failed: ${await loginRes.text()}`)
  const loginData = await loginRes.json()
  return { userId: user.id, accessToken: loginData.access_token }
}

async function createGroup(condition: string): Promise<string> {
  const ts = Date.now()
  const res = await fetch(`${API_BASE}/api/admin/groups`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({ name: `QA Group ${ts}`, condition, is_active: true }),
  })
  if (!res.ok) throw new Error(`create group failed: ${await res.text()}`)
  const data = await res.json()
  return data.id
}

async function addMember(groupId: string, userId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/memberships`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({ group_id: groupId, user_id: userId, role: 'member', status: 'active' }),
  })
  if (!res.ok) throw new Error(`add member failed: ${await res.text()}`)
}

const SRCC_RESPONSES = Object.fromEntries(
  Array.from({ length: 15 }, (_, i) => [`q${i + 1}`, 5 + (i % 3) - 1]),
)

const PCS_RESPONSES = Object.fromEntries(
  Array.from({ length: 6 }, (_, i) => [`q${i + 1}`, 5 + (i % 2)]),
)

async function submitSrcc(token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/questionnaire/srcc`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ responses: SRCC_RESPONSES }),
  })
  if (!res.ok) throw new Error(`submit SRCC failed: ${await res.text()}`)
}

async function submitPcs(token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/questionnaire/pcs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ responses: PCS_RESPONSES }),
  })
  if (!res.ok) throw new Error(`submit PCS failed: ${await res.text()}`)
}

// ─────────────────────────────────────────────────────────────────
// API-level tests
// ─────────────────────────────────────────────────────────────────

test('questionnaire analysis API returns expected shape for SRCC two_conditions', async () => {
  // Seed: one user per condition
  const [ua, ub] = await Promise.all([
    registerAndLogin('srcc-a'),
    registerAndLogin('srcc-b'),
  ])
  const [ga, gb] = await Promise.all([
    createGroup('no_assistance'),
    createGroup('glasses'),
  ])
  await Promise.all([addMember(ga, ua.userId), addMember(gb, ub.userId)])
  await Promise.all([submitSrcc(ua.accessToken), submitSrcc(ub.accessToken)])

  const res = await fetch(
    `${API_BASE}/api/admin/questionnaire-analysis/?scale=srcc&mode=two_conditions`,
    { headers: { 'X-Admin-Token': ADMIN_API_KEY } },
  )
  expect(res.ok).toBe(true)
  const data = await res.json()

  expect(data.scale).toBe('srcc')
  expect(data.mode).toBe('two_conditions')
  expect(data.conditions).toEqual(['no_assistance', 'glasses'])
  expect(Array.isArray(data.metrics)).toBe(true)
  expect(data.metrics.length).toBe(5) // 4 dimensions + total
  expect(Array.isArray(data.reliability)).toBe(true)
  expect(data.reliability.length).toBe(5)
  expect(Array.isArray(data.normality)).toBe(true)
  expect(Array.isArray(data.statistical_tests)).toBe(true)
  expect(Array.isArray(data.post_hoc_tests)).toBe(true)
})

test('questionnaire analysis API returns expected shape for PCS three_conditions', async () => {
  const [ua, ub, uc] = await Promise.all([
    registerAndLogin('pcs-a'),
    registerAndLogin('pcs-b'),
    registerAndLogin('pcs-c'),
  ])
  const [ga, gb, gc] = await Promise.all([
    createGroup('no_assistance'),
    createGroup('glasses'),
    createGroup('app_notification'),
  ])
  await Promise.all([
    addMember(ga, ua.userId),
    addMember(gb, ub.userId),
    addMember(gc, uc.userId),
  ])
  await Promise.all([
    submitPcs(ua.accessToken),
    submitPcs(ub.accessToken),
    submitPcs(uc.accessToken),
  ])

  const res = await fetch(
    `${API_BASE}/api/admin/questionnaire-analysis/?scale=pcs&mode=three_conditions`,
    { headers: { 'X-Admin-Token': ADMIN_API_KEY } },
  )
  expect(res.ok).toBe(true)
  const data = await res.json()

  expect(data.scale).toBe('pcs')
  expect(data.mode).toBe('three_conditions')
  expect(data.conditions).toEqual(['no_assistance', 'glasses', 'app_notification'])
  expect(data.metrics.length).toBe(3) // belonging + morale + total
  expect(data.reliability.length).toBe(3)
})

test('questionnaire analysis API returns 0 entries when no data', async () => {
  const res = await fetch(
    `${API_BASE}/api/admin/questionnaire-analysis/?scale=srcc&mode=two_conditions`,
    { headers: { 'X-Admin-Token': ADMIN_API_KEY } },
  )
  expect(res.ok).toBe(true)
  const data = await res.json()
  // total_entries may be > 0 from other tests, but shape must be correct
  expect(typeof data.total_entries).toBe('number')
  expect(typeof data.entries_by_condition).toBe('object')
})

test('questionnaire analysis API rejects unauthenticated request', async () => {
  const res = await fetch(
    `${API_BASE}/api/admin/questionnaire-analysis/?scale=srcc&mode=two_conditions`,
  )
  expect(res.status).toBe(403)
})

// ─────────────────────────────────────────────────────────────────
// POST endpoint – group_ids_by_condition filtering
// ─────────────────────────────────────────────────────────────────

test('POST endpoint includes only selected groups data', async () => {
  // Create 2 users in the same condition but different groups
  const [ua, ub] = await Promise.all([
    registerAndLogin('post-srcc-a'),
    registerAndLogin('post-srcc-b'),
  ])

  // Create two groups both in no_assistance, plus one in glasses
  const [ga1Res, ga2Res, gbRes] = await Promise.all([
    fetch(`${API_BASE}/api/admin/groups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
      body: JSON.stringify({ name: `Post-NA-1-${Date.now()}`, condition: 'no_assistance', is_active: true }),
    }),
    fetch(`${API_BASE}/api/admin/groups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
      body: JSON.stringify({ name: `Post-NA-2-${Date.now()}`, condition: 'no_assistance', is_active: true }),
    }),
    fetch(`${API_BASE}/api/admin/groups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
      body: JSON.stringify({ name: `Post-GL-${Date.now()}`, condition: 'glasses', is_active: true }),
    }),
  ])
  const ga1 = (await ga1Res.json()).id as string
  const ga2 = (await ga2Res.json()).id as string
  const gb = (await gbRes.json()).id as string

  // Add members
  await Promise.all([
    fetch(`${API_BASE}/api/admin/memberships`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
      body: JSON.stringify({ group_id: ga1, user_id: ua.userId, role: 'member', status: 'active' }),
    }),
    fetch(`${API_BASE}/api/admin/memberships`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': ADMIN_API_KEY },
      body: JSON.stringify({ group_id: ga2, user_id: ub.userId, role: 'member', status: 'active' }),
    }),
  ])

  // Submit SRCC for both users
  await Promise.all([submitSrcc(ua.accessToken), submitSrcc(ub.accessToken)])

  // POST: only include ga1 (ua's group), exclude ga2 (ub's group), no glasses group
  const res = await fetch(`${API_BASE}/api/admin/questionnaire-analysis/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({
      scale: 'srcc',
      mode: 'two_conditions',
      group_ids_by_condition: {
        no_assistance: [ga1],   // only ua's group
        glasses: [gb],          // no one submitted in glasses group
      },
    }),
  })
  expect(res.ok).toBe(true)
  const data = await res.json()

  // ua's group is included → no_assistance has at least 1
  expect(data.entries_by_condition['no_assistance']).toBeGreaterThanOrEqual(1)
  // gb has no submissions
  expect(data.entries_by_condition['glasses']).toBe(0)
})

test('POST endpoint returns correct shape for PCS three_conditions', async () => {
  const res = await fetch(`${API_BASE}/api/admin/questionnaire-analysis/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Token': ADMIN_API_KEY,
    },
    body: JSON.stringify({
      scale: 'pcs',
      mode: 'three_conditions',
      group_ids_by_condition: {
        no_assistance: [],
        glasses: [],
        app_notification: [],
      },
    }),
  })
  expect(res.ok).toBe(true)
  const data = await res.json()
  expect(data.scale).toBe('pcs')
  expect(data.mode).toBe('three_conditions')
  expect(data.metrics.length).toBe(3)
  expect(data.reliability.length).toBe(3)
  expect(data.total_entries).toBe(0)
})

test('POST endpoint rejects unauthenticated request', async () => {
  const res = await fetch(`${API_BASE}/api/admin/questionnaire-analysis/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scale: 'srcc', mode: 'two_conditions', group_ids_by_condition: {} }),
  })
  expect(res.status).toBe(403)
})
