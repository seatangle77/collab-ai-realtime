<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getMyVoiceProfile,
  updateMySamples,
  generateMyEmbedding,
  uploadMyVoiceSample,
  type VoiceProfileOut,
} from '../../api/appVoiceProfile'
import { formatDateTimeToCST } from '../../utils/datetime'

const loading = ref(false)
const savingSamples = ref(false)
const generating = ref(false)
const isRecording = ref(false)
const isUploading = ref(false)
const activeRecordTab = ref<'record' | 'url'>('record')

const profile = ref<VoiceProfileOut | null>(null)
const editableUrls = ref<string[]>([])
const newUrlInput = ref('')
const recordedChunks = ref<BlobPart[]>([])
const recordingDuration = ref(0)
const previewUrl = ref<string | null>(null)
const mediaRecorder = ref<MediaRecorder | null>(null)
let recordingTimer: number | undefined

const hasEmbedding = computed(() => !!profile.value?.voice_embedding)

function parseEmbeddingStatusLabel(): string {
  const status = profile.value?.embedding_status
  if (status === 'not_generated') return '未生成'
  if (status === 'ready') return '已就绪'
  return status || '-'
}

function parseGeneratedAt(): string | null {
  const emb = profile.value?.voice_embedding
  if (!emb) return null
  const raw = (emb as Record<string, unknown>).generated_at
  if (typeof raw !== 'string') return null
  return formatDateTimeToCST(raw)
}

function parseEmbeddingUpdatedAt(): string {
  const raw = profile.value?.embedding_updated_at
  if (!raw) return '-'
  return formatDateTimeToCST(raw)
}

async function fetchProfile() {
  loading.value = true
  try {
    const data = await getMyVoiceProfile()
    profile.value = data
    editableUrls.value = [...(data.sample_audio_urls || [])]
  } catch (err: unknown) {
    console.error(err)
    ElMessage.error((err as Error)?.message || '加载声纹失败')
  } finally {
    loading.value = false
  }
}

async function handleRemoveUrl(idx: number) {
  editableUrls.value.splice(idx, 1)
  await handleSaveSamples()
}

async function handleAddUrl() {
  const v = newUrlInput.value.trim()
  if (!v) {
    ElMessage.warning('请输入非空的样本 URL')
    return
  }
  if (editableUrls.value.length >= 5) {
    ElMessage.warning('已达到最多 5 条样本')
    return
  }
  editableUrls.value.push(v)
  newUrlInput.value = ''
  await handleSaveSamples()
}

async function handleSaveSamples() {
  if (!profile.value) return
  savingSamples.value = true
  try {
    const updated = await updateMySamples(editableUrls.value)
    profile.value = updated
    editableUrls.value = [...(updated.sample_audio_urls || [])]
    ElMessage.success('已保存')
  } catch (err: unknown) {
    console.error(err)
    ElMessage.error((err as Error)?.message || '保存样本列表失败')
  } finally {
    savingSamples.value = false
  }
}

async function startRecording() {
  if (isRecording.value) return
  if (editableUrls.value.length >= 5) {
    ElMessage.warning('已达到最多 5 条样本，无法继续录音')
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' })
    recordedChunks.value = []
    recordingDuration.value = 0

    mr.ondataavailable = (event: BlobEvent) => {
      if (event.data.size > 0) {
        recordedChunks.value.push(event.data)
      }
    }

    mr.onstop = () => {
      window.clearInterval(recordingTimer)
      if (previewUrl.value) {
        URL.revokeObjectURL(previewUrl.value)
        previewUrl.value = null
      }
      if (recordedChunks.value.length) {
        const blob = new Blob(recordedChunks.value, { type: 'audio/webm' })
        previewUrl.value = URL.createObjectURL(blob)
      }
    }

    mr.start()
    isRecording.value = true
    mediaRecorder.value = mr

    recordingTimer = window.setInterval(() => {
      recordingDuration.value += 1
    }, 1000)
  } catch (err: unknown) {
    console.error(err)
    ElMessage.error('无法访问麦克风，请检查浏览器权限设置')
  }
}

function stopRecording() {
  if (!isRecording.value || !mediaRecorder.value) return
  mediaRecorder.value.stop()
  mediaRecorder.value.stream.getTracks().forEach((t) => t.stop())
  isRecording.value = false
}

function resetRecording() {
  if (isRecording.value) {
    stopRecording()
  }
  recordedChunks.value = []
  recordingDuration.value = 0
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
}

function handleTabChange(tab: 'record' | 'url') {
  if (tab !== activeRecordTab.value) {
    resetRecording()
    activeRecordTab.value = tab
  }
}

