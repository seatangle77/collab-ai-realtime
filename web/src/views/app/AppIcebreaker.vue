<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// ── Static mock members（后续替换为 group API 返回的真实成员）──
const MEMBERS = [
  { id: '1', name: '张三', initial: '张', bg: '#3b82f6' },
  { id: '2', name: '李四', initial: '李', bg: '#8b5cf6' },
  { id: '3', name: '王五', initial: '王', bg: '#10b981' },
]

// ─────────────────────────────────────────────────────────────────
// 工具函数
// ─────────────────────────────────────────────────────────────────
function shuffle<T>(arr: T[]): T[] {
  const a = [...arr]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    const tmp = a[i] as T
    a[i] = a[j] as T
    a[j] = tmp
  }
  return a
}

// ─────────────────────────────────────────────────────────────────
// Phase 1 题库
// ─────────────────────────────────────────────────────────────────
const P1_FIXED = '先介绍一下自己——你叫什么名字？你的星座是什么？MBTI 是什么？（不知道 MBTI 的话，说说你觉得自己偏内向还是外向？）'

const P1_EXTRA_POOL = [
  '用一道菜来形容你自己——你是什么菜？为什么？',
  '你有没有一个吃东西的奇怪口味偏好，说出来别人都觉得你怪？',
  '你有没有一个"连自己都觉得很蠢但就是改不掉"的习惯？',
  '你在朋友群里通常是什么角色——发疯的、拉架的、还是潜水的？',
  '你最近发呆的时候在想什么？',
  '你最近有没有做过一件事，做完之后在心里默默给自己鼓掌的？',
  '朋友最常拿你开玩笑的点是什么？',
  '你有没有一个"理论上该戒掉但完全没打算戒"的坏习惯？',
  '你上一次骗自己"就最后一次"是什么事？',
  '你有没有一件"只要没人看见就不算"的事？',
  '你最近做过最"不像自己"的一件事是什么？',
  '你有没有一首歌，单曲循环次数自己都不敢数？',
  '你有没有一个"只有你自己觉得好笑、但给别人解释半天他们也不懂"的梗？',
  '你睡前胡思乱想的时候通常在想什么？',
  '你最容易"破防"的点是什么——什么事会让你突然绷不住？',
  '你在家一个人的时候，会做什么在外面绝对不做的事？',
  '你有没有一件事，"明明知道在浪费时间，但就是停不下来"？',
  '你上一次在公共场合尴尬到想消失是什么时候？',
  '你有没有一个偷偷坚持的小迷信或仪式感？',
  '如果给你现在的状态配一首 BGM，你会选什么歌？',
  '如果你是一种天气，你今天是什么天气？',
  '你有没有一件"明明不该笑但还是笑出来了"的事？',
  '你最近搜索过的最奇怪的一个问题是什么？',
  '你有没有一个"偷偷挺厉害但很少告诉别人"的技能？',
]

// 每位成员：[固定题, 随机题1, 随机题2]
const p1MemberQuestions: string[][] = MEMBERS.map(() =>
  [P1_FIXED, ...shuffle(P1_EXTRA_POOL).slice(0, 2)]
)

// ─────────────────────────────────────────────────────────────────
// Phase 2 故事接龙题库
// ─────────────────────────────────────────────────────────────────
const STORY_POOL = [
  '一个快递员在送一封没有地址的包裹，上面只写着"给最需要它的人"……',
  '深夜 12 点，手机突然收到一条陌生消息："我知道你今天做了什么。"……',
  '便利店收银台上，你发现了一张字条：如果你捡到这张纸，请不要回头……',
  '早上醒来，你发现镜子里的自己比你早了整整三秒……',
  '电梯门打开，里面站着的人和你长得一模一样，而且正在按同一层楼……',
  '一只流浪猫突然开口说了一句话，然后就再也不说了……',
  '博物馆镇馆之宝今天早上不翼而飞，监控只拍到它自己走出了大门……',
  '不知从何时起，城里所有人都忘记了"蓝色"这种颜色……',
  '废弃游乐场里，一架旋转木马在没有风的深夜自己转了起来……',
  '旧书店里有一本日记，翻开来，上面写的竟然是你明年 365 天的每一天……',
  '全市所有时钟在同一秒停了下来，指针停在了 3:33……',
  '邮差送来一封信，收件人是「二十年后的你」，寄件人是「现在的你」……',
]

