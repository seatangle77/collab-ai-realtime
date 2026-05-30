<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import './icebreaker/AppIcebreaker.css'
import {
  P1_QUESTIONS_PER_MEMBER,
  STORY_ROUNDS,
  buildP1MemberQuestions,
  createScoreDraft,
  pickStoryOpening,
} from './icebreaker/content'
import { pickIcebreakerMeme } from './icebreaker/memes'
import { FALLBACK_MEMBER, useIcebreakerMembers } from './icebreaker/useIcebreakerMembers'
import type { IcebreakerMember, ScoreMeme } from './icebreaker/types'
import { useAudioRecorder } from '../../composables/useAudioRecorder'
import {
  adminEvaluateIcebreakerStory,
  adminUploadIcebreakerVoiceSample,
} from '../../api/adminIcebreaker'
import type { IcebreakerStoryTurnPayload } from '../../api/appIcebreaker'
import { extractErrorMessage } from '../../utils/error'

const router = useRouter()
const route = useRoute()

const queryGroupId = typeof route.query.group_id === 'string' ? route.query.group_id : undefined
const uploadVoiceSample = adminUploadIcebreakerVoiceSample
const evaluateStory = adminEvaluateIcebreakerStory

const {
  pageLoading,
  pageError,
  currentGroup,
  currentGroupName,
  members,
  loadIcebreakerMembers,
} = useIcebreakerMembers(resetIcebreakerFlow, {
  groupId: queryGroupId,
  isAdmin: true,
})

const p1MemberQuestions = ref<string[][]>([])
const storyOpening = pickStoryOpening()

// ─────────────────────────────────────────────────────────────────
// Flow
// ─────────────────────────────────────────────────────────────────
type Screen = 'intro' | 'phase1' | 'phase2_intro' | 'phase2' | 'scoring' | 'done'
const screen = ref<Screen>('intro')
const exiting = ref(false)
const recorder = useAudioRecorder()
const activeRecordingPhase = ref<'phase1' | 'story' | null>(null)
const currentRecordingChunks = ref<Blob[]>([])
const currentRecordingMimeType = ref('audio/webm')

recorder.onChunk((blob, mimeType) => {
  if (!activeRecordingPhase.value) return
  currentRecordingChunks.value.push(blob)
  currentRecordingMimeType.value = mimeType || blob.type || currentRecordingMimeType.value
})

function currentGroupId(): string {
  return currentGroup.value?.id ?? ''
}

async function beginAudioCapture(phase: 'phase1' | 'story') {
  currentRecordingChunks.value = []
  currentRecordingMimeType.value = 'audio/webm'
  activeRecordingPhase.value = phase
  try {
    await recorder.startRecording()
  } catch (e) {
    activeRecordingPhase.value = null
    ElMessage.error(extractErrorMessage(e) || '录音启动失败')
    throw e
  }
}

async function endAudioCapture(): Promise<Blob | null> {
  try {
    await recorder.stopRecording()
  } catch (e) {
    ElMessage.error(extractErrorMessage(e) || '录音停止失败')
  }
  activeRecordingPhase.value = null
  if (!currentRecordingChunks.value.length) return null
  return new Blob(currentRecordingChunks.value, { type: currentRecordingMimeType.value })
}

// ─────────────────────────────────────────────────────────────────
// Phase 1 状态
// ─────────────────────────────────────────────────────────────────
type RecordState = 'ready' | 'recording' | 'saved'

const p1MemberIdx = ref(0)
const p1QuestionIdx = ref(0)
const p1RecordState = ref<RecordState>('ready')
const p1Saving = ref(false)
const p1Countdown = ref(20)
const p1SampleAdded = ref(false)
const p1SampleWarnings = ref<string[]>([])
let p1Interval: ReturnType<typeof setInterval> | null = null

const p1Member = computed(() => members.value[p1MemberIdx.value] ?? FALLBACK_MEMBER)
const p1Question = computed(() => p1MemberQuestions.value[p1MemberIdx.value]?.[p1QuestionIdx.value] ?? '')
const p1CurrentStep = computed(() => p1MemberIdx.value * P1_QUESTIONS_PER_MEMBER + p1QuestionIdx.value + 1)
const p1Total = computed(() => members.value.length * P1_QUESTIONS_PER_MEMBER)
const p1ProgressPercent = computed(() => p1Total.value > 0 ? ((p1CurrentStep.value - 1) / p1Total.value) * 100 : 0)

