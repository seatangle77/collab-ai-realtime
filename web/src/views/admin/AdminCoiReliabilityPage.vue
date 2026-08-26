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
const selectedGroupId = ref('')
const selectedSessionId = ref(ALL_SESSIONS)
const loadingGroups = ref(false)
const loadingSessions = ref(false)
const loadingReport = ref(false)
const report = ref<CoiReliabilityResult | null>(null)
const generatedAt = ref<string | null>(null)

const selectedGroup = computed(() => groups.value.find(group => group.id === selectedGroupId.value) ?? null)
const scopeLabel = computed(() => {
  if (!selectedGroup.value) return '尚未选择范围'
  if (selectedSessionId.value === ALL_SESSIONS) return `${selectedGroup.value.name} · 全部会话`
  const session = sessions.value.find(item => item.id === selectedSessionId.value)
  return `${selectedGroup.value.name} · ${session?.session_title ?? '当前会话'}`
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

async function onGroupChange() {
  sessions.value = []
  selectedSessionId.value = ALL_SESSIONS
  report.value = null
  generatedAt.value = null
  if (!selectedGroupId.value) return
  loadingSessions.value = true
  try {
    const response = await listAdminChatSessions({ group_id: selectedGroupId.value, page_size: 200 })
    sessions.value = response.items
  } catch (error: any) {
    ElMessage.error(error?.message || '加载会话失败')
  } finally {
    loadingSessions.value = false
  }
}

function onSessionChange() {
  report.value = null
  generatedAt.value = null
}

function toInputs(rows: AgreementUnit[], sessionTitle: string): CoiReliabilityInput[] {
  return rows.map(row => ({
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
  if (!selectedGroupId.value) {
    ElMessage.warning('请先选择群组')
    return
  }
  const selectedSessions = selectedSessionId.value === ALL_SESSIONS
    ? sessions.value
    : sessions.value.filter(session => session.id === selectedSessionId.value)
  if (selectedSessions.length === 0) {
    ElMessage.warning('当前范围没有可分析的会话')
    return
  }

  loadingReport.value = true
  try {
    const results = await Promise.all(selectedSessions.map(async (session) => {
      const rows = await getCoiAgreement(session.id)
      return toInputs(rows, session.session_title)
    }))
    report.value = calculateCoiReliability(results.flat())
    generatedAt.value = new Date().toLocaleString('zh-CN', { hour12: false })
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
  const header = ['session_id', 'session_title', 'unit_id', 'order_index', 'content', 'coder_a', 'coder_c', 'agreed']
  const rows = report.value.pairs.map(pair => [
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
  const content = [
    ...metadata.map(row => row.map(csvCell).join(',')),
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
        <el-button type="primary" :icon="Refresh" :loading="loadingReport" @click="generateReport">生成可靠性结果</el-button>
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
          <span class="control-label">群组</span>
          <el-select v-model="selectedGroupId" placeholder="选择群组" filterable style="width: 220px" :loading="loadingGroups" @change="onGroupChange">
            <el-option v-for="group in groups" :key="group.id" :label="group.name" :value="group.id" />
          </el-select>
        </div>
        <div class="control-item">
          <span class="control-label">会话范围</span>
          <el-select v-model="selectedSessionId" style="width: 280px" :disabled="!selectedGroupId" :loading="loadingSessions" @change="onSessionChange">
            <el-option label="当前群组全部会话" :value="ALL_SESSIONS" />
            <el-option v-for="session in sessions" :key="session.id" :label="session.session_title" :value="session.id" />
          </el-select>
        </div>
        <el-tag size="large" type="info">{{ scopeLabel }}</el-tag>
      </div>
    </el-card>

    <template v-if="report">
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
.empty-card { min-height: 320px; display: flex; align-items: center; justify-content: center; }
@media (max-width: 800px) {
  .page-header { flex-direction: column; }
  .page-actions { justify-content: flex-start; }
}
</style>
