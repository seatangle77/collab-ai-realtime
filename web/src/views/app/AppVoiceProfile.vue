<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Microphone } from '@element-plus/icons-vue'
import AppEmptyState from '../../components/AppEmptyState.vue'
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
const activeRecordTab = ref<'record' | 'url' | 'file'>('record')

const profile = ref<VoiceProfileOut | null>(null)
const editableUrls = ref<string[]>([])
const newUrlInput = ref('')
const recordedChunks = ref<BlobPart[]>([])
const recordingDuration = ref(0)
const previewUrl = ref<string | null>(null)
const selectedFile = ref<File | null>(null)
const selectedFilePreviewUrl = ref<string | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const mediaRecorder = ref<MediaRecorder | null>(null)
let recordingTimer: number | undefined
const MAX_UPLOAD_FILE_SIZE = 50 * 1024 * 1024

const hasEmbedding = computed(() => !!profile.value?.voice_embedding)
const currentStep = computed(() => (hasEmbedding.value ? 2 : 1))

function parseEmbeddingStatusLabel(): string {
  const status = profile.value?.embedding_status
  if (status === 'not_generated') return '未生成'
  if (status === 'ready') return '已就绪'
  return status || '-'
}

function parseGeneratedAt(): string | null {
  // voice_embedding 是 number[]，没有 generated_at 字段；
  // 改用 embedding_updated_at 作为"生成时间"展示
  const raw = profile.value?.embedding_updated_at
  if (!raw) return null
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

function resetSelectedFile() {
  selectedFile.value = null
  if (selectedFilePreviewUrl.value) {
    URL.revokeObjectURL(selectedFilePreviewUrl.value)
    selectedFilePreviewUrl.value = null
  }
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
  }
}

function handleTabChange(tab: 'record' | 'url' | 'file') {
  if (tab !== activeRecordTab.value) {
    if (activeRecordTab.value === 'record') {
      resetRecording()
    }
    if (activeRecordTab.value === 'file') {
      resetSelectedFile()
    }
    activeRecordTab.value = tab
  }
}

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function handleOpenFilePicker() {
  fileInputRef.value?.click()
}

function setSelectedFile(file: File | null) {
  resetSelectedFile()
  if (!file) return
  selectedFile.value = file
  selectedFilePreviewUrl.value = URL.createObjectURL(file)
}

function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement | null
  const file = input?.files?.[0] || null
  setSelectedFile(file)
}

function handleFileDrop(event: DragEvent) {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0] || null
  setSelectedFile(file)
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

async function handleUploadFileSample() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择一个音频文件')
    return
  }
  if (editableUrls.value.length >= 5) {
    ElMessage.warning('已达到最多 5 条样本')
    return
  }
  if (selectedFile.value.size > MAX_UPLOAD_FILE_SIZE) {
    ElMessage.warning('文件不能超过 50MB')
    return
  }

  isUploading.value = true
  try {
    const { url } = await uploadMyVoiceSample(selectedFile.value)
    editableUrls.value = [...editableUrls.value, url]
    await handleSaveSamples()
    ElMessage.success('文件已上传并添加到样本列表')
    resetSelectedFile()
  } catch (err: unknown) {
    console.error(err)
    ElMessage.error((err as Error)?.message || '上传文件失败')
  } finally {
    isUploading.value = false
  }
}

