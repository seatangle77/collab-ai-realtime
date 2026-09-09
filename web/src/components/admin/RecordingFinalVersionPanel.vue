<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getRecordingVersion, previewRecordingVersion, saveRecordingVersion,
  type RecordingVersion, type RecordingDocument } from '../../api/admin/recording-final-versions'

const props = defineProps<{ sessionId: string; alignmentRunId?: string; suggestedStartId?: string; alignmentStatus?: string; alignmentOffsetSeconds?: number }>()
const emit = defineEmits<{ saved: [] }>()
const saved = ref<RecordingVersion | null>(null)
const preview = ref<RecordingDocument | null>(null)
const confirmed = ref(false)
const loading = ref(false)
const previewing = ref(false)
const saving = ref(false)
const ready = ref(false)
const storageReady = ref(false)
const error = ref('')
let generation = 0
let previewRequest = 0
const document = computed(() => saved.value?.document)
const canConfirm = computed(() => Boolean(props.alignmentRunId) && ['completed', 'completed_with_errors', 'failed'].includes(props.alignmentStatus ?? ''))
const segments = computed(() => document.value?.segments ?? [])
function time(value: number | null) {
  if (value == null) return '时间未标注'
  return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}`
}
function message(e: unknown) {
  const raw = e instanceof Error ? e.message : '操作失败，请重试'
  try { return JSON.parse(raw).detail || raw } catch { return raw }
}
async function load() {
  const token = ++generation
  ++previewRequest
  saved.value = null; preview.value = null
  confirmed.value = false; ready.value = false; storageReady.value = false; error.value = ''
  previewing.value = false; saving.value = false
  if (!props.sessionId) { loading.value = false; return }
  loading.value = true
  try {
    const version = await getRecordingVersion(props.sessionId)
    if (token !== generation) return
    storageReady.value = true
    saved.value = version
    ready.value = true
  } catch (e) { if (token === generation) error.value = message(e) }
  finally { if (token === generation) loading.value = false }
}
function invalidate() { ++previewRequest; preview.value = null; confirmed.value = false; previewing.value = false }
async function buildPreview() {
  if (!ready.value) return
  const token = generation, request = ++previewRequest
  preview.value = null; previewing.value = true; error.value = ''; confirmed.value = false
  try {
    const result = await previewRecordingVersion(props.sessionId, { alignment_run_id: props.alignmentRunId, alignment_offset_seconds: props.alignmentOffsetSeconds })
    if (token === generation && request === previewRequest) preview.value = result
  } catch (e) { if (token === generation && request === previewRequest) error.value = message(e) }
  finally { if (token === generation && request === previewRequest) previewing.value = false }
}
async function save() {
  const doc = preview.value
  if (!doc || !confirmed.value || saving.value || !storageReady.value) return
  const token = generation
  saving.value = true; error.value = ''
  try {
    const result = await saveRecordingVersion(props.sessionId, {
      alignment_offset_seconds: props.alignmentOffsetSeconds,
      alignment_run_id: props.alignmentRunId, source_hash: doc.source_hash, preview_hash: doc.preview_hash,
      boundary_confirmed: true, base_version_id: saved.value?.id ?? null,
    })
    if (token !== generation) return
    saved.value = result; preview.value = null; confirmed.value = false
    ElMessage.success('最终版本已保存，全部录音正文已保留')
    emit('saved')
  } catch (e) { if (token === generation) error.value = message(e) }
  finally { if (token === generation) saving.value = false }
}
async function confirmAndSave() {
  await buildPreview()
  if (!preview.value) return
  confirmed.value = true
  await save()
}
watch(() => props.sessionId, load, { immediate: true })
watch(() => [props.alignmentRunId, props.alignmentOffsetSeconds], invalidate)
defineExpose({ buildPreview })
</script>

<template>
  <div class="recording-final-panel" v-loading="loading">
    <div class="final-panel-heading">
      <strong>最终修订版本</strong>
      <el-tag v-if="saved" type="success" size="small">已保存</el-tag>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-button v-if="error" size="small" @click="load">重新加载</el-button>
    <Teleport v-if="ready && canConfirm" to="#recording-save-controls">
      <div v-if="ready && canConfirm" class="final-range">
        <el-button type="primary" :disabled="!ready || !storageReady" :loading="saving || previewing" @click="confirmAndSave">确认并保存整理结果</el-button>
      </div>
    </Teleport>
    <div v-if="document" class="final-document-summary" role="status">
      <span>录音 {{ document.recording_count }} 段 · 已全部归入正文</span>
      <span>替换 {{ document.replaced_count }} 条实时转写 · 前后保留 {{ document.before_count + document.after_count }} 条</span>
    </div>

    <div v-if="document" class="recording-document-list">
      <article v-for="segment in segments" :key="`${segment.kind}-${segment.id}`" :class="`segment--${segment.kind}`">
        <div class="segment-meta">
          <strong>{{ segment.kind === 'recording' ? `录音 #${segment.recording_order}` : segment.kind === 'before' ? '范围前原文' : '范围后原文' }}</strong>
          <span>{{ time(segment.time) }}</span>
          <span>{{ segment.speaker_name || '说话人未确定' }}</span>

        </div>
        <p>{{ segment.text || '（空白原文）' }}</p>
      </article>
    </div>
    <slot v-if="!document && !loading" name="empty">
      <el-empty description="AI整理完成并确认保存后，显示最终修订结果" :image-size="60" />
    </slot>
  </div>
</template>

<style scoped>
.recording-final-panel { display: flex; flex-direction: column; min-height: 0; height: 100%; color: #334155; }
.final-panel-heading { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 16px; border-bottom: 1px solid #e5eaf0; }
.final-intro { font-size: 13px; line-height: 1.7; margin: 12px 16px; color: #64748b; }
.final-range { display: grid; gap: 8px; padding: 0 16px 12px; }
.final-range label { font-size: 13px; font-weight: 600; }
.final-range small { font-size: 12px; line-height: 1.6; color: #64748b; }
.final-range .el-select { min-width: 0; width: 100%; }
.final-document-summary { display: grid; gap: 4px; padding: 10px 16px; background: #f0fdf4; font-size: 12px; }
.recording-document-list { flex: 1; min-height: 200px; overflow-y: auto; padding: 12px; }
.recording-document-list article { padding: 12px; border: 1px solid #d9e6df; border-radius: 8px; margin-bottom: 10px; background: #fbfefc; }
.recording-document-list .segment--before, .recording-document-list .segment--after { background: #f8fafc; border-color: #e2e8f0; }
.segment-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; font-size: 12px; color: #64748b; }
.recording-document-list p { margin: 8px 0 0; font-size: 15px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.final-save-bar { display: grid; gap: 8px; padding: 12px 16px; border-top: 1px solid #e5eaf0; }
.final-save-bar :deep(.el-checkbox) { white-space: normal; height: auto; }
.final-save-bar :deep(.el-checkbox__label) { white-space: normal; line-height: 1.6; }
</style>
