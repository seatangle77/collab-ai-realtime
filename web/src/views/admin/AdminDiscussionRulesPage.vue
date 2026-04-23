<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { AdminDiscussionRule, AdminDiscussionRuleUpdate } from '../../types/admin'
import { getDiscussionRules, updateDiscussionRules } from '../../api/admin/discussion-rules'

const loading = ref(false)
const saving = ref(false)

const form = reactive<AdminDiscussionRuleUpdate & { updated_at?: string }>({
  speaking_ratio_min: undefined,
  speaking_ratio_max: undefined,
  cosine_similarity_threshold: undefined,
  min_session_duration_minutes: undefined,
  push_interval_minutes: undefined,
  max_push_per_member: undefined,
  analysis_enabled: undefined,
  personal_stagnation_ratio: undefined,
  group_silence_threshold_s: undefined,
  srep_threshold: undefined,
  ttr_threshold: undefined,
  arg_density_threshold: undefined,
  info_gain_threshold: undefined,
  skw_threshold_low: undefined,
  skw_threshold_high: undefined,
  same_state_cooldown_s: undefined,
  cross_state_cooldown_s: undefined,
  updated_at: undefined,
})

function validateForm() {
  const ratioMin = form.speaking_ratio_min
  const ratioMax = form.speaking_ratio_max
  const skwLow = form.skw_threshold_low
  const skwHigh = form.skw_threshold_high

  if (ratioMin != null && (ratioMin < 0 || ratioMin > 1)) {
    ElMessage.warning('发言比例最小值必须在 0 到 1 之间')
    return false
  }
  if (ratioMax != null && (ratioMax < 0 || ratioMax > 1)) {
    ElMessage.warning('发言比例最大值必须在 0 到 1 之间')
    return false
  }
  if (ratioMin != null && ratioMax != null && ratioMin >= ratioMax) {
    ElMessage.warning('发言比例最小值必须小于最大值')
    return false
  }
  if (skwLow != null && skwHigh != null && skwLow >= skwHigh) {
    ElMessage.warning('SKW 低阈值必须小于高阈值')
    return false
  }

  const nonNegativeFields: Array<[string, number | undefined]> = [
    ['群体静默阈值（秒）', form.group_silence_threshold_s],
    ['个人停滞比例', form.personal_stagnation_ratio],
    ['最短会话时长（分钟）', form.min_session_duration_minutes],
    ['余弦相似度阈值', form.cosine_similarity_threshold],
    ['SREP 阈值', form.srep_threshold],
    ['TTR 阈值', form.ttr_threshold],
    ['论点密度阈值', form.arg_density_threshold],
    ['信息增益阈值', form.info_gain_threshold],
    ['SKW 低阈值', form.skw_threshold_low],
    ['SKW 高阈值', form.skw_threshold_high],
    ['推送间隔（分钟）', form.push_interval_minutes],
    ['每人最大推送次数', form.max_push_per_member],
    ['同状态冷却（秒）', form.same_state_cooldown_s],
    ['跨状态冷却（秒）', form.cross_state_cooldown_s],
  ]

  for (const [label, value] of nonNegativeFields) {
    if (value != null && value < 0) {
      ElMessage.warning(`${label}不能小于 0`)
      return false
    }
  }

  return true
}