const storyOpening = shuffle(STORY_POOL)[0]!

// ─────────────────────────────────────────────────────────────────
// Flow
// ─────────────────────────────────────────────────────────────────
type Screen = 'intro' | 'phase1' | 'phase2_intro' | 'phase2' | 'scoring' | 'done'
const screen = ref<Screen>('intro')
const exiting = ref(false)

// ─────────────────────────────────────────────────────────────────
// Phase 1 状态
// ─────────────────────────────────────────────────────────────────
type RecordState = 'ready' | 'recording' | 'saved'

const p1MemberIdx = ref(0)
const p1QuestionIdx = ref(0)
const p1RecordState = ref<RecordState>('ready')
const p1Countdown = ref(20)
let p1Interval: ReturnType<typeof setInterval> | null = null

const p1Member = computed(() => MEMBERS[p1MemberIdx.value]!)
const p1Question = computed(() => p1MemberQuestions[p1MemberIdx.value]?.[p1QuestionIdx.value] ?? '')
const p1CurrentStep = computed(() => p1MemberIdx.value * 3 + p1QuestionIdx.value + 1)
const P1_TOTAL = 9

const RING_C = 2 * Math.PI * 44
const p1RingOffset = computed(() => RING_C * (1 - p1Countdown.value / 20))
const p1IsUrgent = computed(() => p1Countdown.value <= 5)

function stopP1Countdown() {
  if (p1Interval) { clearInterval(p1Interval); p1Interval = null }
}

function startRecording() {
  p1RecordState.value = 'recording'
  p1Countdown.value = 20
  p1Interval = setInterval(() => {
    p1Countdown.value--
    if (p1Countdown.value <= 0) { stopP1Countdown(); p1RecordState.value = 'saved' }
  }, 1000)
}

function stopRecording() { stopP1Countdown(); p1RecordState.value = 'saved' }

function reRecord() { stopP1Countdown(); p1Countdown.value = 20; p1RecordState.value = 'ready' }

function nextP1Question() {
  exiting.value = true
  setTimeout(() => {
    exiting.value = false
    p1RecordState.value = 'ready'
    p1Countdown.value = 20
    if (p1QuestionIdx.value < 2) {
      p1QuestionIdx.value++
    } else if (p1MemberIdx.value < 2) {
      p1MemberIdx.value++
      p1QuestionIdx.value = 0
    } else {
      screen.value = 'phase2_intro'
    }
  }, 360)
}

function startPhase1() {
  p1MemberIdx.value = 0; p1QuestionIdx.value = 0
  p1RecordState.value = 'ready'; p1Countdown.value = 20
  screen.value = 'phase1'
}

// ─────────────────────────────────────────────────────────────────
// Phase 2 故事接龙状态
// ─────────────────────────────────────────────────────────────────
const STORY_ROUNDS = 2
const STORY_TOTAL_TURNS = MEMBERS.length * STORY_ROUNDS  // 6

const storyCurTurn = ref(0)
const storyRecordState = ref<RecordState>('ready')
const storyCountdown = ref(30)
let storyInterval: ReturnType<typeof setInterval> | null = null

const STORY_RING_C = 2 * Math.PI * 44
const storyRingOffset = computed(() => STORY_RING_C * (1 - storyCountdown.value / 30))
const storyIsUrgent = computed(() => storyCountdown.value <= 5)
const storyMember = computed(() => MEMBERS[storyCurTurn.value % MEMBERS.length]!)
const storyRound = computed(() => Math.floor(storyCurTurn.value / MEMBERS.length) + 1)

function stopStoryCountdown() {
  if (storyInterval) { clearInterval(storyInterval); storyInterval = null }
}

function startStoryRecording() {
  storyRecordState.value = 'recording'
  storyCountdown.value = 30
  storyInterval = setInterval(() => {
    storyCountdown.value--
    if (storyCountdown.value <= 0) { stopStoryCountdown(); storyRecordState.value = 'saved' }
  }, 1000)
}

