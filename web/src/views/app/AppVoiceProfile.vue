<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getMyVoiceProfile,
  updateMySamples,
  generateMyEmbedding,
  type VoiceProfileOut,
} from '../../api/appVoiceProfile'
import { formatDateTimeToCST } from '../../utils/datetime'

const loading = ref(false)
const savingSamples = ref(false)
const generating = ref(false)

const profile = ref<VoiceProfileOut | null>(null)
const editableUrls = ref<string[]>([])
const newUrlInput = ref('')

const hasEmbedding = computed(() => !!profile.value?.voice_embedding)

function parseGeneratedAt(): string | null {
  const emb = profile.value?.voice_embedding
  if (!emb) return null
  const raw = (emb as Record<string, unknown>).generated_at
  if (typeof raw !== 'string') return null
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
        在此管理你的声纹样本并生成声纹。添加样本 URL 后保存，再点击「生成声纹」或「重新生成声纹」。
      </p>

      <template v-if="profile">
        <div class="section-divider">样本列表</div>
        <div class="samples-editor">
          <div class="samples-list">
            <div
              v-for="(url, idx) in editableUrls"
              :key="idx"
              class="sample-row"
            >
              <span class="sample-index">样本 {{ idx + 1 }}</span>
              <el-input v-model="editableUrls[idx]" size="default" class="sample-input" />
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
            <span class="meta-item">创建：{{ formatDateTimeToCST(profile.created_at) }}</span>
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
  gap: 16px;
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
  width: 360px;
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
