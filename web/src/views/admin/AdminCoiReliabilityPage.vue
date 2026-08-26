<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import { getCoiAgreement, type AgreementUnit, type CoiCategory } from '../../api/admin/coi-units'
import type { AdminChatSession, AdminGroup } from '../../types/admin'
import {
  calculateCoiReliability,
  COI_RELIABILITY_CATEGORIES,
  type CoiReliabilityInput,
  type CoiReliabilityResult,
} from '../../utils/coiReliability'

const ALL_SESSIONS = '__all__'
const CATEGORY_LABELS: Record<CoiCategory, string> = {
  TE: '触发',
  EX: '探索',
  IN: '整合',
  RE: '解决',
  OTHER: '其他',
}

const router = useRouter()
const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const selectedGroupIds = ref<string[]>([])
const selectedSessionId = ref(ALL_SESSIONS)
const loadingGroups = ref(false)
const loadingSessions = ref(false)
const loadingReport = ref(false)
const report = ref<CoiReliabilityResult | null>(null)
const groupReports = ref<Array<{ groupId: string; groupName: string; report: CoiReliabilityResult }>>([])
const generatedAt = ref<string | null>(null)

const selectedGroups = computed(() => groups.value.filter(group => selectedGroupIds.value.includes(group.id)))
const isSingleGroup = computed(() => selectedGroupIds.value.length === 1)
const allGroupsSelected = computed(() => groups.value.length > 0 && selectedGroupIds.value.length === groups.value.length)
const scopeLabel = computed(() => {
  if (selectedGroups.value.length === 0) return '尚未选择范围'
  if (selectedGroups.value.length > 1) return `${selectedGroups.value.length} 个群组 · 全部会话`
  const selectedGroup = selectedGroups.value[0]!
  if (selectedSessionId.value === ALL_SESSIONS) return `${selectedGroup.name} · 全部会话`
  const session = sessions.value.find(item => item.id === selectedSessionId.value)
  return `${selectedGroup.name} · ${session?.session_title ?? '当前会话'}`
})
const groupReportRows = computed(() => {
  const rows = groupReports.value.map(item => ({ ...item, isOverall: false }))
  if (report.value && groupReports.value.length > 1) {
    rows.push({ groupId: '__overall__', groupName: '全部选中群组（汇总）', report: report.value, isOverall: true })
  }
  return rows
})

onMounted(loadGroups)