async function handleGenerateEmbedding() {
  if (!profile.value) return
  const hadEmbedding = hasEmbedding.value
  if (!editableUrls.value.length) {
    ElMessage.warning('请先添加样本 URL 后再生成声纹')
    return
  }
  if (hadEmbedding) {
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
    ElMessage.success(hadEmbedding ? '声纹已重新生成' : '声纹已生成')
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

onBeforeUnmount(() => {
  resetRecording()
  resetSelectedFile()
})
</script>

<template>
  <div class="app-voice-profile">
    <div class="app-voice-profile-card" v-loading="loading">
      <h2 class="app-voice-profile-title">我的声纹</h2>
      <p class="app-voice-profile-desc">录制或上传音频样本，生成专属声纹用于说话人识别。</p>

      <template v-if="profile">
        <div class="voice-stepbar" aria-label="声纹设置步骤">
          <div class="voice-stepbar-item" :data-active="currentStep >= 1">
            <span class="voice-stepbar-dot">1</span>
            <span class="voice-stepbar-text">添加音频样本</span>
          </div>
          <div class="voice-stepbar-line" aria-hidden="true"></div>
          <div class="voice-stepbar-item" :data-active="currentStep >= 2">
            <span class="voice-stepbar-dot">2</span>
            <span class="voice-stepbar-text">生成声纹</span>
          </div>
        </div>
        <h3 class="voice-step-heading">第一步：添加音频样本</h3>
        <div class="record-card">
          <div class="record-tabs">
            <button
              type="button"
              class="record-tab"
              :class="{ active: activeRecordTab === 'record' }"
              @click="handleTabChange('record')"
            >
              现场录音
            </button>
            <button
              type="button"
              class="record-tab"
              :class="{ active: activeRecordTab === 'url' }"
              @click="handleTabChange('url')"
            >
              粘贴 URL
            </button>
            <button
              type="button"
              class="record-tab"
              :class="{ active: activeRecordTab === 'file' }"
              @click="handleTabChange('file')"
            >
              上传文件
            </button>
          </div>

          <!-- Tab: 现场录音 -->
          <div v-if="activeRecordTab === 'record'" class="tab-panel">
            <!-- 未录音 -->
            <template v-if="!isRecording && !previewUrl">
              <el-button
                type="primary"
                size="default"
                :icon="Microphone"
                class="record-action-btn"
                :disabled="editableUrls.length >= 5"
                @click="startRecording"
              >
                <span class="record-action-btn__pulse" aria-hidden="true"></span>
                开始录音
              </el-button>
              <span class="recording-hint">每段建议 10–15 秒</span>
            </template>

            <!-- 录音中 -->
            <template v-else-if="isRecording">
              <el-button
                type="danger"
                size="default"
                class="record-action-btn record-action-btn--recording"
                @click="stopRecording"
              >
                <span class="record-action-btn__pulse" aria-hidden="true"></span>
                停止录音
              </el-button>
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
                >
                  添加此段
                </el-button>
              </div>
            </template>
          </div>

          <!-- Tab: 粘贴 URL -->
          <div v-if="activeRecordTab === 'url'" class="tab-panel">
            <div class="url-add-row">
              <el-input
                v-model="newUrlInput"
                size="default"
                placeholder="请输入音频 URL"
                class="url-input"
                @keyup.enter.prevent="handleAddUrl"
              />
              <el-button type="primary" size="default" @click="handleAddUrl">添加</el-button>
            </div>
          </div>

          <!-- Tab: 上传文件 -->
          <div v-if="activeRecordTab === 'file'" class="tab-panel tab-panel--file">
            <input
              ref="fileInputRef"
              type="file"
              accept="audio/*"
              class="file-input"
              @change="handleFileSelected"
            />
            <button
              type="button"
              class="file-drop-area"
              :disabled="editableUrls.length >= 5"
              @click="handleOpenFilePicker"
              @dragover.prevent
              @drop="handleFileDrop"
            >
              <span class="file-drop-area__title">点击选择音频文件</span>
              <span class="file-drop-area__hint">支持拖拽上传，建议单个文件不超过 50MB</span>
            </button>

            <div v-if="selectedFile" class="file-info">
              <span class="file-info__name">{{ selectedFile.name }}</span>
              <span class="file-info__meta">{{ formatFileSize(selectedFile.size) }}</span>
            </div>

            <audio
              v-if="selectedFilePreviewUrl"
              :src="selectedFilePreviewUrl"
              controls
              class="preview-audio"
            />

            <div v-if="selectedFile" class="preview-actions">
              <el-button size="default" @click="resetSelectedFile">重新选择</el-button>
              <el-button
                type="primary"
                size="default"
                :loading="isUploading"
                :disabled="editableUrls.length >= 5"
                @click="handleUploadFileSample"
              >
                上传此文件
              </el-button>
            </div>
          </div>
        </div>

        <p class="voice-samples-count">已添加 {{ editableUrls.length }} / 5 条样本</p>
        <div class="samples-editor">
          <div class="samples-list">
            <AppEmptyState
              v-if="editableUrls.length === 0"
              icon="🎙️"
              title="暂无样本"
              description="请先通过录音或粘贴 URL 添加样本。"
              compact
            />
            <div
              v-for="(url, idx) in editableUrls"
              :key="idx"
              class="sample-row"
            >
              <span class="sample-index">{{ idx + 1 }}</span>
              <div class="sample-row-main">
                <audio :src="url" controls class="sample-audio" />
                <div class="sample-progress-track" aria-hidden="true">
                  <div class="sample-progress-fill" />
                </div>
              </div>
              <el-button
                type="danger"
                plain
                size="small"
                :icon="Delete"
                circle
                :aria-label="`删除第 ${idx + 1} 条样本`"
                @click="handleRemoveUrl(idx)"
              />
            </div>
          </div>
        </div>

        <div class="voice-step-separator" role="presentation" />

        <h3 class="voice-step-heading">第二步：生成声纹</h3>

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
  max-width: var(--app-content-width-narrow);
  padding: 18px 20px;
  border-radius: var(--app-radius-card);
  background: var(--app-bg-elevated);
  box-shadow: var(--app-shadow-soft);
  border: 1px solid var(--app-border);
}

.app-voice-profile-title {
  margin: 0 0 8px;
  font-size: var(--app-font-size-title);
  font-weight: 700;
  color: var(--app-text-primary);
  letter-spacing: -0.02em;
}

.app-voice-profile-desc {
  margin: 0 0 24px;
  font-size: 14px;
  line-height: 1.65;
  color: var(--app-text-secondary);
}

.voice-stepbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.voice-stepbar-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--app-text-muted);
}

.voice-stepbar-item[data-active='true'] {
  color: var(--app-text-primary);
}

.voice-stepbar-dot {
  width: 24px;
  height: 24px;
  border-radius: var(--app-radius-pill);
  border: 1px solid var(--app-border-strong);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--app-font-size-caption);
  font-weight: 700;
  background: var(--app-bg-elevated);
}