function stopStoryRecording() { stopStoryCountdown(); storyRecordState.value = 'saved' }

function reStoryRecord() { stopStoryCountdown(); storyCountdown.value = 30; storyRecordState.value = 'ready' }

function nextStoryTurn() {
  exiting.value = true
  setTimeout(() => {
    exiting.value = false
    storyRecordState.value = 'ready'
    storyCountdown.value = 30
    if (storyCurTurn.value < STORY_TOTAL_TURNS - 1) {
      storyCurTurn.value++
    } else {
      screen.value = 'scoring'
      startScoring()
    }
  }, 360)
}

function startStoryPhase() {
  storyCurTurn.value = 0
  storyRecordState.value = 'ready'
  storyCountdown.value = 30
  screen.value = 'phase2'
}

// ─────────────────────────────────────────────────────────────────
// Scoring（AI 点评）
// ─────────────────────────────────────────────────────────────────
interface ScoreDim { label: string; emoji: string; score: number; max: number }

const scoringLoading = ref(true)
const scoreDims = ref<ScoreDim[]>([])
const scoreMvpIdx = ref(0)
const scoreTags = ref<string[]>([])
const scoreSummary = ref('')
let scoringTimer: ReturnType<typeof setTimeout> | null = null

const SCORE_TAGS_POOL = ['悬疑', '奇幻', '温情', '搞笑', '惊悚', '励志', '科幻', '治愈', '反转', '热血']

const SCORE_SUMMARIES = [
  '三位讲述者将这个神秘的开头推向了始料未及的方向，每一棒都充满惊喜！',
  '想象力爆棚！从开头的悬念到意外的结尾，团队默契让故事走向了全新高度。',
  '充满创意的接龙！大家的发言相互呼应，把一个小开头变成了难忘的故事。',
  '反转不断，高潮迭起！这场故事接龙展示了大家不俗的创造力和默契配合。',
]

function startScoring() {
  const DIMS: Omit<ScoreDim, 'score'>[] = [
    { label: '故事完整度', emoji: '📖', max: 5 },
    { label: '想象力指数', emoji: '✨', max: 5 },
    { label: '团队配合度', emoji: '🤝', max: 5 },
    { label: '情节反转数', emoji: '🎭', max: 5 },
  ]
  scoreDims.value = DIMS.map(d => ({ ...d, score: Math.floor(Math.random() * 2) + 4 }))
  scoreMvpIdx.value = Math.floor(Math.random() * MEMBERS.length)
  scoreTags.value = shuffle(SCORE_TAGS_POOL).slice(0, 3)
  scoreSummary.value = SCORE_SUMMARIES[Math.floor(Math.random() * SCORE_SUMMARIES.length)]!
  scoringLoading.value = true
  scoringTimer = setTimeout(() => { scoringLoading.value = false }, 2600)
}

onUnmounted(() => {
  stopP1Countdown()
  stopStoryCountdown()
  if (scoringTimer) clearTimeout(scoringTimer)
})
</script>