async function fetchRules() {
  loading.value = true
  try {
    const data: AdminDiscussionRule = await getDiscussionRules()
    Object.assign(form, data)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载讨论规则失败')
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  if (!validateForm()) return
  saving.value = true
  try {
    const payload: AdminDiscussionRuleUpdate = {
      speaking_ratio_min: form.speaking_ratio_min,
      speaking_ratio_max: form.speaking_ratio_max,
      cosine_similarity_threshold: form.cosine_similarity_threshold,
      min_session_duration_minutes: form.min_session_duration_minutes,
      push_interval_minutes: form.push_interval_minutes,
      max_push_per_member: form.max_push_per_member,
      analysis_enabled: form.analysis_enabled,
      personal_stagnation_ratio: form.personal_stagnation_ratio,
      group_silence_threshold_s: form.group_silence_threshold_s,
      srep_threshold: form.srep_threshold,
      ttr_threshold: form.ttr_threshold,
      arg_density_threshold: form.arg_density_threshold,
      info_gain_threshold: form.info_gain_threshold,
      skw_threshold_low: form.skw_threshold_low,
      skw_threshold_high: form.skw_threshold_high,
      same_state_cooldown_s: form.same_state_cooldown_s,
      cross_state_cooldown_s: form.cross_state_cooldown_s,
    }
    const updated = await updateDiscussionRules(payload)
    Object.assign(form, updated)
    ElMessage.success('保存成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存讨论规则失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchRules()
})
</script>

<template>
  <div class="admin-discussion-rules-page">
    <div class="admin-discussion-rules-header">
      <div>
        <h2 class="admin-discussion-rules-title">讨论规则配置</h2>
        <div class="admin-discussion-rules-subtitle">配置 AI 分析触发、语义阈值与推送控制规则</div>
      </div>
      <div class="admin-discussion-rules-header-actions">
        <div class="analysis-switch-row">
          <span class="analysis-switch-label">AI 分析开关</span>
          <el-switch v-model="form.analysis_enabled" />
        </div>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </div>
    </div>

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="card-title">沉默 & 发言检测</div>
      </template>
      <el-form :model="form" label-width="200px">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="群体静默阈值（秒）">
              <el-input-number v-model="form.group_silence_threshold_s" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="发言比例最小值">
              <el-input-number v-model="form.speaking_ratio_min" :min="0" :max="1" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="发言比例最大值">
              <el-input-number v-model="form.speaking_ratio_max" :min="0" :max="1" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="个人停滞比例">
              <el-input-number v-model="form.personal_stagnation_ratio" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最短会话时长（分钟）">
              <el-input-number v-model="form.min_session_duration_minutes" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="card-title">语义 & 内容分析</div>
      </template>
      <el-form :model="form" label-width="200px">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="余弦相似度阈值">
              <el-input-number v-model="form.cosine_similarity_threshold" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="SREP 阈值">
              <el-input-number v-model="form.srep_threshold" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="TTR 阈值">
              <el-input-number v-model="form.ttr_threshold" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="论点密度阈值">
              <el-input-number v-model="form.arg_density_threshold" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="信息增益阈值">
              <el-input-number v-model="form.info_gain_threshold" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="SKW 低阈值">
              <el-input-number v-model="form.skw_threshold_low" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="SKW 高阈值">
              <el-input-number v-model="form.skw_threshold_high" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="card-title">推送控制</div>
      </template>
      <el-form :model="form" label-width="200px">
        <el-row :gutter="24">
          <el-col :span="12">
            <el-form-item label="推送间隔（分钟）">
              <el-input-number v-model="form.push_interval_minutes" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="每人最大推送次数">
              <el-input-number v-model="form.max_push_per_member" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="同状态冷却（秒）">
              <el-input-number v-model="form.same_state_cooldown_s" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="跨状态冷却（秒）">
              <el-input-number v-model="form.cross_state_cooldown_s" :min="0" :precision="2" :step="0.01" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <div class="footer-meta">
      <span class="updated-at-label">最后更新时间：</span>
      <span class="updated-at-text">{{ form.updated_at || '-' }}</span>
    </div>
  </div>
</template>

<style scoped>
.admin-discussion-rules-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-discussion-rules-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.admin-discussion-rules-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.admin-discussion-rules-subtitle {
  margin-top: 6px;
  color: #6b7280;
  font-size: 13px;
}

.admin-discussion-rules-header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.analysis-switch-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #ffffff;
}

.analysis-switch-label {
  color: #374151;
  font-size: 13px;
  font-weight: 500;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.footer-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  color: #6b7280;
  font-size: 13px;
}

.updated-at-label {
  color: #9ca3af;
}

.updated-at-text {
  color: #6b7280;
  font-size: 13px;
}
</style>
