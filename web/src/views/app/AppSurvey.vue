<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElTabs, ElTabPane } from 'element-plus'
import {
  fetchScaleMeta,
  fetchMyEntry,
  submitSrcc,
  submitPcs,
  type ScaleMeta,
  type QuestionnaireEntry,
} from '../../api/appQuestionnaire'

const loading = ref(false)
const submittingSrcc = ref(false)
const submittingPcs = ref(false)
const activeTab = ref<'srcc' | 'pcs'>('srcc')

const meta = ref<ScaleMeta | null>(null)
const entry = ref<QuestionnaireEntry | null>(null)

const srccAnswers = ref<Record<string, number | null>>({})
const pcsAnswers = ref<Record<string, number | null>>({})

const srccComplete = computed(() => {
  if (!meta.value) return false
  return meta.value.srcc_items.every((item) => {
    const v = srccAnswers.value[item.id]
    return v !== null && v !== undefined
  })
})

const pcsComplete = computed(() => {
  if (!meta.value) return false
  return meta.value.pcs_items.every((item) => {
    const v = pcsAnswers.value[item.id]
    return v !== null && v !== undefined
  })
})

const srccSubmitted = computed(() => !!entry.value?.srcc_responses)
const pcsSubmitted = computed(() => !!entry.value?.pcs_responses)

function initAnswers(e: QuestionnaireEntry | null) {
  if (!meta.value) return
  const srccDefaults: Record<string, number | null> = {}
  meta.value.srcc_items.forEach((item) => {
    srccDefaults[item.id] = e?.srcc_responses?.[item.id] ?? null
  })
  srccAnswers.value = srccDefaults

  const pcsDefaults: Record<string, number | null> = {}
  meta.value.pcs_items.forEach((item) => {
    pcsDefaults[item.id] = e?.pcs_responses?.[item.id] ?? null
  })
  pcsAnswers.value = pcsDefaults
}