.voice-stepbar-item[data-active='true'] .voice-stepbar-dot {
  border-color: var(--app-primary);
  background: var(--app-primary);
  color: var(--app-bg-elevated);
}

.voice-stepbar-text {
  font-size: var(--app-font-size-body);
  font-weight: 500;
}

.voice-stepbar-line {
  flex: 1;
  min-width: 24px;
  height: 1px;
  background: var(--app-border);
}

.voice-step-heading {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.voice-samples-count {
  margin: 16px 0 10px;
  font-size: 14px;
  font-weight: 500;
  color: var(--app-text-secondary);
}

.voice-step-separator {
  height: 1px;
  margin: 24px 0 20px;
  background: var(--app-border);
  border: none;
}

/* 录音 / URL 区（卡片，对齐 demo） */
.record-card {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-card);
  background: var(--app-bg-elevated);
  box-shadow: var(--app-shadow-card);
  padding: 18px 20px;
}

.recording-indicator {
  font-size: 14px;
  font-weight: 500;
  color: var(--app-danger);
}

.record-action-btn {
  width: 100%;
  min-height: 48px;
}

.record-action-btn--recording {
  width: auto;
  min-width: 140px;
}

.record-action-btn__pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 2px;
  border-radius: var(--app-radius-pill);
  background: currentColor;
  animation: voice-record-pulse 1.2s ease-in-out infinite;
}

.recording-hint {
  font-size: 13px;
  color: var(--app-text-muted);
}

.preview-audio {
  width: 100%;
  max-width: 100%;
}

.preview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.samples-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.samples-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sample-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--app-radius-md);
  background: var(--app-bg-page);
}

.sample-index {
  flex-shrink: 0;
  width: 22px;
  font-size: 13px;
  font-weight: 500;
  color: var(--app-text-muted);
  text-align: right;
}

.sample-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sample-audio {
  width: 100%;
  max-width: 100%;
}

/* 占位进度条（后续可接真实播放进度） */
.sample-progress-track {
  height: 4px;
  border-radius: 999px;
  background: #e2e8f0;
  overflow: hidden;
}

.sample-progress-fill {
  height: 100%;
  width: 0;
  border-radius: 999px;
  background: var(--app-primary);
}

.samples-empty {
  font-size: 14px;
  color: var(--app-text-muted);
  padding: 8px 0;
}

.embedding-block {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 4px 0 8px;
}

/* Tab：下划线激活（对齐 demo） */
.record-tabs {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--app-border);
}

.record-tab {
  padding: 0 0 10px;
  margin-bottom: -1px;
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  color: var(--app-text-secondary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition:
    color 0.18s ease,
    border-color 0.18s ease;
}

.record-tab:hover {
  color: var(--app-text-primary);
}

.record-tab.active {
  color: var(--app-primary);
  border-bottom-color: var(--app-primary);
}

.tab-panel {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  min-height: 44px;
  width: 100%;
}

.tab-panel--file {
  align-items: stretch;
  flex-direction: column;
}

.file-input {
  display: none;
}

.file-drop-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  min-height: 132px;
  padding: 20px;
  border: 1px dashed var(--app-border-strong);
  border-radius: var(--app-radius-md);
  background: var(--app-bg-page);
  color: var(--app-text-secondary);
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease;
}

.file-drop-area:hover:not(:disabled) {
  border-color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 6%, var(--app-bg-page));
  color: var(--app-text-primary);
}

.file-drop-area:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.file-drop-area__title {
  font-size: 14px;
  font-weight: 600;
}

.file-drop-area__hint {
  font-size: 13px;
}

.file-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 10px 12px;
  border-radius: var(--app-radius-md);
  background: var(--app-bg-page);
  color: var(--app-text-secondary);
}

.file-info__name {
  min-width: 0;
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: var(--app-text-primary);
  word-break: break-all;
}

.file-info__meta {
  flex-shrink: 0;
  font-size: 13px;
}

.url-add-row {
  display: flex;
  align-items: stretch;
  gap: 12px;
  width: 100%;
}

.url-input {
  flex: 1;
}

.generate-hint {
  font-size: 13px;
  color: var(--app-text-muted);
}

.embedding-done {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 4px 0 12px;
}

.embedding-done-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.embedding-done-time {
  font-size: 13px;
  color: var(--app-text-secondary);
}

.detail-collapse {
  margin-top: 8px;
}

.detail-collapse :deep(.el-collapse-item__header) {
  font-size: 14px;
  font-weight: 500;
  color: var(--app-text-secondary);
}

.detail-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.collapse-title {
  color: var(--app-text-primary);
}

.detail-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--app-text-secondary);
}

.detail-item {
  white-space: nowrap;
}

.embedding-json {
  margin: 0;
  padding: 12px 14px;
  border-radius: var(--app-radius-sm);
  background: var(--app-bg-page);
  border: 1px solid var(--app-border);
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 200px;
  overflow-y: auto;
}

@keyframes voice-record-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.45;
    transform: scale(1.35);
  }
}
</style>