const RING_C = 2 * Math.PI * 44
const p1RingOffset = computed(() => RING_C * (1 - p1Countdown.value / 20))
const p1IsUrgent = computed(() => p1Countdown.value <= 5)

function stopP1Countdown() {
  if (p1Interval) { clearInterval(p1Interval); p1Interval = null }
}

async function startRecording() {
  if (!currentGroupId()) return
  try {
    await beginAudioCapture('phase1')
  } catch {
    return
  }
  p1RecordState.value = 'recording'
  p1Countdown.value = 20
  p1Interval = setInterval(() => {
    p1Countdown.value--
    if (p1Countdown.value <= 0) { void stopRecording() }
  }, 1000)
}

async function stopRecording() {
  if (p1Saving.value) return
  stopP1Countdown()
  p1Saving.value = true
  try {
    const audio = await endAudioCapture()
    const groupId = currentGroupId()
    if (!groupId || !p1Member.value.id || !audio) {
      ElMessage.warning('这一题没有录到音频，可以重录')
      p1RecordState.value = 'ready'
      return
    }

    const result = await uploadVoiceSample({
      groupId,
      userId: p1Member.value.id,
      source: 'intro',
      questionIndex: p1QuestionIdx.value + 1,
      mimeType: currentRecordingMimeType.value || audio.type || 'audio/webm',
      audio,
    })
    p1SampleAdded.value = result.voice_sample_added
    p1SampleWarnings.value = result.warnings || []
    if (!result.voice_sample_added) {
      ElMessage.warning(result.warnings?.[0] || '这段录音质量不太稳定，建议重录')
    } else if (result.warnings?.length) {
      ElMessage.warning(result.warnings[0])
    }
    p1RecordState.value = 'saved'
  } catch (e) {
    p1RecordState.value = 'ready'
    ElMessage.error(extractErrorMessage(e) || '破冰声纹采样失败')
  } finally {
    p1Saving.value = false
  }
}

async function reRecord() {
  stopP1Countdown()
  await endAudioCapture()
  p1Countdown.value = 20
  p1SampleAdded.value = false
  p1SampleWarnings.value = []
  p1RecordState.value = 'ready'
}

function nextP1Question() {
  exiting.value = true
  setTimeout(() => {
    exiting.value = false
    p1RecordState.value = 'ready'
    p1Countdown.value = 20
    p1SampleAdded.value = false
    p1SampleWarnings.value = []
    if (p1QuestionIdx.value < P1_QUESTIONS_PER_MEMBER - 1) {
      p1QuestionIdx.value++
    } else if (p1MemberIdx.value < members.value.length - 1) {
      p1MemberIdx.value++
      p1QuestionIdx.value = 0
    } else {
      screen.value = 'phase2_intro'
    }
  }, 360)
}

function startPhase1() {
  if (members.value.length === 0) return
  p1MemberIdx.value = 0; p1QuestionIdx.value = 0
  p1RecordState.value = 'ready'; p1Countdown.value = 20
  p1SampleAdded.value = false; p1SampleWarnings.value = []
  screen.value = 'phase1'
}

function jumpToPhase2() {
  stopP1Countdown()
  storyCurTurn.value = 0
  storyRecordState.value = 'ready'
  storyCountdown.value = 30
  screen.value = 'phase2_intro'
}

// ─────────────────────────────────────────────────────────────────
// Phase 2 故事接龙状态
// ─────────────────────────────────────────────────────────────────
const storyTotalTurns = computed(() => members.value.length * STORY_ROUNDS)  // 6 when group has 3 members

const storyCurTurn = ref(0)
const storyRecordState = ref<RecordState>('ready')
const storySaving = ref(false)
const storyTurns = ref<IcebreakerStoryTurnPayload[]>([])
const storyTranscribeTasks = new Map<number, Promise<void>>()
const storyCountdown = ref(30)
let storyInterval: ReturnType<typeof setInterval> | null = null