<template>
  <div class="ib">

    <!-- ── INTRO ─────────────────────────────────────────────────── -->
    <div v-if="screen === 'intro'" class="ib-screen ib-intro">
      <div class="ib-intro-hero">
        <span class="ib-intro-hero-emoji">🧊</span>
        <h1 class="ib-intro-title">破冰时间</h1>
        <p class="ib-intro-subtitle">开始正式讨论前，用几分钟互相认识一下</p>
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
        <div v-for="m in MEMBERS" :key="m.id" class="ib-intro-member">
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
          <div class="ib-progress-fill" :style="{ width: `${((p1CurrentStep - 1) / P1_TOTAL) * 100}%` }"></div>
        </div>
        <div class="ib-topbar-labels">
          <span class="ib-phase-badge">阶段一：自我介绍</span>
          <span class="ib-step-tag">{{ p1CurrentStep }} / {{ P1_TOTAL }}</span>
        </div>
      </div>

      <div class="ib-speaker-callout">
        <div class="ib-avatar ib-avatar--xl" :style="{ background: p1Member.bg }">{{ p1Member.initial }}</div>
        <div>
          <p class="ib-speaker-name">{{ p1Member.name }}</p>
          <p class="ib-speaker-hint">
            <template v-if="p1RecordState === 'ready'">轮到你啦，准备好了就开始 👇</template>
            <template v-else-if="p1RecordState === 'recording'">🔴 录音中，说完后点停止</template>
            <template v-else>✓ 这题录完啦</template>
          </p>
        </div>
      </div>

      <div class="ib-question-card" :key="`${p1MemberIdx}-${p1QuestionIdx}`">
        <p class="ib-question-text">{{ p1Question }}</p>
      </div>

      <div v-if="p1RecordState === 'ready'" class="ib-record-ready">
        <button class="ib-btn ib-btn--primary ib-btn--lg ib-btn--record" @click="startRecording">
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
        <button class="ib-btn ib-btn--danger-outline" @click="stopRecording">停止录音</button>
      </div>

      <div v-else class="ib-saved-section">
        <div class="ib-save-banner">
          <span class="ib-save-icon">✓</span>
          <span>{{ p1Member.name }} 的声音特征已记录</span>
        </div>
        <div class="ib-save-actions">
          <button class="ib-btn ib-btn--ghost" @click="reRecord">↺ 重录这一题</button>
          <button class="ib-btn ib-btn--primary" @click="nextP1Question">
            {{ p1CurrentStep < P1_TOTAL ? '下一题 →' : '进入第二阶段 →' }}
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
            :style="{ width: `${(storyCurTurn / STORY_TOTAL_TURNS) * 100}%` }"
          ></div>
        </div>
        <div class="ib-topbar-labels">
          <span class="ib-phase-badge ib-phase-badge--green">故事接龙</span>
          <span class="ib-step-tag">第 {{ storyRound }} 轮 · 第 {{ storyCurTurn + 1 }} / {{ STORY_TOTAL_TURNS }} 棒</span>
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
          v-for="i in STORY_TOTAL_TURNS"
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
            :style="{ background: MEMBERS[(i - 1) % MEMBERS.length]!.bg }"
          >{{ MEMBERS[(i - 1) % MEMBERS.length]!.initial }}</div>
          <span class="ib-chain-node-label">
            R{{ Math.floor((i - 1) / MEMBERS.length) + 1 }}
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
            <template v-else-if="storyRecordState === 'recording'">🔴 接龙中，说完后点停止</template>
            <template v-else>✓ 这棒接完啦！</template>
          </p>
        </div>
      </div>

      <!-- 录音控件 -->
      <div v-if="storyRecordState === 'ready'" class="ib-record-ready">
        <button class="ib-btn ib-btn--primary ib-btn--lg ib-btn--record ib-btn--green" @click="startStoryRecording">
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
        <button class="ib-btn ib-btn--danger-outline" @click="stopStoryRecording">停止接龙</button>
      </div>

      <div v-else class="ib-saved-section">
        <div class="ib-save-banner ib-save-banner--green">
          <span class="ib-save-icon">✓</span>
          <span>{{ storyMember.name }} 的故事片段已记录</span>
        </div>
        <div class="ib-save-actions">
          <button class="ib-btn ib-btn--ghost" @click="reStoryRecord">↺ 重新接龙</button>
          <button class="ib-btn ib-btn--primary" @click="nextStoryTurn">
            {{ storyCurTurn < STORY_TOTAL_TURNS - 1 ? '下一棒 →' : '查看 AI 点评 →' }}
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
          <p class="ib-scoring-loading-title">AI 正在分析你们的故事……</p>
          <div class="ib-scoring-dots">
            <span></span><span></span><span></span>
          </div>
        </div>
      </template>

      <!-- 结果揭晓 -->
      <Transition name="ib-rise">
        <div v-if="!scoringLoading" class="ib-scoring-result">

          <div class="ib-scoring-header">
            <span class="ib-scoring-trophy">🏆</span>
            <h2 class="ib-scoring-title">AI 点评出炉！</h2>
          </div>

          <!-- 故事总评 -->
          <div class="ib-scoring-summary-card">
            <p class="ib-scoring-summary-text">"{{ scoreSummary }}"</p>
            <div class="ib-scoring-tags">
              <span v-for="tag in scoreTags" :key="tag" class="ib-scoring-tag">{{ tag }}</span>
            </div>
          </div>

          <!-- 评分维度 -->
          <div class="ib-scoring-dims">
            <div v-for="dim in scoreDims" :key="dim.label" class="ib-scoring-dim">
              <span class="ib-scoring-dim-emoji">{{ dim.emoji }}</span>
              <div class="ib-scoring-dim-body">
                <div class="ib-scoring-dim-top">
                  <span class="ib-scoring-dim-label">{{ dim.label }}</span>
                  <span class="ib-scoring-dim-score">{{ dim.score }}/{{ dim.max }}</span>
                </div>
                <div class="ib-stars">
                  <span
                    v-for="i in dim.max"
                    :key="i"
                    class="ib-star"
                    :class="{ 'ib-star--filled': i <= dim.score }"
                  >★</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 最佳故事家 -->
          <div class="ib-scoring-mvp">
            <div class="ib-avatar ib-avatar--xl" :style="{ background: MEMBERS[scoreMvpIdx]!.bg }">
              {{ MEMBERS[scoreMvpIdx]!.initial }}
            </div>
            <div>
              <p class="ib-scoring-mvp-label">🌟 最佳故事家</p>
              <p class="ib-scoring-mvp-name">{{ MEMBERS[scoreMvpIdx]!.name }}</p>
            </div>
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
        <div v-for="m in MEMBERS" :key="m.id" class="ib-done-member">
          <div class="ib-avatar ib-avatar--xl" :style="{ background: m.bg }">{{ m.initial }}</div>
          <span class="ib-done-member-name">{{ m.name }}</span>
        </div>
      </div>

      <div class="ib-done-actions">
        <button class="ib-btn ib-btn--primary ib-btn--lg" @click="router.push('/app/sessions')">
          进入讨论
        </button>
        <button class="ib-btn ib-btn--ghost" @click="screen = 'intro'">再来一次</button>
      </div>
    </div>

  </div>