async function load() {
  loading.value = true
  try {
    const [m, e] = await Promise.all([fetchScaleMeta(), fetchMyEntry()])
    meta.value = m
    entry.value = e
    initAnswers(e)
  } catch (err: unknown) {
    ElMessage.error((err as Error)?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function handleSubmitSrcc() {
  submittingSrcc.value = true
  try {
    const updated = await submitSrcc(srccAnswers.value)
    entry.value = updated
    ElMessage({
      type: 'success',
      message: '已保存 SRCC 量表',
      duration: 2000,
    })
    if (!pcsSubmitted.value) {
      setTimeout(() => {
        ElMessage({ type: 'info', message: '请继续填写 PCS 量表', duration: 3000 })
        activeTab.value = 'pcs'
      }, 800)
    }
  } catch (err: unknown) {
    ElMessage.error((err as Error)?.message || '提交失败')
  } finally {
    submittingSrcc.value = false
  }
}

async function handleSubmitPcs() {
  submittingPcs.value = true
  try {
    const updated = await submitPcs(pcsAnswers.value)
    entry.value = updated
    ElMessage({ type: 'success', message: '已保存 PCS 量表', duration: 2000 })
  } catch (err: unknown) {
    ElMessage.error((err as Error)?.message || '提交失败')
  } finally {
    submittingPcs.value = false
  }
}

function dimensionLabel(scale: 'srcc' | 'pcs', dim: string): string {
  if (!meta.value) return dim
  const map = scale === 'srcc' ? meta.value.srcc_dimensions : meta.value.pcs_dimensions
  return map[dim] ?? dim
}

function srccItemsByDimension() {
  if (!meta.value) return []
  const dims = Object.keys(meta.value.srcc_dimensions)
  return dims.map((dim) => ({
    dim,
    label: dimensionLabel('srcc', dim),
    items: meta.value!.srcc_items.filter((i) => i.dimension === dim),
  }))
}

onMounted(load)
</script>

<template>
  <div class="survey-page">
    <div class="survey-header">
      <h2 class="survey-title">量表填写</h2>
      <p class="survey-desc">请根据本次讨论的真实体验作答，每题 1–7 分（1 = 完全不同意，7 = 完全同意）。</p>
    </div>

    <div v-if="loading" class="survey-loading">加载中…</div>

    <template v-else-if="meta">
      <el-tabs v-model="activeTab" class="survey-tabs">
        <!-- ── SRCC Tab ── -->
        <el-tab-pane name="srcc">
          <template #label>
            <span class="tab-label">
              SRCC
              <span v-if="srccSubmitted" class="tab-badge tab-badge--done">✓</span>
            </span>
          </template>

          <div class="scale-intro">
            <p class="scale-name">Self-regulation in a Collaborative Context Scale</p>
            <p class="scale-sub">协作情境自我调节量表 · 共 15 题</p>
          </div>

          <div
            v-for="group in srccItemsByDimension()"
            :key="group.dim"
            class="dimension-block"
          >
            <div class="dimension-label">{{ group.label }}</div>
            <div
              v-for="item in group.items"
              :key="item.id"
              class="question-card"
            >
              <div class="question-text">
                <span class="question-zh">{{ item.zh }}</span>
                <span class="question-en">{{ item.en }}</span>
              </div>
              <div class="rating-row">
                <span class="rating-hint">完全不同意</span>
                <div class="rating-buttons">
                  <button
                    v-for="n in 7"
                    :key="n"
                    class="rating-btn"
                    :class="{ 'rating-btn--active': srccAnswers[item.id] === n }"
                    type="button"
                    @click="srccAnswers[item.id] = n"
                  >
                    {{ n }}
                  </button>
                </div>
                <span class="rating-hint">完全同意</span>
              </div>
            </div>
          </div>

          <div class="submit-row">
            <button
              class="submit-btn"
              :class="{ 'submit-btn--disabled': !srccComplete }"
              :disabled="submittingSrcc || !srccComplete"
              type="button"
              @click="handleSubmitSrcc"
            >
              {{ submittingSrcc ? '保存中…' : srccSubmitted ? '更新 SRCC' : '提交 SRCC' }}
            </button>
            <p v-if="!srccComplete" class="submit-hint">请完成所有 15 题后提交</p>
          </div>
        </el-tab-pane>

        <!-- ── PCS Tab ── -->
        <el-tab-pane name="pcs">
          <template #label>
            <span class="tab-label">
              PCS
              <span v-if="pcsSubmitted" class="tab-badge tab-badge--done">✓</span>
            </span>
          </template>

          <div class="scale-intro">
            <p class="scale-name">Perceived Cohesion Scale</p>
            <p class="scale-sub">感知凝聚力量表 · 共 6 题</p>
          </div>

          <div class="dimension-block">
            <div
              v-for="item in meta.pcs_items"
              :key="item.id"
              class="question-card"
            >
              <div class="question-text">
                <span class="question-zh">{{ item.zh }}</span>
                <span class="question-en">{{ item.en }}</span>
                <span class="question-dim-tag">{{ dimensionLabel('pcs', item.dimension) }}</span>
              </div>
              <div class="rating-row">
                <span class="rating-hint">完全不同意</span>
                <div class="rating-buttons">
                  <button
                    v-for="n in 7"
                    :key="n"
                    class="rating-btn"
                    :class="{ 'rating-btn--active': pcsAnswers[item.id] === n }"
                    type="button"
                    @click="pcsAnswers[item.id] = n"
                  >
                    {{ n }}
                  </button>
                </div>
                <span class="rating-hint">完全同意</span>
              </div>
            </div>
          </div>

          <div class="submit-row">
            <button
              class="submit-btn"
              :class="{ 'submit-btn--disabled': !pcsComplete }"
              :disabled="submittingPcs || !pcsComplete"
              type="button"
              @click="handleSubmitPcs"
            >
              {{ submittingPcs ? '保存中…' : pcsSubmitted ? '更新 PCS' : '提交 PCS' }}
            </button>
            <p v-if="!pcsComplete" class="submit-hint">请完成所有 6 题后提交</p>
          </div>
        </el-tab-pane>
      </el-tabs>

      <!-- 整体完成状态 -->
      <div v-if="srccSubmitted && pcsSubmitted" class="all-done-banner">
        两份量表均已完成，感谢你的作答！你可以随时回来修改。
      </div>
    </template>
  </div>
</template>

<style scoped>
.survey-page {
  max-width: 680px;
  margin: 0 auto;
}

.survey-header {
  margin-bottom: 20px;
}

.survey-title {
  font-size: var(--app-font-size-heading);
  font-weight: 700;
  color: var(--app-text-primary);
  margin: 0 0 6px;
}

.survey-desc {
  font-size: var(--app-font-size-caption);
  color: var(--app-text-secondary);
  margin: 0;
  line-height: 1.6;
}

.survey-loading {
  text-align: center;
  padding: 48px 0;
  color: var(--app-text-muted);
}

.survey-tabs {
  --el-tabs-header-height: 44px;
}

.tab-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
}

.tab-badge {
  font-size: 11px;
  border-radius: 999px;
  padding: 1px 6px;
}

.tab-badge--done {
  background: #d1fae5;
  color: #065f46;
}

.scale-intro {
  padding: 14px 0 8px;
  border-bottom: 1px solid var(--app-border);
  margin-bottom: 16px;
}

.scale-name {
  font-size: var(--app-font-size-body);
  font-weight: 600;
  color: var(--app-text-primary);
  margin: 0 0 2px;
}

.scale-sub {
  font-size: var(--app-font-size-caption);
  color: var(--app-text-muted);
  margin: 0;
}

.dimension-block {
  margin-bottom: 20px;
}

.dimension-label {
  font-size: var(--app-font-size-caption);
  font-weight: 700;
  color: var(--app-primary);
  padding: 6px 0 10px;
  letter-spacing: 0.02em;
}

.question-card {
  background: var(--app-bg-card, #fff);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 10px;
}

.question-text {
  margin-bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.question-zh {
  font-size: var(--app-font-size-body);
  font-weight: 500;
  color: var(--app-text-primary);
  line-height: 1.5;
}

.question-en {
  font-size: var(--app-font-size-caption);
  color: var(--app-text-muted);
  line-height: 1.4;
}

.question-dim-tag {
  font-size: 11px;
  color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 10%, transparent);
  border-radius: 999px;
  padding: 1px 8px;
  align-self: flex-start;
  margin-top: 2px;
}

.rating-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rating-hint {
  font-size: var(--app-font-size-caption);
  color: var(--app-text-secondary);
  white-space: nowrap;
  flex-shrink: 0;
  font-weight: 500;
}

.rating-buttons {
  display: flex;
  gap: 5px;
  flex: 1;
  justify-content: center;
}

.rating-btn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-bg-page, #f8fafc);
  color: var(--app-text-secondary);
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  flex-shrink: 0;
}

.rating-btn--active {
  background: var(--app-primary);
  border-color: var(--app-primary);
  color: #fff;
}

.rating-btn:hover:not(.rating-btn--active) {
  border-color: var(--app-primary);
  color: var(--app-primary);
}

.submit-row {
  padding: 16px 0 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.submit-btn {
  min-width: 140px;
  padding: 12px 28px;
  background: var(--app-primary);
  color: #fff;
  border: none;
  border-radius: 10px;
  font: inherit;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.submit-btn:hover:not(.submit-btn--disabled) {
  background: var(--app-primary-hover, #3b5bdb);
}

.submit-btn--disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.submit-hint {
  font-size: var(--app-font-size-caption);
  color: var(--app-text-muted);
  margin: 0;
}

.all-done-banner {
  margin-top: 16px;
  padding: 14px 16px;
  background: #d1fae5;
  color: #065f46;
  border-radius: 12px;
  font-size: var(--app-font-size-body);
  font-weight: 500;
  text-align: center;
}

@media (max-width: 480px) {
  .question-card {
    padding: 14px 12px;
  }

  .rating-row {
    flex-wrap: wrap;
    justify-content: space-between;
    row-gap: 6px;
  }

  .rating-buttons {
    order: 1;
    flex: 0 0 100%;
    justify-content: space-between;
    gap: 4px;
  }

  .rating-hint {
    order: 2;
    font-size: 11px;
  }

  .rating-btn {
    width: 30px;
    height: 30px;
    font-size: 13px;
    border-radius: 6px;
  }
}
</style>