async function handleUploadRecordedSample() {
  if (!recordedChunks.value.length) {
    ElMessage.warning('请先录制一段音频')
    return
  }
  if (editableUrls.value.length >= 5) {
    ElMessage.warning('已达到最多 5 条样本')
    return
  }

  const blob = new Blob(recordedChunks.value, { type: 'audio/webm' })
  const file = new File([blob], `voice-sample-${Date.now()}.webm`, { type: blob.type })

  isUploading.value = true
  try {
    const { url } = await uploadMyVoiceSample(file)
    editableUrls.value = [...editableUrls.value, url]
    await handleSaveSamples()
    ElMessage.success('录音已上传并添加到样本列表')
    resetRecording()
  } catch (err: unknown) {
    console.error(err)
    ElMessage.error((err as Error)?.message || '上传录音失败')
  } finally {
    isUploading.value = false
  }
}

async function handleGenerateEmbedding() {
  if (!profile.value) return
  if (!editableUrls.value.length) {
    ElMessage.warning('请先添加样本 URL 后再生成声纹')
    return
  }
  if (hasEmbedding.value) {
    try {
      await ElMessageBox.confirm(
        '将根据当前样本列表重新生成声纹，可能会覆盖之前的结果，确定继续吗？',
        '重新生成声纹',
        { type: 'warning', confirmButtonText: '生成', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }

  generating.value = true
  try {
    const updated = await generateMyEmbedding()
    profile.value = updated
    ElMessage.success(hasEmbedding.value ? '声纹已重新生成' : '声纹已生成')
  } catch (err: unknown) {
    console.error(err)
    ElMessage.error((err as Error)?.message || '生成声纹失败')
  } finally {
    generating.value = false
  }
}

onMounted(() => {
  void fetchProfile()
})
</script>

<template>
  <div class="app-voice-profile">
    <div class="app-voice-profile-card" v-loading="loading">
      <h2 class="app-voice-profile-title">我的声纹</h2>
      <p class="app-voice-profile-desc">录制或上传音频样本，生成专属声纹用于说话人识别。</p>

      <template v-if="profile">
        <div class="section-divider">第一步：添加音频样本</div>
        <el-card class="record-card" shadow="never">
          <div class="record-tabs">
            <button
              class="record-tab"
              :class="{ active: activeRecordTab === 'record' }"
              @click="handleTabChange('record')"
            >现场录音</button>
            <button
              class="record-tab"
              :class="{ active: activeRecordTab === 'url' }"
              @click="handleTabChange('url')"
            >粘贴 URL</button>
          </div>

          <!-- Tab: 现场录音 -->
          <div v-if="activeRecordTab === 'record'" class="tab-panel">
            <!-- 未录音 -->
            <template v-if="!isRecording && !previewUrl">
              <el-button
                type="primary"
                size="default"
                :disabled="editableUrls.length >= 5"
                @click="startRecording"
              >开始录音</el-button>
              <span class="recording-hint">每段建议 10–15 秒</span>
            </template>

            <!-- 录音中 -->
            <template v-else-if="isRecording">
              <el-button type="danger" size="default" @click="stopRecording">停止录音</el-button>
              <span class="recording-indicator">录音中… {{ recordingDuration }}s</span>
            </template>

            <!-- 录完，预览 -->
            <template v-else-if="previewUrl">
              <audio :src="previewUrl" controls class="preview-audio" />
              <div class="preview-actions">
                <el-button size="default" @click="resetRecording">重新录制</el-button>
                <el-button
                  type="primary"
                  size="default"
                  :loading="isUploading"
                  :disabled="editableUrls.length >= 5"
                  @click="handleUploadRecordedSample"
                >添加此段</el-button>
              </div>
            </template>
          </div>

          <!-- Tab: 粘贴 URL -->
          <div v-if="activeRecordTab === 'url'" class="tab-panel">
            <div class="url-add-row">
              <el-input
                v-model="newUrlInput"
                size="default"
                placeholder="粘贴音频 URL"
                class="url-input"
                @keyup.enter.prevent="handleAddUrl"
              />
              <el-button type="primary" size="default" @click="handleAddUrl">添加</el-button>
            </div>
          </div>
        </el-card>

        <div class="section-divider">
          已添加 {{ editableUrls.length }} / 5 条样本
        </div>
        <div class="samples-editor">
          <div class="samples-list">
            <div v-if="editableUrls.length === 0" class="samples-empty">
              暂无样本，请在上方添加。
            </div>
            <div
              v-for="(url, idx) in editableUrls"
              :key="idx"
              class="sample-row"
            >
              <span class="sample-index">{{ idx + 1 }}</span>
              <audio :src="url" controls class="sample-audio" />
              <el-button type="danger" plain size="small" @click="handleRemoveUrl(idx)">删除</el-button>
            </div>
          </div>
        </div>

        <div class="section-divider">第二步：生成声纹</div>

        <!-- 未生成 / 可生成 -->
        <div v-if="!hasEmbedding" class="embedding-block">
          <el-button
            type="primary"
            size="default"
            :loading="generating"
            :disabled="editableUrls.length === 0"
            @click="handleGenerateEmbedding"
          >生成声纹</el-button>
          <span v-if="editableUrls.length === 0" class="generate-hint">至少需要 1 条样本</span>
        </div>

        <!-- 已生成 -->
        <div v-else class="embedding-done">
          <div class="embedding-done-info">
            <el-tag type="success" size="small" effect="light">声纹已生成</el-tag>
            <span v-if="parseGeneratedAt()" class="embedding-done-time">生成于 {{ parseGeneratedAt() }}</span>
          </div>
          <el-button
            link
            type="primary"
            size="small"
            :loading="generating"
            @click="handleGenerateEmbedding"
          >重新生成</el-button>
        </div>

        <el-collapse class="detail-collapse">
          <el-collapse-item name="detail">
            <template #title>
              <span class="collapse-title">详细信息</span>
            </template>
            <div class="detail-fields">
              <span class="detail-item">嵌入状态：{{ parseEmbeddingStatusLabel() }}</span>
              <span class="detail-item">创建时间：{{ formatDateTimeToCST(profile.created_at) }}</span>
              <span class="detail-item">最近更新：{{ parseEmbeddingUpdatedAt() }}</span>
            </div>
            <pre v-if="profile.voice_embedding" class="embedding-json">{{ JSON.stringify(profile.voice_embedding, null, 2) }}</pre>
          </el-collapse-item>
        </el-collapse>
      </template>
    </div>
  </div>
</template>

<style scoped>
.app-voice-profile {
  display: flex;
  justify-content: center;
}

.app-voice-profile-card {
  width: 100%;
  max-width: 720px;
  padding: 20px 22px;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
  border: 1px solid #e5e7eb;
}

.app-voice-profile-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #111827;
}

.app-voice-profile-desc {
  margin: 0 0 20px;
  font-size: 13px;
  line-height: 1.6;
  color: #4b5563;
}

.section-divider {
  margin: 20px 0 12px;
  padding-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  border-bottom: 1px solid #e5e7eb;
}

.section-divider:first-of-type {
  margin-top: 0;
}

.record-card {
  border-radius: 10px;
  background: #f9fafb;
}

.recording-indicator {
  font-size: 13px;
  color: #dc2626;
}

.recording-hint {
  font-size: 12px;
  color: #9ca3af;
}

.preview-audio {
  width: 100%;
  max-width: 100%;
}

.preview-actions {
  display: flex;
  gap: 10px;
}

.samples-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.samples-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.sample-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.sample-index {
  flex-shrink: 0;
  width: 20px;
  font-size: 13px;
  color: #9ca3af;
  text-align: right;
}

.sample-audio {
  flex: 1;
  min-width: 0;
}

.samples-empty {
  font-size: 12px;
  color: #9ca3af;
  padding: 8px 0;
}

.embedding-block {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 0;
}

/* Tab 切换 */
.record-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  border-bottom: 1px solid #e5e7eb;
}

.record-tab {
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #6b7280;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
  margin-bottom: -1px;
}

.record-tab.active {
  color: #2563eb;
  border-bottom-color: #2563eb;
}

.tab-panel {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  min-height: 40px;
}

.url-add-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.url-input {
  flex: 1;
}

/* 生成声纹区 */
.generate-hint {
  font-size: 12px;
  color: #9ca3af;
}

.embedding-done {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 0;
}

.embedding-done-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.embedding-done-time {
  font-size: 12px;
  color: #6b7280;
}

/* 详细信息折叠 */
.detail-collapse {
  margin-top: 16px;
}

.detail-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: #6b7280;
}

.collapse-title {
  font-weight: 500;
}

.detail-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  margin-bottom: 10px;
  font-size: 12px;
  color: #6b7280;
}

.detail-item {
  white-space: nowrap;
}

.embedding-json {
  margin: 0;
  padding: 12px;
  border-radius: 6px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 200px;
  overflow-y: auto;
}
</style>