</template>

<style scoped>
/* ── Container ─────────────────────────────────────────────────── */
.ib {
  max-width: 960px;
  margin: 0 auto;
  padding: 8px 24px 80px;
}

/* ── Screen base ────────────────────────────────────────────────── */
.ib-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 22px;
  animation: ib-enter 0.35s cubic-bezier(0.22, 1, 0.36, 1);
}

.ib-screen--exit {
  animation: ib-leave 0.32s cubic-bezier(0.55, 0, 1, 0.45) forwards;
  pointer-events: none;
}

@keyframes ib-enter {
  from { opacity: 0; transform: translateY(18px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes ib-leave {
  from { opacity: 1; transform: translateY(0); }
  to   { opacity: 0; transform: translateY(-14px); }
}

/* ── Progress bar ───────────────────────────────────────────────── */
.ib-topbar {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ib-progress {
  width: 100%;
  height: 4px;
  background: var(--app-border);
  border-radius: 999px;
  overflow: hidden;
}

.ib-progress-fill {
  height: 100%;
  background: var(--app-primary);
  border-radius: 999px;
  transition: width 0.5s ease;
}

.ib-progress-fill--green {
  background: linear-gradient(90deg, #34d399, #10b981);
}

.ib-topbar-labels {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ib-phase-badge {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-primary);
  background: var(--app-primary-soft);
  padding: 4px 12px;
  border-radius: 999px;
}

.ib-phase-badge--green {
  color: #065f46;
  background: #d1fae5;
}

.ib-step-tag {
  font-size: 15px;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
}

/* ── Avatar ─────────────────────────────────────────────────────── */
.ib-avatar {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}

.ib-avatar--sm {
  width: 30px;
  height: 30px;
  font-size: 12px;
}

.ib-avatar--lg {
  width: 44px;
  height: 44px;
  font-size: 16px;
}

.ib-avatar--xl {
  width: 56px;
  height: 56px;
  font-size: 20px;
}

/* ── Buttons ─────────────────────────────────────────────────────── */
.ib-btn {
  border-radius: var(--app-radius-pill);
  padding: 10px 28px;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  border: none;
  transition: all 0.18s ease;
  line-height: 1.4;
}

.ib-btn--primary {
  background: var(--app-primary);
  color: #fff;
}

.ib-btn--primary:hover:not(:disabled) {
  background: var(--app-primary-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
}

.ib-btn--green {
  background: #10b981 !important;
}

.ib-btn--green:hover:not(:disabled) {
  background: #059669 !important;
  box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35) !important;
}

.ib-btn--ghost {
  background: none;
  color: var(--app-text-secondary);
  border: 1.5px solid transparent;
}

.ib-btn--ghost:hover {
  color: var(--app-text-primary);
  border-color: var(--app-border);
}

.ib-btn--lg {
  padding: 13px 40px;
  font-size: 16px;
}

.ib-btn--disabled,
.ib-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none !important;
  box-shadow: none !important;
}

.ib-btn--danger-outline {
  background: none;
  border: 1.5px solid #ef4444;
  color: #ef4444;
  border-radius: var(--app-radius-pill);
  padding: 10px 28px;
  font-size: 15px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.18s ease;
}

.ib-btn--danger-outline:hover {
  background: #fef2f2;
}

/* ── INTRO ───────────────────────────────────────────────────────── */
.ib-intro {
  padding-top: 16px;
}

.ib-intro-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 32px 24px 28px;
  width: 100%;
  background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%);
  border-radius: 18px;
  border: 1px solid var(--app-border);
}

.ib-intro-hero-emoji {
  font-size: 52px;
  line-height: 1;
}

.ib-intro-title {
  margin: 0;
  font-size: 38px;
  font-weight: 800;
  color: var(--app-text-primary);
  letter-spacing: -0.5px;
}

.ib-intro-subtitle {
  margin: 0;
  font-size: 18px;
  color: var(--app-text-secondary);
}

.ib-intro-phases {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ib-intro-phase {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px 18px;
  background: var(--app-bg-elevated);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  box-shadow: var(--app-shadow-card);
}

.ib-intro-phase-num {
  font-size: 36px;
  font-weight: 800;
  color: var(--app-primary);
  opacity: 0.25;
  line-height: 1;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  letter-spacing: -1px;
}

.ib-intro-phase-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ib-intro-phase-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.ib-intro-phase-desc {
  margin: 0;
  font-size: 16px;
  color: var(--app-text-secondary);
  line-height: 1.6;
}

.ib-intro-members {
  display: flex;
  gap: 20px;
  justify-content: center;
}

.ib-intro-member {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.ib-intro-member-name {
  font-size: 16px;
  color: var(--app-text-secondary);
  font-weight: 500;
}

/* ── PHASE 1 ─────────────────────────────────────────────────────── */
.ib-p1 {
  width: 100%;
}

.ib-speaker-callout {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 16px 20px;
  background: var(--app-bg-elevated);
  border-radius: 14px;
  border: 1.5px solid var(--app-border);
  box-shadow: var(--app-shadow-card);
}

.ib-speaker-name {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.ib-speaker-hint {
  margin: 0;
  font-size: 16px;
  color: var(--app-text-secondary);
}

.ib-question-card {
  width: 100%;
  padding: 28px 24px;
  background: linear-gradient(135deg, #eff6ff 0%, #eef2ff 100%);
  border-radius: 18px;
  border: 1.5px solid #c7d2fe;
  animation: ib-q-enter 0.3s ease;
}

@keyframes ib-q-enter {
  from { opacity: 0; transform: scale(0.97); }
  to   { opacity: 1; transform: scale(1); }
}

.ib-question-text {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: #1e3a8a;
  line-height: 1.45;
  text-align: center;
}

.ib-countdown-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.ib-ring {
  filter: drop-shadow(0 2px 8px rgba(37, 99, 235, 0.15));
}

.ib-record-ready {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.ib-btn--record {
  min-width: 200px;
  font-size: 18px;
  letter-spacing: 0.02em;
}

.ib-saved-section {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.ib-save-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 24px;
  background: #f0fdf4;
  border: 1.5px solid #86efac;
  border-radius: 14px;
  font-size: 17px;
  font-weight: 600;
  color: #166534;
  width: 100%;
  justify-content: center;
  animation: ib-enter 0.3s ease;
}

.ib-save-banner--green {
  background: #ecfdf5;
  border-color: #6ee7b7;
  color: #065f46;
}

.ib-save-icon {
  font-size: 20px;
  font-weight: 800;
  color: #16a34a;
}

.ib-save-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  justify-content: center;
}

/* ── PHASE 2 INTRO ───────────────────────────────────────────────── */
.ib-p2intro {
  padding-top: 32px;
  text-align: center;
}

.ib-p2intro-icon {
  font-size: 64px;
  line-height: 1;
  animation: ib-pulse 1.8s ease-in-out infinite;
}

@keyframes ib-pulse {
  0%, 100% { transform: scale(1); }
  50%       { transform: scale(1.1); }
}

.ib-p2intro-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.ib-p2intro-sub {
  margin: 0;
  font-size: 40px;
  font-weight: 800;
  color: var(--app-text-primary);
  letter-spacing: -0.5px;
}

.ib-p2intro-desc {
  margin: 0;
  font-size: 18px;
  color: var(--app-text-secondary);
  line-height: 1.8;
}

.ib-p2intro-opening-preview {
  width: 100%;
  background: linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%);
  border: 1.5px solid #6ee7b7;
  border-radius: 16px;
  padding: 20px 24px;
  text-align: left;
}

.ib-p2intro-opening-label {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #059669;
}

.ib-p2intro-opening-text {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #064e3b;
  line-height: 1.6;
}

/* ── PHASE 2 故事接龙 ─────────────────────────────────────────────── */
.ib-p2 {
  width: 100%;
}

/* 故事开头卡片 */
.ib-story-opening-card {
  width: 100%;
  padding: 18px 22px;
  background: linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%);
  border: 1.5px solid #6ee7b7;
  border-radius: 14px;
  animation: ib-q-enter 0.3s ease;
}

.ib-story-opening-label {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #059669;
}

.ib-story-opening-text {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #064e3b;
  line-height: 1.6;
}

/* 接龙进度链 */
.ib-chain-log {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  padding: 4px 0;
}

.ib-chain-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 52px;
  padding: 10px 6px;
  border-radius: 12px;
  background: var(--app-bg-elevated);
  border: 1.5px solid var(--app-border);
  transition: all 0.2s ease;
  position: relative;
}

.ib-chain-node--active {
  border-color: #10b981;
  background: #ecfdf5;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15);
}

.ib-chain-node--done {
  background: #f0fdf4;
  border-color: #a7f3d0;
}

.ib-chain-node--future {
  opacity: 0.4;
}

.ib-chain-node-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-muted);
  letter-spacing: 0.02em;
}

.ib-chain-node-status {
  font-size: 12px;
  font-weight: 800;
  position: absolute;
  top: 5px;
  right: 7px;
}

.ib-chain-done-mark {
  color: #10b981;
}

.ib-chain-active-mark {
  color: #10b981;
  animation: ib-blink 1s ease-in-out infinite;
}

@keyframes ib-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}

