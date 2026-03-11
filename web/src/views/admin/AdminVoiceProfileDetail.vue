<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getAdminVoiceProfileDetail,
  updateAdminVoiceProfileSamples,
  generateAdminVoiceProfileEmbedding,
} from '../../api/admin/voice-profiles'
import type { AdminVoiceProfileDetail } from '../../types/admin'
import { formatDateTimeToCST } from '../../utils/datetime'

const route = useRoute()
const router = useRouter()
const profileId = route.params.id as string

function goBackToList() {
  router.push({ name: 'AdminVoiceProfiles', query: route.query })
}

const loading = ref(false)
const savingSamples = ref(false)
const generating = ref(false)

const detail = ref<AdminVoiceProfileDetail | null>(null)
const editableUrls = ref<string[]>([])

const newUrlInput = ref('')

const hasEmbedding = computed(() => !!detail.value?.profile.voice_embedding)

function parseGeneratedAt(): string | null {
  const emb = detail.value?.profile.voice_embedding
  if (!emb) return null
  const raw = (emb as any).generated_at
  if (typeof raw !== 'string') return null
  return formatDateTimeToCST(raw)
}

async function fetchDetail() {
  loading.value = true
  try {
    const data = await getAdminVoiceProfileDetail(profileId)
    detail.value = data
    editableUrls.value = [...(data.profile.sample_audio_urls || [])]
  } catch (err: any) {
    console.error(err)
    ElMessage.error(err?.message || '加载声纹配置详情失败')
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
  if (!detail.value) return
  savingSamples.value = true
  try {
    const updated = await updateAdminVoiceProfileSamples(detail.value.profile.id, editableUrls.value)
    detail.value = { ...detail.value, profile: updated }
    editableUrls.value = [...(updated.sample_audio_urls || [])]
    ElMessage.success('样本列表已保存')
  } catch (err: any) {
    console.error(err)
    ElMessage.error(err?.message || '保存样本列表失败')
  } finally {
    savingSamples.value = false
  }
}

async function handleGenerateEmbedding() {
  if (!detail.value) return
  if (!editableUrls.value.length) {
    ElMessage.warning('当前没有任何样本，请先添加样本 URL 后再生成声纹')
    return
  }

  try {
    await ElMessageBox.confirm(
      '将根据当前样本列表重新生成声纹，可能会覆盖之前的结果，确定继续吗？',
      '重新生成声纹',
      { type: 'warning', confirmButtonText: '生成', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  generating.value = true
  try {
    const updated = await generateAdminVoiceProfileEmbedding(detail.value.profile.id)
    detail.value = { ...detail.value, profile: updated }
    ElMessage.success('声纹已生成')
  } catch (err: any) {
    console.error(err)
    ElMessage.error(err?.message || '生成声纹失败')
  } finally {
    generating.value = false
  }
}

onMounted(() => {
  void fetchDetail()
})
</script>

<template>
  <div class="admin-voice-profile-detail">
    <el-card v-loading="loading" shadow="never" class="detail-card">
        <template #header>
        <div class="card-header">
          <span class="card-title">声纹配置详情</span>
          <el-button type="primary" plain size="default" @click="goBackToList">返回列表</el-button>
        </div>
      </template>

      <div v-if="detail" class="detail-body">
        <el-descriptions :column="1" border size="small" class="user-info">
          <el-descriptions-item label="用户">
            <span class="user-value">
              <span v-if="detail.user_name">
                {{ detail.user_name }}
                <span v-if="detail.user_email" class="text-muted">（{{ detail.user_email }}）</span>
              </span>
              <span v-else>{{ detail.user_email || detail.profile.user_id }}</span>
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="用户 ID">
            <span class="mono">{{ detail.profile.user_id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="当前小组">
            <span v-if="detail.primary_group_id">
              {{ detail.primary_group_id }} / {{ detail.primary_group_name || '未命名小组' }}
            </span>
            <span v-else class="text-muted">-</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">样本列表</el-divider>
        <p class="hint">增删样本 URL 后保存，再可点击「重新生成声纹」。</p>
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

        <el-divider content-position="left">声纹状态</el-divider>
        <div class="embedding-block">
          <div class="embedding-meta">
            <span class="meta-item">
              状态：
              <el-tag v-if="hasEmbedding" type="success" size="small" effect="light">已生成</el-tag>
              <el-tag v-else type="info" size="small" effect="light">未生成</el-tag>
            </span>
            <span class="meta-item">创建：{{ formatDateTimeToCST(detail.profile.created_at) }}</span>
            <span v-if="parseGeneratedAt()" class="meta-item">最近生成：{{ parseGeneratedAt() }}</span>
          </div>
          <el-button type="primary" size="default" :loading="generating" @click="handleGenerateEmbedding">
            重新生成声纹
          </el-button>
        </div>

        <el-collapse v-if="detail.profile.voice_embedding" class="embedding-collapse">
          <el-collapse-item name="meta">
            <template #title>
              <span class="collapse-title">声纹元数据（占位）</span>
            </template>
            <pre class="embedding-json">{{ JSON.stringify(detail.profile.voice_embedding, null, 2) }}</pre>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.admin-voice-profile-detail {
  max-width: 900px;
}

.detail-card :deep(.el-card__header) {
  padding: 14px 20px;
  background: #fafafa;
  border-bottom: 1px solid #eee;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.detail-body {
  padding: 8px 4px 20px;
}

.user-info {
  margin-bottom: 8px;
}

.user-info :deep(.el-descriptions__label) {
  width: 88px;
  color: #6b7280;
  font-size: 13px;
}

.user-value {
  word-break: break-all;
  max-width: 100%;
}

.text-muted {
  color: #9ca3af;
  font-size: 12px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 13px;
}

.el-divider {
  margin: 24px 0 16px;
}

.el-divider__text {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #6b7280;
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

