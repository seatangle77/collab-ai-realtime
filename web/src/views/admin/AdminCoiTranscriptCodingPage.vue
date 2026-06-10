<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import { listAdminGroups } from '../../api/admin/groups'
import { listAdminChatSessions } from '../../api/admin/chat-sessions'
import { getUtteranceCount, saveTranscriptUtterances } from '../../api/admin/coi-transcript-coding'
import type { AdminGroup, AdminChatSession } from '../../types/admin'

// ── Types ─────────────────────────────────────────────────────────────────────

interface DraftLine {
  key: number
  content: string
  startTime: number | null
  endTime: number | null
}

const FILLER_RE = /^[\s嗯啊哦哈哎呀哟喂呵嘻吧呢是好对、，。！？…—·]+$/
const LINE_RE = /^\[(\d+):(\d+(?:\.\d+)?),(\d+):(\d+(?:\.\d+)?),\d+\]\s+(.+)$/

// ── 群组 / 会话 ────────────────────────────────────────────────────────────────

const groups = ref<AdminGroup[]>([])
const sessions = ref<AdminChatSession[]>([])
const selectedGroupId = ref('')
const selectedSessionId = ref('')
const existingCount = ref(0)
const loadingGroups = ref(false)
const loadingSessions = ref(false)

onMounted(async () => {
  loadingGroups.value = true
  try {
    const res = await listAdminGroups({ page_size: 200 })
    groups.value = res.items
  } catch (e: any) {
    ElMessage.error(e?.message || '加载群组失败')
  } finally {
    loadingGroups.value = false
  }
})

async function onGroupChange() {
  selectedSessionId.value = ''
  existingCount.value = 0
  sessions.value = []
  resetContent()
  if (!selectedGroupId.value) return
  loadingSessions.value = true
  try {
    const res = await listAdminChatSessions({ group_id: selectedGroupId.value, page_size: 200 })
    sessions.value = res.items
    if (res.items.length > 0) {
      selectedSessionId.value = res.items[0].id
      await checkExisting()
    }
  } finally {
    loadingSessions.value = false
  }
}

async function onSessionChange() {
  existingCount.value = 0
  resetContent()
  await checkExisting()
}

async function checkExisting() {
  if (!selectedSessionId.value) return
  try {
    const res = await getUtteranceCount(selectedSessionId.value)
    existingCount.value = res.count
  } catch {}
}

// ── 文件解析 ───────────────────────────────────────────────────────────────────

const filterEnabled = ref(true)
const rawLines = ref<DraftLine[]>([])
const uploadedFileName = ref('')
let keyCounter = 0

function parseTime(min: string, sec: string) {
  return parseInt(min, 10) * 60 + parseFloat(sec)
}

function fmt(s: number | null): string {
  if (s == null) return '--'
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1).padStart(4, '0')
  return `${m}:${sec}`
}

function resetContent() {
  rawLines.value = []
  lines.value = []
  uploadedFileName.value = ''
}

function handleFileChange(file: UploadFile) {
  if (!selectedSessionId.value) {
    ElMessage.warning('请先选择群组和会话')
    return
  }
  const raw = file.raw
  if (!raw) return
  uploadedFileName.value = file.name
  const reader = new FileReader()
  reader.onload = evt => {
    keyCounter = 0
    rawLines.value = (evt.target?.result as string)
      .split('\n')
      .map(l => l.trim().match(LINE_RE))
      .filter((m): m is RegExpMatchArray => !!m)
      .map(m => ({
        key: ++keyCounter,
        content: m[5].trim(),
        startTime: parseTime(m[1], m[2]),
        endTime: parseTime(m[3], m[4]),
      }))
    applyFilter()
  }
  reader.readAsText(raw, 'utf-8')
}

const lines = ref<DraftLine[]>([])
const removedCount = computed(() => rawLines.value.length - lines.value.length)

function applyFilter() {
  keyCounter = 0
  lines.value = (filterEnabled.value
    ? rawLines.value.filter(l => !FILLER_RE.test(l.content))
    : [...rawLines.value]
  ).map(l => ({ ...l, key: ++keyCounter }))
}

watch(filterEnabled, applyFilter)

// ── 编辑操作 ───────────────────────────────────────────────────────────────────

function deleteLine(index: number) {
  lines.value.splice(index, 1)
}

function mergeDown(index: number) {
  if (index >= lines.value.length - 1) return
  const a = lines.value[index]
  const b = lines.value[index + 1]
  a.content = a.content + ' ' + b.content
  a.endTime = b.endTime
  lines.value.splice(index + 1, 1)
}

// ── 保存 ───────────────────────────────────────────────────────────────────────

const saving = ref(false)