/* ── SCORING ─────────────────────────────────────────────────────── */
.ib-scoring {
  width: 100%;
  min-height: 60vh;
  justify-content: center;
}

/* loading */
.ib-scoring-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  padding: 60px 0;
}

.ib-scoring-robot {
  font-size: 72px;
  animation: ib-bob 1.2s ease-in-out infinite;
}

@keyframes ib-bob {
  0%, 100% { transform: translateY(0); }
  50%       { transform: translateY(-10px); }
}

.ib-scoring-loading-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.ib-scoring-dots {
  display: flex;
  gap: 8px;
}

.ib-scoring-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #10b981;
  animation: ib-dot-bounce 1.2s ease-in-out infinite;
}

.ib-scoring-dots span:nth-child(2) { animation-delay: 0.2s; }
.ib-scoring-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes ib-dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40%            { transform: scale(1);   opacity: 1; }
}

/* result */
.ib-scoring-result {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.ib-scoring-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.ib-scoring-trophy {
  font-size: 64px;
  line-height: 1;
}

.ib-scoring-title {
  margin: 0;
  font-size: 32px;
  font-weight: 800;
  color: var(--app-text-primary);
  letter-spacing: -0.5px;
}

/* 总评卡片 */
.ib-scoring-summary-card {
  width: 100%;
  padding: 22px 24px;
  background: linear-gradient(135deg, #fefce8 0%, #fffbeb 100%);
  border: 1.5px solid #fcd34d;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ib-scoring-summary-text {
  margin: 0;
  font-size: 18px;
  font-weight: 500;
  color: #78350f;
  line-height: 1.7;
  font-style: italic;
}

.ib-scoring-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.ib-scoring-tag {
  font-size: 13px;
  font-weight: 600;
  padding: 3px 12px;
  border-radius: 999px;
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fcd34d;
}

/* 评分维度 */
.ib-scoring-dims {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ib-scoring-dim {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 18px;
  background: var(--app-bg-elevated);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  box-shadow: var(--app-shadow-card);
}

.ib-scoring-dim-emoji {
  font-size: 28px;
  flex-shrink: 0;
  line-height: 1;
}

.ib-scoring-dim-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ib-scoring-dim-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ib-scoring-dim-label {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.ib-scoring-dim-score {
  font-size: 15px;
  font-weight: 700;
  color: var(--app-text-secondary);
  font-variant-numeric: tabular-nums;
}

.ib-stars {
  display: flex;
  gap: 3px;
}

.ib-star {
  font-size: 20px;
  color: #d1d5db;
  line-height: 1;
  transition: color 0.2s ease;
}

.ib-star--filled {
  color: #f59e0b;
}

/* MVP */
.ib-scoring-mvp {
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  padding: 18px 22px;
  background: linear-gradient(135deg, #faf5ff 0%, #f5f3ff 100%);
  border: 1.5px solid #c4b5fd;
  border-radius: 16px;
}

.ib-scoring-mvp-label {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #7c3aed;
}

.ib-scoring-mvp-name {
  margin: 0;
  font-size: 24px;
  font-weight: 800;
  color: #4c1d95;
}

/* ── DONE ────────────────────────────────────────────────────────── */
.ib-done {
  padding-top: 24px;
  text-align: center;
  position: relative;
}

.ib-done-confetti {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 200px;
  pointer-events: none;
  overflow: hidden;
}

.ib-confetti-dot {
  position: absolute;
  left: calc(var(--i) * 5%);
  top: calc(var(--i) * 2% - 10px);
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: hsl(calc(var(--i) * 18deg), 80%, 65%);
  animation: ib-fall 3s ease-in calc(var(--i) * 0.12s) infinite;
  opacity: 0;
}

@keyframes ib-fall {
  0%   { opacity: 0; transform: translateY(-20px) rotate(0deg); }
  10%  { opacity: 1; }
  80%  { opacity: 1; }
  100% { opacity: 0; transform: translateY(180px) rotate(720deg); }
}

.ib-done-emoji {
  font-size: 72px;
  line-height: 1;
  display: block;
  position: relative;
  z-index: 1;
}

.ib-done-title {
  margin: 0;
  font-size: 32px;
  font-weight: 800;
  color: var(--app-text-primary);
  letter-spacing: -0.5px;
}

.ib-done-desc {
  margin: 0;
  font-size: 18px;
  color: var(--app-text-secondary);
  line-height: 1.6;
}

.ib-done-members {
  display: flex;
  gap: 24px;
  justify-content: center;
}

.ib-done-member {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.ib-done-member-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--app-text-secondary);
}

.ib-done-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  width: 100%;
}

/* ── Transitions ─────────────────────────────────────────────────── */
.ib-rise-enter-active,
.ib-rise-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}

.ib-rise-enter-from,
.ib-rise-leave-to {
  opacity: 0;
  transform: translateY(16px);
}
</style>
