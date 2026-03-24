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

function handleRemoveUrl(idx: number) {
  editableUrls.value.splice(idx, 1)
}

function handleAddUrl() {
  const v = newUrlInput.value.trim()
  if (!v) {
    ElMessage.warning('请输入非空的样本 URL')
    return
  }
  editableUrls.value.push(v)
  newUrlInput.value = ''
}

async function handleSaveSamples() {
  if (!profile.value) return
  savingSamples.value = true
  try {
    const updated = await updateMySamples(editableUrls.value)
    profile.value = updated
    editableUrls.value = [...(updated.sample_audio_urls || [])]
    ElMessage.success('样本列表已保存')
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
      <p class="app-voice-profile-desc">
        在此管理你的声纹样本并生成声纹。你可以直接在页面录音上传，或手动添加样本 URL，保存后点击「生成声纹」或「重新生成声纹」。
      </p>

      <template v-if="profile">
        <div class="section-divider">录音采集</div>
        <el-card class="record-card" shadow="never">
          <div class="record-controls">
            <el-button
              type="primary"
              size="default"
              :disabled="isRecording || editableUrls.length >= 5"
              @click="startRecording"
            >
              开始录音
            </el-button>
            <el-button type="warning" size="default" :disabled="!isRecording" @click="stopRecording">
              停止
            </el-button>
            <el-button
              size="default"
              :disabled="isRecording || !recordedChunks.length"
              @click="resetRecording"
            >
              重录
            </el-button>
            <span v-if="isRecording" class="recording-indicator">录音中... {{ recordingDuration }}s</span>
            <span v-else class="recording-hint">每段建议控制在 10–15 秒内</span>
          </div>
          <div v-if="previewUrl" class="record-preview">
            <p class="preview-title">录音预览</p>
            <audio :src="previewUrl" controls class="preview-audio" />
            <el-button
              type="success"
              size="default"
              :loading="isUploading"
              :disabled="editableUrls.length >= 5"
              @click="handleUploadRecordedSample"
            >
              上传并添加为样本
            </el-button>
          </div>
        </el-card>

        <div class="section-divider">样本列表</div>
        <div class="samples-editor">
          <p class="samples-count-tip">样本数量：{{ editableUrls.length }}/5（最多 5 条）</p>
          <div class="samples-list">
            <div
              v-for="(url, idx) in editableUrls"
              :key="idx"
              class="sample-row"
            >
              <span class="sample-index">样本 {{ idx + 1 }}</span>
              <el-input v-model="editableUrls[idx]" size="default" class="sample-input" />
              <audio
                v-if="url"
                :src="url"
                controls
                class="sample-audio"
              />
              <el-button type="danger" plain size="default" @click="handleRemoveUrl(idx)">删除</el-button>
            </div>
            <div v-if="editableUrls.length === 0" class="samples-empty">暂无样本，请在下行添加 URL。</div>
          </div>
          <div class="samples-add-row">
            <el-input
              v-model="newUrlInput"
              size="default"
              placeholder="输入样本 URL"
              class="add-input"
              @keyup.enter.prevent="handleAddUrl"
            />
            <el-button type="primary" size="default" @click="handleAddUrl">添加样本</el-button>
          </div>
          <div class="samples-save-row">
            <el-button type="primary" size="default" :loading="savingSamples" @click="handleSaveSamples">
              保存样本列表
            </el-button>
          </div>
        </div>

        <div class="section-divider">声纹状态</div>
        <div class="embedding-block">
          <div class="embedding-meta">
            <span class="meta-item">
              状态：
              <el-tag v-if="hasEmbedding" type="success" size="small" effect="light">已生成</el-tag>
              <el-tag v-else type="info" size="small" effect="light">未生成</el-tag>
            </span>
            <span class="meta-item">嵌入状态：{{ parseEmbeddingStatusLabel() }}</span>
            <span class="meta-item">创建：{{ formatDateTimeToCST(profile.created_at) }}</span>
            <span class="meta-item">最近更新：{{ parseEmbeddingUpdatedAt() }}</span>
            <span v-if="parseGeneratedAt()" class="meta-item">最近生成：{{ parseGeneratedAt() }}</span>
          </div>
          <el-button type="primary" size="default" :loading="generating" @click="handleGenerateEmbedding">
            {{ hasEmbedding ? '重新生成声纹' : '生成声纹' }}
          </el-button>
        </div>

        <el-collapse v-if="profile.voice_embedding" class="embedding-collapse">
          <el-collapse-item name="meta">
            <template #title>
              <span class="collapse-title">声纹元数据（占位）</span>
            </template>
            <pre class="embedding-json">{{ JSON.stringify(profile.voice_embedding, null, 2) }}</pre>
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

.record-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 16px;
}

.recording-indicator {
  font-size: 13px;
  color: #dc2626;
}

.recording-hint {
  font-size: 12px;
  color: #9ca3af;
}

.record-preview {
  margin-top: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 16px;
}

.preview-title {
  margin: 0;
  font-size: 12px;
  color: #6b7280;
}

.preview-audio {
  flex-shrink: 0;
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

.samples-count-tip {
  margin: 0 0 2px;
  font-size: 12px;
  color: #6b7280;
}

.sample-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.sample-index {
  flex-shrink: 0;
  width: 52px;
  font-size: 12px;
  color: #6b7280;
}

.sample-input {
  flex: 1;
  min-width: 0;
}

.sample-audio {
  flex-shrink: 0;
  max-width: 100%;
  width: 100%;
}

.samples-empty {
  font-size: 12px;
  color: #9ca3af;
  padding: 8px 0;
}

.samples-add-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 4px;
}

.samples-save-row {
  margin-top: 16px;
}

.add-input {
  width: 100%;
  min-width: 200px;
}

.embedding-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 20px;
  padding: 16px 0;
}

.embedding-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px 24px;
  font-size: 13px;
  color: #4b5563;
}

.meta-item {
  white-space: nowrap;
}

.embedding-collapse {
  margin-top: 8px;
}

.embedding-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: #6b7280;
}

.collapse-title {
  font-weight: 500;
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