async function loadGroups() {
  loadingGroups.value = true
  try {
    const response = await listAdminGroups({ page_size: 200 })
    groups.value = response.items
  } catch (error: any) {
    ElMessage.error(error?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
}

function clearResults() {
  report.value = null
  groupReports.value = []
  generatedAt.value = null
}

function selectAllGroups() {
  selectedGroupIds.value = allGroupsSelected.value ? [] : groups.value.map(group => group.id)
  void onGroupChange()
}

async function onGroupChange() {
  sessions.value = []
  selectedSessionId.value = ALL_SESSIONS
  clearResults()
  if (!isSingleGroup.value) return
  loadingSessions.value = true
  try {
    const response = await listAdminChatSessions({ group_id: selectedGroupIds.value[0], page_size: 200 })
    sessions.value = response.items
  } catch (error: any) {
    ElMessage.error(error?.message || '加载会话失败')
  } finally {
    loadingSessions.value = false
  }
}

function onSessionChange() {
  clearResults()
}

function toInputs(rows: AgreementUnit[], group: AdminGroup, sessionTitle: string): CoiReliabilityInput[] {
  return rows.map(row => ({
    groupId: group.id,
    groupName: group.name,
    unitId: row.unit.id,
    sessionId: row.unit.session_id,
    sessionTitle,
    orderIndex: row.unit.order_index,
    content: row.unit.content,
    coderA: [...(row.coder_a?.coi_categories ?? [])],
    coderC: [...(row.coder_c?.coi_categories ?? [])],
  }))
}

async function generateReport() {
  if (selectedGroupIds.value.length === 0) {
    ElMessage.warning('请先选择至少一个群组')
    return
  }

  loadingReport.value = true
  try {
    const resultsByGroup = await Promise.all(selectedGroups.value.map(async (group) => {
      const groupSessions = isSingleGroup.value
        ? sessions.value
        : (await listAdminChatSessions({ group_id: group.id, page_size: 200 })).items
      const scopedSessions = isSingleGroup.value && selectedSessionId.value !== ALL_SESSIONS
        ? groupSessions.filter(session => session.id === selectedSessionId.value)
        : groupSessions
      const inputs = (await Promise.all(scopedSessions.map(async (session) => {
        const rows = await getCoiAgreement(session.id)
        return toInputs(rows, group, session.session_title)
      }))).flat()
      return { groupId: group.id, groupName: group.name, inputs }
    }))
    const allInputs = resultsByGroup.flatMap(item => item.inputs)
    groupReports.value = resultsByGroup.map(item => ({
      groupId: item.groupId,
      groupName: item.groupName,
      report: calculateCoiReliability(item.inputs),
    }))
    report.value = calculateCoiReliability(allInputs)
    generatedAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
    if (allInputs.length === 0) {
      ElMessage.warning('当前范围没有可分析的观点')
      return
    }
    if (report.value.eligibleCount === 0) {
      ElMessage.warning('当前范围没有A和C均完成的单编码观点')
    }
  } catch (error: any) {
    report.value = null
    generatedAt.value = null
    ElMessage.error(error?.message || '生成可靠性结果失败')
  } finally {
    loadingReport.value = false
  }
}

function percentage(value: number | null): string {
  return value === null ? '--' : `${(value * 100).toFixed(1)}%`
}

function decimal(value: number | null): string {
  return value === null ? '--' : value.toFixed(3)
}

function groupRowClassName({ row }: { row: { isOverall: boolean } }): string {
  return row.isOverall ? 'overall-table-row' : ''
}

function kappaStatus(value: number | null): { text: string; type: 'success' | 'warning' | 'danger' | 'info'; note: string } {
  if (value === null) return { text: '无法计算', type: 'info', note: '有效样本不足，或所有观点都落在同一类别。' }
  if (value >= 0.8) return { text: '一致性较强', type: 'success', note: '可以进入协商，同时仍应查看具体分歧。' }
  if (value >= 0.7) return { text: '基本可用', type: 'warning', note: '建议先检查主要分歧，尤其是 EX 与 IN。' }
  return { text: '建议优化规则', type: 'danger', note: '先保存本轮结果，优化手册后再进行新的独立编码；不要直接把答案改到一致。' }
}

function csvCell(value: string | number): string {
  return `"${String(value).split('"').join('""')}"`
}

function downloadCsv() {
  if (!report.value) return
  const header = ['group_id', 'group_name', 'session_id', 'session_title', 'unit_id', 'order_index', 'content', 'coder_a', 'coder_c', 'agreed']
  const rows = report.value.pairs.map(pair => [
    pair.groupId,
    pair.groupName,
    pair.sessionId,
    pair.sessionTitle,
    pair.unitId,
    pair.orderIndex,
    pair.content,
    pair.categoryA,
    pair.categoryC,
    pair.agreed ? '1' : '0',
  ])
  const metadata = [
    ['scope', scopeLabel.value],
    ['generated_at', generatedAt.value ?? ''],
    ['eligible_n', report.value.eligibleCount],
    ['observed_agreement', report.value.observedAgreement ?? ''],
    ['cohen_kappa', report.value.cohenKappa ?? ''],
  ]
  const groupSummaryHeader = ['group_id', 'group_name', 'total_n', 'eligible_n', 'agreement', 'cohen_kappa', 'missing_n', 'multi_code_n']
  const groupSummaryRows = groupReports.value.map(item => [
    item.groupId,
    item.groupName,
    item.report.totalCount,
    item.report.eligibleCount,
    item.report.observedAgreement ?? '',
    item.report.cohenKappa ?? '',
    item.report.missingCount,
    item.report.invalidMultiCount,
  ])
  const content = [
    ...metadata.map(row => row.map(csvCell).join(',')),
    '',
    groupSummaryHeader.map(csvCell).join(','),
    ...groupSummaryRows.map(row => row.map(csvCell).join(',')),
    '',
    header.map(csvCell).join(','),
    ...rows.map(row => row.map(csvCell).join(',')),
  ].join('\n')
  const blob = new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `coi-reliability-a-c-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function escapeHtml(value: string | number | null | undefined): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function htmlTable(headers: string[], rows: Array<Array<string | number>>, className = ''): string {
  const head = headers.map(header => `<th>${escapeHtml(header)}</th>`).join('')
  const body = rows.length > 0
    ? rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('')
    : `<tr><td colspan="${headers.length}" class="empty">无数据</td></tr>`
  return `<div class="table-wrap"><table class="${className}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`
}

function downloadHtml() {
  if (!report.value) return
  const currentReport = report.value
  const status = kappaStatus(currentReport.cohenKappa)
  const groupRows = groupReportRows.value.map(item => [
    item.groupName,
    item.report.totalCount,
    item.report.eligibleCount,
    percentage(item.report.observedAgreement),
    decimal(item.report.cohenKappa),
    item.report.disagreementCount,
    item.report.missingCount,
    item.report.invalidMultiCount,
  ])
  const matrixHeaders = ['A \\ C', ...COI_RELIABILITY_CATEGORIES.map(category => `${category} ${CATEGORY_LABELS[category]}`)]
  const matrixRows = COI_RELIABILITY_CATEGORIES.map(rowCategory => [
    `${rowCategory} ${CATEGORY_LABELS[rowCategory]}`,
    ...COI_RELIABILITY_CATEGORIES.map(columnCategory => currentReport.confusionMatrix[rowCategory][columnCategory]),
  ])
  const disagreementRows = currentReport.disagreements.map(pair => [
    pair.groupName,
    pair.sessionTitle,
    pair.orderIndex,
    pair.content,
    pair.categoryA,
    pair.categoryC,
  ])
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CoI 协商前可靠性报告（A–C）</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: #1e2d40; background: #f4f6f9; }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 32px 20px; }
    main { max-width: 1120px; margin: 0 auto; padding: 38px 42px; background: #fff; border: 1px solid #dfe4ec; border-radius: 12px; box-shadow: 0 8px 30px rgba(30,45,64,.08); }
    h1 { margin: 0 0 8px; font-size: 28px; }
    h2 { margin: 34px 0 14px; padding-bottom: 9px; border-bottom: 2px solid #e7edf5; font-size: 19px; }
    p { line-height: 1.7; }
    .subtitle, .meta, .note { color: #65748b; }
    .meta { display: grid; grid-template-columns: 120px 1fr; gap: 8px 14px; margin: 24px 0; padding: 16px 18px; background: #f6f8fb; border-radius: 8px; font-size: 14px; }
    .meta strong { color: #334155; }
    .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
    .card { padding: 16px; border: 1px solid #dfe4ec; border-radius: 8px; }
    .card span { display: block; color: #718098; font-size: 13px; }
    .card strong { display: block; margin-top: 5px; font-size: 25px; }
    .interpretation { margin-top: 12px; padding: 14px 16px; background: #fff8e8; border-left: 4px solid #e6a23c; border-radius: 4px; }
    .table-wrap { width: 100%; overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 10px 9px; border: 1px solid #dfe4ec; text-align: left; vertical-align: top; }
    th { background: #f3f6fa; white-space: nowrap; }
    .matrix th, .matrix td { text-align: center; }
    .matrix tbody td:not(:first-child) { font-weight: 600; }
    .empty { padding: 24px; color: #909399; text-align: center; }
    .footer { margin-top: 34px; padding-top: 16px; border-top: 1px solid #e5eaf1; color: #7b8799; font-size: 12px; }
    .print { position: fixed; top: 18px; right: 18px; padding: 9px 15px; color: #fff; background: #2563eb; border: 0; border-radius: 6px; cursor: pointer; }
    @media (max-width: 760px) { main { padding: 24px 18px; } .cards { grid-template-columns: repeat(2, 1fr); } .meta { grid-template-columns: 1fr; } }
    @media print { body { padding: 0; background: #fff; } main { max-width: none; padding: 0; border: 0; box-shadow: none; } .print { display: none; } h2 { break-after: avoid; } table, .card { break-inside: avoid; } }
  </style>
</head>
<body>
  <button class="print" onclick="window.print()">打印 / 保存为 PDF</button>
  <main>
    <h1>CoI 协商前可靠性报告（A–C）</h1>
    <p class="subtitle">研究员A与AI辅助研究员C的独立单编码一致性分析</p>
    <div class="meta">
      <strong>分析范围</strong><span>${escapeHtml(scopeLabel.value)}</span>
      <strong>生成时间</strong><span>${escapeHtml(generatedAt.value)}</span>
      <strong>数据性质</strong><span>生成时的实时计算结果；此HTML文件是独立导出副本，不会修改任何编码。</span>
    </div>

    <h2>结果摘要</h2>
    <div class="cards">
      <div class="card"><span>全部观点</span><strong>${currentReport.totalCount}</strong></div>
      <div class="card"><span>有效A/C配对</span><strong>${currentReport.eligibleCount}</strong></div>
      <div class="card"><span>原始一致率</span><strong>${percentage(currentReport.observedAgreement)}</strong></div>
      <div class="card"><span>Cohen’s κ</span><strong>${decimal(currentReport.cohenKappa)}</strong></div>
      <div class="card"><span>一致</span><strong>${currentReport.agreedCount}</strong></div>
      <div class="card"><span>分歧</span><strong>${currentReport.disagreementCount}</strong></div>
      <div class="card"><span>缺失A或C</span><strong>${currentReport.missingCount}</strong></div>
      <div class="card"><span>多编码异常</span><strong>${currentReport.invalidMultiCount}</strong></div>
    </div>
    <div class="interpretation"><strong>${escapeHtml(status.text)}</strong>：${escapeHtml(status.note)}</div>

    <h2>各群组与全部汇总</h2>
    ${htmlTable(['群组', '全部观点', '有效配对', '一致率', 'Cohen’s κ', '分歧', '缺失', '多编码异常'], groupRows)}

    <h2>A–C 编码混淆矩阵</h2>
    <p class="note">行代表研究员A，列代表研究员C；对角线表示一致。</p>
    ${htmlTable(matrixHeaders, matrixRows, 'matrix')}

    <h2>分歧明细（${currentReport.disagreementCount}条）</h2>
    ${htmlTable(['群组', '会话', '序号', '观点内容', '研究员A', '研究员C'], disagreementRows)}

    <p class="footer">说明：可靠性不是编码正确率，也不存在自动“70%及格”。如结果偏低，应保留本轮结果、优化编码手册，并重新进行独立编码。</p>
  </main>
</body>
</html>`
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `coi-reliability-a-c-${new Date().toISOString().slice(0, 10)}.html`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="reliability-page">
    <div class="page-header">
      <div>
        <h1>CoI 协商前可靠性（A–C）</h1>
        <p>比较研究员A与AI辅助研究员C的独立单编码结果；本页不会修改任何编码。</p>
      </div>
      <div class="page-actions">
        <el-button :icon="Download" :disabled="!report" @click="downloadCsv">导出协商前CSV</el-button>
        <el-button :icon="Download" :disabled="!report" @click="downloadHtml">导出HTML报告</el-button>
        <el-button type="primary" :icon="Refresh" :loading="loadingReport" :disabled="loadingSessions" @click="generateReport">生成可靠性结果</el-button>
      </div>
    </div>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="当前是实时计算结果，尚未保存为数据库中的不可变快照。导出CSV后再修改A或C，页面结果会随之变化。"
    />

    <el-card shadow="never" class="control-card">
      <div class="control-bar">
        <div class="control-item">
          <span class="control-label">群组（可多选）</span>
          <el-select v-model="selectedGroupIds" placeholder="选择一个或多个群组" filterable multiple collapse-tags collapse-tags-tooltip style="width: 320px" :loading="loadingGroups" @change="onGroupChange">
            <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
          </el-select>
          <el-button :disabled="groups.length === 0" @click="selectAllGroups">{{ allGroupsSelected ? '清空群组' : '全选群组' }}</el-button>
        </div>
        <div class="control-item">
          <span class="control-label">会话范围</span>
          <el-select v-model="selectedSessionId" style="width: 280px" :disabled="!isSingleGroup" :loading="loadingSessions" @change="onSessionChange">
            <el-option :label="isSingleGroup ? '当前群组全部会话' : '所选群组全部会话'" :value="ALL_SESSIONS" />
            <el-option v-for="session in sessions" :key="session.id" :label="session.session_title" :value="session.id" />
          </el-select>
        </div>
        <el-tag size="large" type="info">{{ scopeLabel }}</el-tag>
      </div>
    </el-card>

    <template v-if="report">
      <el-card shadow="never">
        <template #header>
          <div class="section-header">
            <div><strong>各群组与全部汇总</strong><span>每一组单独计算；最后一行将所有选中组的有效观点合并计算</span></div>
          </div>
        </template>
        <el-table :data="groupReportRows" border empty-text="当前范围没有群组结果" :row-class-name="groupRowClassName">
          <el-table-column prop="groupName" label="群组" min-width="180" />
          <el-table-column label="全部观点" width="105" align="center"><template #default="scope">{{ scope.row.report.totalCount }}</template></el-table-column>
          <el-table-column label="有效配对" width="105" align="center"><template #default="scope">{{ scope.row.report.eligibleCount }}</template></el-table-column>
          <el-table-column label="一致率" width="110" align="center"><template #default="scope">{{ percentage(scope.row.report.observedAgreement) }}</template></el-table-column>
          <el-table-column label="Cohen’s κ" width="115" align="center"><template #default="scope">{{ decimal(scope.row.report.cohenKappa) }}</template></el-table-column>
          <el-table-column label="分歧" width="85" align="center"><template #default="scope">{{ scope.row.report.disagreementCount }}</template></el-table-column>
          <el-table-column label="缺失" width="85" align="center"><template #default="scope">{{ scope.row.report.missingCount }}</template></el-table-column>
          <el-table-column label="多编码异常" width="110" align="center"><template #default="scope">{{ scope.row.report.invalidMultiCount }}</template></el-table-column>
        </el-table>
      </el-card>

      <el-row :gutter="12">
        <el-col :xs="12" :sm="8" :lg="4">
          <el-card shadow="never" class="summary-card"><span>全部观点</span><strong>{{ report.totalCount }}</strong></el-card>
        </el-col>
        <el-col :xs="12" :sm="8" :lg="4">
          <el-card shadow="never" class="summary-card"><span>有效A/C配对</span><strong>{{ report.eligibleCount }}</strong></el-card>
        </el-col>
        <el-col :xs="12" :sm="8" :lg="4">
          <el-card shadow="never" class="summary-card"><span>一致</span><strong>{{ report.agreedCount }}</strong></el-card>
        </el-col>
        <el-col :xs="12" :sm="8" :lg="4">
          <el-card shadow="never" class="summary-card"><span>分歧</span><strong>{{ report.disagreementCount }}</strong></el-card>
        </el-col>
        <el-col :xs="12" :sm="8" :lg="4">
          <el-card shadow="never" class="summary-card"><span>缺失A或C</span><strong>{{ report.missingCount }}</strong></el-card>
        </el-col>
        <el-col :xs="12" :sm="8" :lg="4">
          <el-card shadow="never" class="summary-card"><span>多编码异常</span><strong>{{ report.invalidMultiCount }}</strong></el-card>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :xs="24" :md="12">
          <el-card shadow="never" class="metric-card">
            <div class="metric-label">原始一致率</div>
            <div class="metric-value">{{ percentage(report.observedAgreement) }}</div>
            <p>{{ report.agreedCount }} / {{ report.eligibleCount }} 条有效观点完全一致</p>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="never" class="metric-card">
            <div class="metric-heading">
              <div><div class="metric-label">Cohen’s κ</div><div class="metric-value">{{ decimal(report.cohenKappa) }}</div></div>
              <el-tag :type="kappaStatus(report.cohenKappa).type" size="large">{{ kappaStatus(report.cohenKappa).text }}</el-tag>
            </div>
            <p>{{ kappaStatus(report.cohenKappa).note }}</p>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never">
        <template #header>
          <div class="section-header">
            <div><strong>A–C 编码混淆矩阵</strong><span>行=研究员A，列=研究员C；对角线为一致</span></div>
          </div>
        </template>
        <div class="matrix-wrap">
          <table class="matrix-table">
            <thead><tr><th>A \ C</th><th v-for="category in COI_RELIABILITY_CATEGORIES" :key="category">{{ category }}<small>{{ CATEGORY_LABELS[category] }}</small></th></tr></thead>
            <tbody>
              <tr v-for="rowCategory in COI_RELIABILITY_CATEGORIES" :key="rowCategory">
                <th>{{ rowCategory }}<small>{{ CATEGORY_LABELS[rowCategory] }}</small></th>
                <td v-for="columnCategory in COI_RELIABILITY_CATEGORIES" :key="columnCategory" :class="{ diagonal: rowCategory === columnCategory, mismatch: rowCategory !== columnCategory && report.confusionMatrix[rowCategory][columnCategory] > 0 }">
                  {{ report.confusionMatrix[rowCategory][columnCategory] }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="section-header">
            <div><strong>分歧明细</strong><span>这里只读展示，不会进入协商或修改编码</span></div>
            <el-tag type="warning">{{ report.disagreementCount }} 条</el-tag>
          </div>
        </template>
        <el-table :data="report.disagreements" border max-height="460" empty-text="当前范围没有A/C分歧">
          <el-table-column prop="groupName" label="群组" min-width="140" show-overflow-tooltip />
          <el-table-column prop="sessionTitle" label="会话" min-width="150" show-overflow-tooltip />
          <el-table-column prop="orderIndex" label="序号" width="70" align="center" />
          <el-table-column prop="content" label="观点内容" min-width="360" />
          <el-table-column label="研究员A" width="105" align="center"><template #default="scope"><el-tag>{{ scope.row.categoryA }}</el-tag></template></el-table-column>
          <el-table-column label="研究员C" width="105" align="center"><template #default="scope"><el-tag type="warning">{{ scope.row.categoryC }}</el-tag></template></el-table-column>
        </el-table>
      </el-card>

      <el-alert type="info" :closable="false" show-icon>
        <template #default>
          <span>生成时间：{{ generatedAt }}。可靠性不是正确率，也没有自动“70%及格”；若结果偏低，应保存本轮、优化手册后重新独立编码。</span>
          <el-button type="primary" link @click="router.push('/admin/coi-agreement')">查看最终协商页面</el-button>
        </template>
      </el-alert>
    </template>

    <el-card v-else shadow="never" class="empty-card">
      <el-empty description="选择群组和会话范围，然后生成A–C协商前可靠性结果" />
    </el-card>
  </div>
</template>

<style scoped>
.reliability-page { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.page-header h1 { margin: 0; color: #1e2d40; font-size: 20px; font-weight: 600; }
.page-header p { margin: 6px 0 0; color: #627089; font-size: 14px; }
.page-actions, .control-bar, .control-item, .section-header, .metric-heading { display: flex; align-items: center; gap: 10px; }
.page-actions { flex-wrap: wrap; justify-content: flex-end; }
.control-bar { flex-wrap: wrap; }
.control-label { color: #606266; font-size: 14px; white-space: nowrap; }
.summary-card { margin-bottom: 4px; }
.summary-card :deep(.el-card__body) { display: flex; flex-direction: column; gap: 5px; padding: 13px 16px; }
.summary-card span, .metric-label { color: #718098; font-size: 13px; }
.summary-card strong { color: #1e2d40; font-size: 22px; }
.metric-card { min-height: 138px; }
.metric-card :deep(.el-card__body) { padding: 18px 20px; }
.metric-value { margin-top: 6px; color: #1e2d40; font-size: 34px; font-weight: 700; }
.metric-card p { margin: 9px 0 0; color: #718098; font-size: 13px; line-height: 1.6; }
.metric-heading { justify-content: space-between; align-items: flex-start; }
.section-header { justify-content: space-between; flex-wrap: wrap; }
.section-header div { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.section-header span { color: #909399; font-size: 13px; }
.matrix-wrap { overflow-x: auto; }
.matrix-table { width: 100%; min-width: 620px; border-collapse: collapse; table-layout: fixed; }
.matrix-table th, .matrix-table td { border: 1px solid #dcdfe6; padding: 12px; text-align: center; }
.matrix-table th { color: #606266; background: #f5f7fa; }
.matrix-table small { display: block; margin-top: 3px; color: #909399; font-weight: 400; }
.matrix-table td.diagonal { color: #15803d; background: #f0fdf4; font-weight: 700; }
.matrix-table td.mismatch { color: #b45309; background: #fff3bf; font-weight: 700; }
.reliability-page :deep(.overall-table-row td.el-table__cell) { background: #eef5ff !important; font-weight: 700; }
.empty-card { min-height: 320px; display: flex; align-items: center; justify-content: center; }
@media (max-width: 800px) {
  .page-header { flex-direction: column; }
  .page-actions { justify-content: flex-start; }
}
</style>