async function handleSave() {
  if (!selectedSessionId.value) { ElMessage.warning('请先选择会话'); return }
  if (lines.value.length === 0) { ElMessage.warning('没有可保存的内容'); return }

  try {
    await ElMessageBox.confirm(
      `将保存 ${lines.value.length} 条预处理话语。${existingCount.value > 0 ? `原有 ${existingCount.value} 条数据将被覆盖。` : ''}确认保存？`,
      '确认保存预处理结果',
      { type: 'warning', confirmButtonText: '保存', cancelButtonText: '取消' },
    )
  } catch { return }

  saving.value = true
  try {
    const payload = lines.value.map((l, i) => ({
      order_index: i + 1,
      content: l.content,
      start_time: l.startTime,
      coi_category: null,
    }))
    const res = await saveTranscriptUtterances(selectedSessionId.value, payload)
    ElMessage.success(`预处理保存成功：${res.saved} 条${res.deleted_previous > 0 ? `，覆盖旧数据 ${res.deleted_previous} 条` : ''}`)
    existingCount.value = res.saved
    resetContent()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">CoI 预处理（录音转写）</h2>
      <span class="header-desc">上传腾讯 ASR 的 TXT → 清洗 → 保存，之后到「CoI 编码（录音转写）」完成编码</span>
    </div>

    <!-- 控制栏 -->
    <el-card shadow="never" class="control-card">
      <div class="control-bar">
        <div class="control-left">
          <div class="control-item">
            <span class="control-label">群组</span>
            <el-select
              v-model="selectedGroupId"
              placeholder="选择群组"
              style="width: 200px"
              :loading="loadingGroups"
              filterable
              @change="onGroupChange"
            >
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </div>

          <div v-if="sessions.length > 0" class="control-item">
            <span class="control-label">会话</span>
            <el-select
              v-model="selectedSessionId"
              style="width: 240px"
              :loading="loadingSessions"
              filterable
              @change="onSessionChange"
            >
              <el-option v-for="s in sessions" :key="s.id" :label="s.session_title" :value="s.id" />
            </el-select>
            <el-tag v-if="existingCount > 0" type="warning" size="small">
              已有 {{ existingCount }} 条，将覆盖
            </el-tag>
            <el-tag v-else-if="selectedSessionId" type="info" size="small">无预处理数据</el-tag>
          </div>
        </div>

        <div class="control-right">
          <template v-if="lines.length > 0">
            <div class="filter-item">
              <el-switch v-model="filterEnabled" size="small" />
              <span class="filter-label">过滤填充词</span>
              <el-tag v-if="filterEnabled && removedCount > 0" type="info" size="small">
                已过滤 {{ removedCount }} 条
              </el-tag>
            </div>
            <span class="count-text">共 {{ lines.length }} 条</span>
          </template>

          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            accept=".txt"
            :on-change="handleFileChange"
          >
            <el-button :type="lines.length ? 'default' : 'primary'" plain>
              <el-icon style="margin-right:4px"><UploadFilled /></el-icon>
              {{ uploadedFileName || '上传 TXT 文件' }}
            </el-button>
          </el-upload>

          <el-button
            v-if="lines.length > 0"
            type="primary"
            :loading="saving"
            @click="handleSave"
          >
            保存预处理结果
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 话语列表 -->
    <el-card v-if="lines.length > 0" shadow="never">
      <template #header>
        <div class="list-header">
          <span class="list-title">预处理话语列表</span>
          <span class="list-desc">保存后，在「CoI 编码（录音转写）」页逐条打标签</span>
        </div>
      </template>

      <div class="line-list">
        <div v-for="(line, i) in lines" :key="line.key" class="line-row">
          <span class="line-num">{{ i + 1 }}</span>
          <span class="line-time">{{ fmt(line.startTime) }}</span>
          <span class="line-content">{{ line.content }}</span>
          <div class="line-actions">
            <el-button link size="small" :disabled="i === lines.length - 1" @click="mergeDown(i)">
              合并↓
            </el-button>
            <el-button link type="danger" size="small" @click="deleteLine(i)">删除</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 空状态 -->
    <el-card v-else shadow="never" class="empty-card">
      <el-empty
        :image-size="120"
        :description="selectedSessionId ? '请上传腾讯 ASR 导出的 TXT 文件' : '请先选择群组'"
      />
    </el-card>
  </div>
</template>

<style scoped>
.page-container { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.header-desc { font-size: 13px; color: #909399; }

.control-card :deep(.el-card__body) { padding: 14px 20px; }
.control-bar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.control-left { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.control-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.control-item { display: flex; align-items: center; gap: 8px; }
.control-label { font-size: 13px; color: #606266; white-space: nowrap; }
.filter-item { display: flex; align-items: center; gap: 6px; }
.filter-label { font-size: 13px; color: #606266; }
.count-text { font-size: 13px; color: #606266; }

.list-header { display: flex; align-items: center; gap: 10px; }
.list-title { font-size: 14px; font-weight: 600; color: #303133; }
.list-desc { font-size: 12px; color: #909399; }

.line-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: calc(100vh - 320px);
  overflow-y: auto;
}
.line-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  transition: background 0.12s;
}
.line-row:hover { background: #f5f7fa; }
.line-num { width: 28px; flex-shrink: 0; text-align: right; font-size: 11px; color: #c0c4cc; font-weight: 600; }
.line-time { width: 46px; flex-shrink: 0; font-size: 11px; color: #909399; }
.line-content { flex: 1; color: #303133; line-height: 1.5; word-break: break-all; }
.line-actions { display: flex; gap: 4px; flex-shrink: 0; opacity: 0; }
.line-row:hover .line-actions { opacity: 1; }

.empty-card :deep(.el-card__body) { display: flex; align-items: center; justify-content: center; min-height: 300px; }
</style>