const STORY_RING_C = 2 * Math.PI * 44
const storyRingOffset = computed(() => STORY_RING_C * (1 - storyCountdown.value / 30))
const storyIsUrgent = computed(() => storyCountdown.value <= 5)
const storyProgressPercent = computed(() => storyTotalTurns.value > 0 ? (storyCurTurn.value / storyTotalTurns.value) * 100 : 0)
const storyMember = computed(() => {
  if (members.value.length === 0) return FALLBACK_MEMBER
  return members.value[storyCurTurn.value % members.value.length] ?? FALLBACK_MEMBER
})
const storyRound = computed(() => {
  if (members.value.length === 0) return 1
  return Math.floor(storyCurTurn.value / members.value.length) + 1
})

function getStoryMemberAt(index: number): IcebreakerMember {
  if (members.value.length === 0) return FALLBACK_MEMBER
  return members.value[index % members.value.length] ?? FALLBACK_MEMBER
}

function getStoryRoundAt(index: number): number {
  if (members.value.length === 0) return 1
  return Math.floor(index / members.value.length) + 1
}

function stopStoryCountdown() {
  if (storyInterval) { clearInterval(storyInterval); storyInterval = null }
}

function uploadStoryTurnInBackground(audio: Blob | null) {
  const groupId = currentGroupId()
  const member = storyMember.value
  const round = storyRound.value
  const turnIndex = storyCurTurn.value + 1
  if (!groupId || !member.id || !audio) {
    ElMessage.warning('这一棒没有录到音频，可以重录')
    return
  }

  const mimeType = currentRecordingMimeType.value || audio.type || 'audio/webm'
  let task: Promise<void>
  task = uploadVoiceSample({
    groupId,
    userId: member.id,
    source: 'story',
    round,
    turnIndex,
    mimeType,
    audio,
  }).then((result) => {
    if (storyTranscribeTasks.get(turnIndex) !== task) return
    const text = result.text.trim()
    if (!text) throw new Error('这段录音没有识别到文字')
    const nextTurn: IcebreakerStoryTurnPayload = {
      user_id: member.id,
      user_name: member.name,
      round,
      turn_index: turnIndex,
      text,
    }
    const others = storyTurns.value.filter((turn) => turn.turn_index !== turnIndex)
    storyTurns.value = [...others, nextTurn].sort((a, b) => a.turn_index - b.turn_index)
  }).catch((e) => {
    if (storyTranscribeTasks.get(turnIndex) !== task) return
    console.error('icebreaker transcribe failed', e)
  })
  storyTranscribeTasks.set(turnIndex, task)
}

async function startStoryRecording() {
  if (!currentGroupId()) return
  try {
    await beginAudioCapture('story')
  } catch {
    return
  }
  storyRecordState.value = 'recording'
  storyCountdown.value = 30
  storyInterval = setInterval(() => {
    storyCountdown.value--
    if (storyCountdown.value <= 0) { void stopStoryRecording() }
  }, 1000)
}

async function stopStoryRecording() {
  if (storySaving.value) return
  stopStoryCountdown()
  storySaving.value = true
  try {
    const audio = await endAudioCapture()
    uploadStoryTurnInBackground(audio)
    storyRecordState.value = 'saved'
  } catch (e) {
    storyRecordState.value = 'ready'
    ElMessage.error(extractErrorMessage(e) || '破冰录音转写失败')
  } finally {
    storySaving.value = false
  }
}

async function reStoryRecord() {
  stopStoryCountdown()
  await endAudioCapture()
  storyTranscribeTasks.delete(storyCurTurn.value + 1)
  storyTurns.value = storyTurns.value.filter((turn) => turn.turn_index !== storyCurTurn.value + 1)
  storyCountdown.value = 30
  storyRecordState.value = 'ready'
}

function nextStoryTurn() {
  exiting.value = true
  setTimeout(() => {
    exiting.value = false
    storyRecordState.value = 'ready'
    storyCountdown.value = 30
    if (storyCurTurn.value < storyTotalTurns.value - 1) {
      storyCurTurn.value++
    } else {
      screen.value = 'scoring'
      startScoring()
    }
  }, 360)
}

function startStoryPhase() {
  if (members.value.length === 0) return
  storyCurTurn.value = 0
  storyRecordState.value = 'ready'
  storyCountdown.value = 30
  storyTurns.value = []
  storyTranscribeTasks.clear()
  screen.value = 'phase2'
}

// ─────────────────────────────────────────────────────────────────
// Scoring（AI 点评）
// ─────────────────────────────────────────────────────────────────
const scoringLoading = ref(true)
const scoreValue = ref(0)          // 精彩度 0-100
const scoreComment = ref('')       // 毒舌评价
const scoreMvpIdx = ref(0)         // 最佳桥段奖得主
const scoreMvpTitle = ref('')      // 奖项名
const scoreMvpReason = ref('')     // 得奖理由
const scoreImageGradient = ref('') // 配图背景渐变
const scoreImageEmoji = ref('')    // 配图主视觉
const polishedStory = ref('')
const scoreMeme = ref<ScoreMeme | null>(null)
let scoringTimer: ReturnType<typeof setTimeout> | null = null
const scoreMvpMember = computed(() => members.value[scoreMvpIdx.value] ?? FALLBACK_MEMBER)

async function startScoring() {
  scoringLoading.value = true
  try {
    const draft = createScoreDraft()
    scoreImageGradient.value = draft.imageStyle.gradient
    scoreImageEmoji.value = draft.imageStyle.emoji
    await storyTranscribeTasks.get(storyTotalTurns.value)
    if (storyTurns.value.length === 0) {
      throw new Error('还没有可用于评价的故事文本')
    }
    const result = await evaluateStory({
      group_id: currentGroupId(),
      story_opening: storyOpening,
      members: members.value.map((member) => ({
        user_id: member.id,
        user_name: member.name,
      })),
      turns: storyTurns.value,
    })
    polishedStory.value = result.polished_story
    scoreValue.value = result.score
    scoreComment.value = result.comment
    scoreMvpTitle.value = result.mvp_title
    scoreMvpReason.value = result.mvp_reason
    scoreMvpIdx.value = Math.max(0, members.value.findIndex((member) => member.id === result.mvp_user_id))
    scoreMeme.value = pickIcebreakerMeme({
      score: result.score,
      comment: result.comment,
      mvpTitle: result.mvp_title,
      mvpReason: result.mvp_reason,
      story: result.polished_story,
    })
  } catch (e) {
    const fallback = createScoreDraft()
    scoreValue.value = fallback.value
    scoreComment.value = fallback.comment
    scoreMvpIdx.value = Math.floor(Math.random() * Math.max(members.value.length, 1))
    scoreMvpTitle.value = fallback.mvpTitle
    scoreMvpReason.value = fallback.mvpReason
    polishedStory.value = storyTurns.value.map((turn) => turn.text).join(' ')
    scoreImageGradient.value = fallback.imageStyle.gradient
    scoreImageEmoji.value = fallback.imageStyle.emoji
    scoreMeme.value = pickIcebreakerMeme({
      score: fallback.value,
      comment: fallback.comment,
      mvpTitle: fallback.mvpTitle,
      mvpReason: fallback.mvpReason,
      story: polishedStory.value,
    })
    ElMessage.error(extractErrorMessage(e) || 'AI 评价失败，已展示本地兜底评价')
  } finally {
    scoringTimer = setTimeout(() => { scoringLoading.value = false }, 400)
  }
}

function resetIcebreakerFlow() {
  stopP1Countdown()
  stopStoryCountdown()
  if (scoringTimer) {
    clearTimeout(scoringTimer)
    scoringTimer = null
  }
  p1MemberQuestions.value = buildP1MemberQuestions(members.value.length)
  screen.value = 'intro'
  exiting.value = false
  p1MemberIdx.value = 0
  p1QuestionIdx.value = 0
  p1RecordState.value = 'ready'
  p1Saving.value = false
  p1Countdown.value = 20
  p1SampleAdded.value = false
  p1SampleWarnings.value = []
  storyCurTurn.value = 0
  storyRecordState.value = 'ready'
  storySaving.value = false
  storyTurns.value = []
  storyTranscribeTasks.clear()
  storyCountdown.value = 30
  polishedStory.value = ''
  scoreMeme.value = null
  scoringLoading.value = true
}

onMounted(() => {
  loadIcebreakerMembers()
})

onUnmounted(() => {
  stopP1Countdown()
  stopStoryCountdown()
  void recorder.stopRecording().catch(() => undefined)
  if (scoringTimer) clearTimeout(scoringTimer)
})
</script>

<template>
  <div class="ib">
    <div v-if="pageLoading" class="ib-screen ib-state">
      <div class="ib-state-icon">🧊</div>
      <p class="ib-state-title">正在加载小组成员</p>
      <p class="ib-state-desc">破冰名单会自动关联后台选择的小组。</p>
    </div>

    <div v-else-if="pageError" class="ib-screen ib-state">
      <div class="ib-state-icon">🧊</div>
      <p class="ib-state-title">暂时不能开始破冰</p>
      <p class="ib-state-desc">{{ pageError }}</p>
      <div class="ib-state-actions">
        <button class="ib-btn ib-btn--primary" @click="router.push('/admin/groups')">返回群组管理</button>
        <button class="ib-btn ib-btn--ghost" @click="loadIcebreakerMembers">重新加载</button>
      </div>
    </div>

    <template v-else>

    <!-- ── Phase Nav ────────────────────────────────────────────── -->
    <div class="ib-phase-nav">
      <button
        class="ib-nav-btn"
        :class="{ 'ib-nav-btn--active': screen === 'intro' || screen === 'phase1' }"
        @click="startPhase1"
      >阶段一 · 自我介绍</button>
      <button
        class="ib-nav-btn"
        :class="{ 'ib-nav-btn--active': screen === 'phase2_intro' || screen === 'phase2' || screen === 'scoring' || screen === 'done' }"
        @click="jumpToPhase2"
      >阶段二 · 故事接龙</button>
    </div>

    <!-- ── INTRO ─────────────────────────────────────────────────── -->
    <div v-if="screen === 'intro'" class="ib-screen ib-intro">
      <div class="ib-intro-hero">
        <span class="ib-intro-hero-emoji">🧊</span>
        <h1 class="ib-intro-title">破冰时间</h1>
        <p class="ib-intro-subtitle">{{ currentGroupName }} · 开始正式讨论前，用几分钟互相认识一下</p>
      </div>

      <div class="ib-intro-phases">
        <div class="ib-intro-phase">
          <span class="ib-intro-phase-num">01</span>
          <div class="ib-intro-phase-body">
            <p class="ib-intro-phase-title">自我介绍</p>
            <p class="ib-intro-phase-desc">每人回答三个问题，各有 20 秒，让大家互相了解</p>
          </div>
        </div>
        <div class="ib-intro-phase">
          <span class="ib-intro-phase-num">02</span>
          <div class="ib-intro-phase-body">
            <p class="ib-intro-phase-title">故事接龙</p>
            <p class="ib-intro-phase-desc">从随机开头轮流续写，两轮后由 AI 点评故事</p>
          </div>
        </div>
      </div>

      <div class="ib-intro-members">
        <div v-for="m in members" :key="m.id" class="ib-intro-member">
          <div class="ib-avatar ib-avatar--lg" :style="{ background: m.bg }">{{ m.initial }}</div>
          <span class="ib-intro-member-name">{{ m.name }}</span>
        </div>
      </div>

      <button class="ib-btn ib-btn--primary ib-btn--lg" @click="startPhase1">
        开始破冰
      </button>
    </div>

    <!-- ── PHASE 1 ──────────────────────────────────────────────── -->
    <div
      v-else-if="screen === 'phase1'"
      class="ib-screen ib-p1"
      :class="{ 'ib-screen--exit': exiting }"
    >
      <div class="ib-topbar">
        <div class="ib-progress">
          <div class="ib-progress-fill" :style="{ width: `${p1ProgressPercent}%` }"></div>
        </div>
        <div class="ib-topbar-labels">
          <span class="ib-phase-badge">阶段一：自我介绍</span>
          <span class="ib-step-tag">{{ p1CurrentStep }} / {{ p1Total }}</span>
        </div>
      </div>

      <div class="ib-speaker-callout">
        <div class="ib-avatar ib-avatar--xl" :style="{ background: p1Member.bg }">{{ p1Member.initial }}</div>
        <div>
          <p class="ib-speaker-name">{{ p1Member.name }}</p>
          <p class="ib-speaker-hint">
            <template v-if="p1RecordState === 'ready'">轮到你啦，准备好了就开始 👇</template>
            <template v-else-if="p1RecordState === 'recording'">
              {{ p1Saving ? '正在保存录音……' : '🔴 录音中，说完后点停止' }}
            </template>
            <template v-else>✓ 这题录完啦</template>
          </p>
        </div>
      </div>

      <div class="ib-question-card" :key="`${p1MemberIdx}-${p1QuestionIdx}`">
        <p class="ib-question-text">{{ p1Question }}</p>
      </div>

      <div v-if="p1RecordState === 'ready'" class="ib-record-ready">
        <button class="ib-btn ib-btn--primary ib-btn--lg ib-btn--record" :disabled="p1Saving" @click="startRecording">
          🎙&nbsp;&nbsp;开始录音
        </button>
      </div>

      <div v-else-if="p1RecordState === 'recording'" class="ib-countdown-wrap">
        <svg class="ib-ring" viewBox="0 0 100 100" width="116" height="116">
          <circle cx="50" cy="50" r="44" fill="none" stroke="#e2e8f0" stroke-width="7" />
          <circle
            cx="50" cy="50" r="44"
            fill="none"
            :stroke="p1IsUrgent ? '#ef4444' : '#2563eb'"
            stroke-width="7"
            stroke-linecap="round"
            :stroke-dasharray="RING_C"
            :stroke-dashoffset="p1RingOffset"
            transform="rotate(-90 50 50)"
            style="transition: stroke-dashoffset 1s linear, stroke 0.3s ease"
          />
          <text x="50" y="57" text-anchor="middle" font-size="26" font-weight="700"
            :fill="p1IsUrgent ? '#ef4444' : '#0f172a'">{{ p1Countdown }}</text>
        </svg>
        <button class="ib-btn ib-btn--danger-outline" :disabled="p1Saving" @click="stopRecording">
          {{ p1Saving ? '保存中…' : '停止录音' }}
        </button>
      </div>

      <div v-else class="ib-saved-section">
        <div class="ib-save-banner">
          <span class="ib-save-icon">✓</span>
          <span>{{ p1SampleAdded ? '录得很好，继续下一题吧' : '这段录音质量不太稳定，建议重录' }}</span>
        </div>
        <p v-if="p1SampleWarnings.length" class="ib-state-desc">{{ p1SampleWarnings[0] }}</p>
        <div class="ib-save-actions">
          <button class="ib-btn ib-btn--ghost" :disabled="p1Saving" @click="reRecord">↺ 重录这一题</button>
          <button class="ib-btn ib-btn--primary" @click="nextP1Question">
            {{ p1CurrentStep < p1Total ? '下一题 →' : '进入第二阶段 →' }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── PHASE 2 INTRO ─────────────────────────────────────────── -->
    <div v-else-if="screen === 'phase2_intro'" class="ib-screen ib-p2intro">
      <div class="ib-p2intro-icon">📖</div>
      <h2 class="ib-p2intro-title">第二阶段</h2>
      <h3 class="ib-p2intro-sub">故事接龙</h3>
      <p class="ib-p2intro-desc">
        接下来大家轮流续写同一个故事，<br>
        每人每棒 30 秒，共 {{ STORY_ROUNDS }} 轮。<br>
        最后由 AI 打分点评！
      </p>
      <div class="ib-p2intro-opening-preview">
        <p class="ib-p2intro-opening-label">本次故事开头</p>
        <p class="ib-p2intro-opening-text">{{ storyOpening }}</p>
      </div>
      <button class="ib-btn ib-btn--primary ib-btn--lg" @click="startStoryPhase">
        开始接龙
      </button>
    </div>

    <!-- ── PHASE 2 故事接龙 ────────────────────────────────────────── -->
    <div
      v-else-if="screen === 'phase2'"
      class="ib-screen ib-p2"
      :class="{ 'ib-screen--exit': exiting }"
    >
      <div class="ib-topbar">
        <div class="ib-progress">
          <div
            class="ib-progress-fill ib-progress-fill--green"
            :style="{ width: `${storyProgressPercent}%` }"
          ></div>
        </div>
        <div class="ib-topbar-labels">
          <span class="ib-phase-badge ib-phase-badge--green">故事接龙</span>
          <span class="ib-step-tag">第 {{ storyRound }} 轮 · 第 {{ storyCurTurn + 1 }} / {{ storyTotalTurns }} 棒</span>
        </div>
      </div>

      <!-- 故事开头卡片 -->
      <div class="ib-story-opening-card">
        <p class="ib-story-opening-label">故事开头</p>
        <p class="ib-story-opening-text">{{ storyOpening }}</p>
      </div>

      <!-- 接龙进度链 -->
      <div class="ib-chain-log">
        <div
          v-for="i in storyTotalTurns"
          :key="i"
          class="ib-chain-node"
          :class="{
            'ib-chain-node--done':   (i - 1) < storyCurTurn,
            'ib-chain-node--active': (i - 1) === storyCurTurn,
            'ib-chain-node--future': (i - 1) > storyCurTurn,
          }"
        >
          <div
            class="ib-avatar ib-avatar--sm"
            :style="{ background: getStoryMemberAt(i - 1).bg }"
          >{{ getStoryMemberAt(i - 1).initial }}</div>
          <span class="ib-chain-node-label">
            R{{ getStoryRoundAt(i - 1) }}
          </span>
          <span v-if="(i - 1) < storyCurTurn" class="ib-chain-node-status ib-chain-done-mark">✓</span>
          <span v-else-if="(i - 1) === storyCurTurn" class="ib-chain-node-status ib-chain-active-mark">●</span>
        </div>
      </div>

      <!-- 当前发言者 -->
      <div class="ib-speaker-callout">
        <div class="ib-avatar ib-avatar--xl" :style="{ background: storyMember.bg }">{{ storyMember.initial }}</div>
        <div>
          <p class="ib-speaker-name">{{ storyMember.name }}</p>
          <p class="ib-speaker-hint">
            <template v-if="storyRecordState === 'ready'">轮到你接龙啦，准备好了就开始 👇</template>
            <template v-else-if="storyRecordState === 'recording'">
              {{ storySaving ? '正在转写这一棒……' : '🔴 接龙中，说完后点停止' }}
            </template>
            <template v-else>✓ 这棒已转写完成！</template>
          </p>
        </div>
      </div>

      <!-- 录音控件 -->
      <div v-if="storyRecordState === 'ready'" class="ib-record-ready">
        <button class="ib-btn ib-btn--primary ib-btn--lg ib-btn--record ib-btn--green" :disabled="storySaving" @click="startStoryRecording">
          🎙&nbsp;&nbsp;开始接龙
        </button>
      </div>

      <div v-else-if="storyRecordState === 'recording'" class="ib-countdown-wrap">
        <svg class="ib-ring" viewBox="0 0 100 100" width="116" height="116">
          <circle cx="50" cy="50" r="44" fill="none" stroke="#e2e8f0" stroke-width="7" />
          <circle
            cx="50" cy="50" r="44"
            fill="none"
            :stroke="storyIsUrgent ? '#ef4444' : '#10b981'"
            stroke-width="7"
            stroke-linecap="round"
            :stroke-dasharray="STORY_RING_C"
            :stroke-dashoffset="storyRingOffset"
            transform="rotate(-90 50 50)"
            style="transition: stroke-dashoffset 1s linear, stroke 0.3s ease"
          />
          <text x="50" y="57" text-anchor="middle" font-size="26" font-weight="700"
            :fill="storyIsUrgent ? '#ef4444' : '#0f172a'">{{ storyCountdown }}</text>
        </svg>
        <button class="ib-btn ib-btn--danger-outline" :disabled="storySaving" @click="stopStoryRecording">
          {{ storySaving ? '转写中…' : '停止接龙' }}
        </button>
      </div>

      <div v-else class="ib-saved-section">
        <div class="ib-save-banner ib-save-banner--green">
          <span class="ib-save-icon">✓</span>
          <span>{{ storyMember.name }} 的故事片段已转写</span>
        </div>
        <div class="ib-save-actions">
          <button class="ib-btn ib-btn--ghost" :disabled="storySaving" @click="reStoryRecord">↺ 重新接龙</button>
          <button class="ib-btn ib-btn--primary" @click="nextStoryTurn">
            {{ storyCurTurn < storyTotalTurns - 1 ? '下一棒 →' : '查看 AI 点评 →' }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── SCORING AI 点评 ────────────────────────────────────────── -->
    <div v-else-if="screen === 'scoring'" class="ib-screen ib-scoring">

      <!-- 加载中 -->
      <template v-if="scoringLoading">
        <div class="ib-scoring-loading">
          <div class="ib-scoring-robot">🤖</div>
          <p class="ib-scoring-loading-title">AI 正在整理并分析你们的故事……</p>
          <div class="ib-scoring-dots">
            <span></span><span></span><span></span>
          </div>
        </div>
      </template>

      <!-- 结果揭晓 -->
      <Transition name="ib-rise">
        <div v-if="!scoringLoading" class="ib-scoring-result">

          <!-- 精彩度大分 -->
          <div class="ib-score-hero">
            <p class="ib-score-hero-label">精彩度评分</p>
            <div class="ib-score-hero-number">
              <span class="ib-score-value">{{ scoreValue }}</span>
              <span class="ib-score-unit">分</span>
            </div>
            <div class="ib-score-bar-wrap">
              <div class="ib-score-bar-fill" :style="{ width: `${scoreValue}%` }"></div>
            </div>
          </div>

          <!-- 毒舌评价 -->
          <div class="ib-score-comment-card">
            <span class="ib-score-comment-robot">🤖</span>
            <p class="ib-score-comment-text">{{ scoreComment }}</p>
          </div>

          <!-- 故事表情包 -->
          <div v-if="scoreMeme" class="ib-score-meme">
            <div class="ib-score-meme-media" :style="{ background: scoreImageGradient }">
              <img
                class="ib-score-meme-img"
                :src="scoreMeme.imageUrl"
                :alt="scoreMeme.label"
                loading="lazy"
              >
              <span class="ib-score-meme-fallback">{{ scoreMeme.fallbackEmoji }}</span>
            </div>
            <div class="ib-score-meme-body">
              <p class="ib-score-meme-label">本组故事表情</p>
              <p class="ib-score-meme-title">{{ scoreMeme.label }}</p>
              <p class="ib-score-meme-caption">{{ scoreMeme.mood }} · {{ storyOpening }}</p>
            </div>
          </div>

          <!-- 最佳桥段奖 -->
          <div class="ib-score-award">
            <div class="ib-score-award-trophy">🏅</div>
            <div class="ib-score-award-body">
              <p class="ib-score-award-label">本场称号</p>
              <p class="ib-score-award-title">{{ scoreMvpTitle }}</p>
              <div class="ib-score-award-winner">
                <div class="ib-avatar ib-avatar--lg" :style="{ background: scoreMvpMember.bg }">
                  {{ scoreMvpMember.initial }}
                </div>
                <span class="ib-score-award-name">{{ scoreMvpMember.name }}</span>
              </div>
              <p class="ib-score-award-reason">{{ scoreMvpReason }}</p>
            </div>
          </div>

          <div v-if="polishedStory" class="ib-score-story-card">
            <p class="ib-score-story-label">AI 整理版故事</p>
            <p class="ib-score-story-text">{{ polishedStory }}</p>
          </div>

          <button class="ib-btn ib-btn--primary ib-btn--lg" @click="screen = 'done'">
            完成破冰 🎉
          </button>
        </div>
      </Transition>
    </div>

    <!-- ── DONE ──────────────────────────────────────────────────── -->
    <div v-else-if="screen === 'done'" class="ib-screen ib-done">
      <div class="ib-done-confetti" aria-hidden="true">
        <span v-for="i in 20" :key="i" class="ib-confetti-dot" :style="{ '--i': i }"></span>
      </div>
      <span class="ib-done-emoji">🎉</span>
      <h2 class="ib-done-title">破冰完成！</h2>
      <p class="ib-done-desc">大家已经互相认识了，开始正式讨论吧。</p>

      <div class="ib-done-members">
        <div v-for="m in members" :key="m.id" class="ib-done-member">
          <div class="ib-avatar ib-avatar--xl" :style="{ background: m.bg }">{{ m.initial }}</div>
          <span class="ib-done-member-name">{{ m.name }}</span>
        </div>
      </div>

      <div class="ib-done-actions">
        <button class="ib-btn ib-btn--primary ib-btn--lg" @click="router.push('/admin/groups')">
          返回群组管理
        </button>
        <button class="ib-btn ib-btn--ghost" @click="screen = 'intro'">再来一次</button>
      </div>
    </div>

    </template>
  </div>
</template>
