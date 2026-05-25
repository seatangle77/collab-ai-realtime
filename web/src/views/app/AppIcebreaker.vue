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

// 第一题固定：名字 + 星座 + MBTI 合并
const P1_FIXED = '先介绍一下自己——你叫什么名字？你的星座是什么？MBTI 是什么？（不知道 MBTI 的话，说说你觉得自己偏内向还是外向？）'

// 随机题池
const P1_EXTRA_POOL = [
  '你现在在做什么工作或者在读什么专业？',
  '你今天来之前在干嘛？',
  '用一个词描述你今天的状态',
  '你最近在迷什么？',
  '你平时怎么放松？',
  '你最近看过或玩过让你印象深刻的东西是什么？',
  '如果让你用三个词描述自己，你会选哪三个？',
  '你有没有一个别人不太知道的小爱好？',
  '你觉得自己最大的优点是什么？',
  '你最近有没有在学什么新东西？',
  '你是那种容易交到朋友的人吗？',
  '如果明天不用上班/上学，你会怎么过？',
  '你最喜欢哪种天气？为什么？',
  '你有没有一句最近常挂在嘴边的话或口头禅？',
  '你觉得自己更像猫还是狗？为什么？',
  '你做过最冲动的一件事是什么？',
  '你对自己的城市有什么特别的感情吗？',
  '如果可以立刻掌握一项技能，你会选什么？',
  '你有没有一个坚持了很久的习惯？',
  '你最享受一天中的哪个时间段？',
  '最近让你开心的一件小事是什么？',
  '你更喜欢早起还是熬夜？',
  '如果只能选一种食物吃一整年，你会选什么？',
  '你有没有觉得自己和别人很不一样的地方？',
  '你平时更喜欢一个人待着还是和朋友在一起？',
]

const P2_POOL = [
  { a: '永远只能喝热饮', b: '永远只能喝冷饮' },
  { a: '出门永远迷路', b: '在家永远找不到东西' },
  { a: '每天必须午睡2小时', b: '每天晚上12点前必须睡' },
  { a: '能看见别人的心情但说不出来', b: '能说出自己心情但没人信' },
  { a: '永远不能吃甜的', b: '永远不能吃咸的' },
  { a: '每次说话都会有回音', b: '每次说话都会延迟3秒' },
  { a: '走路永远比别人慢一倍', b: '说话永远比别人快一倍' },
  { a: '永远记得所有尴尬瞬间', b: '永远记不住别人的名字' },
  { a: '每天只能睡5小时但精神好', b: '每天睡10小时但还是困' },
  { a: '说话时嘴边总有字幕显示', b: '脑子里想什么头顶都有气泡显示' },
  { a: '永远不能发朋友圈但可以看', b: '永远可以发朋友圈但看不到别人的' },
  { a: '每次坐电梯必须和陌生人同乘', b: '每次坐电梯都要等超过5分钟' },
  { a: '每次笑都特别大声', b: '每次笑都完全没有声音' },
  { a: '永远不能听音乐', b: '永远不能看视频' },
  { a: '手机永远只剩20%电', b: '手机永远只有2格信号' },
  { a: '永远不能用表情包', b: '永远不能发语音消息' },
  { a: '所有人都知道你的年龄', b: '所有人都知道你的体重' },
  { a: '每次打电话对方声音都很小', b: '每次打电话对方声音都很大' },
  { a: '拍的照片永远有人闯入', b: '拍的照片永远对不上焦' },
  { a: '永远不知道现在几点', b: '永远不知道今天星期几' },
]

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

// 每位成员：[固定题, 随机题1, 随机题2]
const p1MemberQuestions: string[][] = MEMBERS.map(() =>
  [P1_FIXED, ...shuffle(P1_EXTRA_POOL).slice(0, 2)]
)
const p2Questions = shuffle(P2_POOL).slice(0, 6)

// ── Flow ────────────────────────────────────────────────────────
type Screen = 'intro' | 'phase1' | 'phase2_intro' | 'phase2' | 'done'
const screen = ref<Screen>('intro')
const exiting = ref(false)

// ── Phase 1 ─────────────────────────────────────────────────────
type P1RecordState = 'ready' | 'recording' | 'saved'

const p1MemberIdx = ref(0)    // 0-2（哪位成员）
const p1QuestionIdx = ref(0)  // 0-2（第几题）
const p1RecordState = ref<P1RecordState>('ready')
const p1Countdown = ref(20)
let p1Interval: ReturnType<typeof setInterval> | null = null

const p1Member = computed(() => MEMBERS[p1MemberIdx.value]!)
const p1Question = computed(() => p1MemberQuestions[p1MemberIdx.value]?.[p1QuestionIdx.value] ?? '')
const p1CurrentStep = computed(() => p1MemberIdx.value * 3 + p1QuestionIdx.value + 1)
const P1_TOTAL = 9  // 3人 × 3题

const RING_C = 2 * Math.PI * 44
const p1RingOffset = computed(() => RING_C * (1 - p1Countdown.value / 20))
const p1IsUrgent = computed(() => p1Countdown.value <= 5)

function stopCountdown() {
  if (p1Interval) { clearInterval(p1Interval); p1Interval = null }
}

function startRecording() {
  p1RecordState.value = 'recording'
  p1Countdown.value = 20
  p1Interval = setInterval(() => {
    p1Countdown.value--
    if (p1Countdown.value <= 0) {
      stopCountdown()
      p1RecordState.value = 'saved'
    }
  }, 1000)
}

function stopRecording() {
  stopCountdown()
  p1RecordState.value = 'saved'
}

function reRecord() {
  stopCountdown()
  p1Countdown.value = 20
  p1RecordState.value = 'ready'
}

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
  p1MemberIdx.value = 0
  p1QuestionIdx.value = 0
  p1RecordState.value = 'ready'
  p1Countdown.value = 20
  screen.value = 'phase1'
}

// ── Phase 2 ─────────────────────────────────────────────────────
const p2Step = ref(0)
const p2MyVote = ref<'a' | 'b' | null>(null)
const p2SimVotes = ref<{ id: string; choice: 'a' | 'b' }[]>([])
let p2T1: ReturnType<typeof setTimeout> | null = null
let p2T2: ReturnType<typeof setTimeout> | null = null

const p2Q = computed(() => p2Questions[p2Step.value]!)
const p2CountA = computed(() =>
  (p2MyVote.value === 'a' ? 1 : 0) + p2SimVotes.value.filter(v => v.choice === 'a').length)
const p2CountB = computed(() =>
  (p2MyVote.value === 'b' ? 1 : 0) + p2SimVotes.value.filter(v => v.choice === 'b').length)
const p2AllVoted = computed(() => p2MyVote.value !== null && p2SimVotes.value.length >= 2)
const p2CanNext = computed(() => p2MyVote.value !== null)

function clearSim() {
  if (p2T1) { clearTimeout(p2T1); p2T1 = null }
  if (p2T2) { clearTimeout(p2T2); p2T2 = null }
}

function p2Vote(choice: 'a' | 'b') {
  if (p2MyVote.value !== null) return
  p2MyVote.value = choice
  p2T1 = setTimeout(() => {
    const c: 'a' | 'b' = Math.random() > 0.45 ? 'a' : 'b'
    p2SimVotes.value = [...p2SimVotes.value, { id: MEMBERS[1]!.id, choice: c }]
  }, 600 + Math.random() * 500)
  p2T2 = setTimeout(() => {
    const c: 'a' | 'b' = Math.random() > 0.45 ? 'a' : 'b'
    p2SimVotes.value = [...p2SimVotes.value, { id: MEMBERS[2]!.id, choice: c }]
  }, 1100 + Math.random() * 700)
}

function nextP2() {
  if (!p2CanNext.value) return
  clearSim()
  exiting.value = true
  setTimeout(() => {
    if (p2Step.value < p2Questions.length - 1) {
      p2Step.value++
      p2MyVote.value = null
      p2SimVotes.value = []
      exiting.value = false
    } else {
      exiting.value = false
      screen.value = 'done'
    }
  }, 360)
}

function startPhase2() {
  p2Step.value = 0
  p2MyVote.value = null
  p2SimVotes.value = []
  screen.value = 'phase2'
}

function memberById(id: string) {
  return MEMBERS.find(m => m.id === id)
}

onUnmounted(() => {
  stopCountdown()
  clearSim()
})

</script>

<template>
  <div class="ib">

    <!-- ── INTRO ─────────────────────────────────────────────────── -->
    <div v-if="screen === 'intro'" class="ib-screen ib-intro">
      <div class="ib-intro-hero">
        <span class="ib-intro-hero-emoji">🧊</span>
        <h1 class="ib-intro-title">破冰时间</h1>
        <p class="ib-intro-subtitle">开始正式讨论前，用 5 分钟互相认识一下</p>
      </div>

      <div class="ib-intro-phases">
        <div class="ib-intro-phase">
          <span class="ib-intro-phase-num">01</span>
          <div class="ib-intro-phase-body">
            <p class="ib-intro-phase-title">自我介绍</p>
            <p class="ib-intro-phase-desc">每人回答一个问题，各有 45 秒，系统同时采集声音特征</p>
          </div>
        </div>
        <div class="ib-intro-phase">
          <span class="ib-intro-phase-num">02</span>
          <div class="ib-intro-phase-body">
            <p class="ib-intro-phase-title">极端二选一</p>
            <p class="ib-intro-phase-desc">每题大家各选一边，选完再聊聊为什么</p>
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

      <!-- ready：等待点击开始 -->
      <div v-if="p1RecordState === 'ready'" class="ib-record-ready">
        <button class="ib-btn ib-btn--primary ib-btn--lg ib-btn--record" @click="startRecording">
          🎙&nbsp;&nbsp;开始录音
        </button>
      </div>

      <!-- recording：倒计时 + 停止 -->
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
          <text
            x="50" y="57"
            text-anchor="middle"
            font-size="26"
            font-weight="700"
            :fill="p1IsUrgent ? '#ef4444' : '#0f172a'"
          >{{ p1Countdown }}</text>
        </svg>
        <button class="ib-btn ib-btn--danger-outline" @click="stopRecording">停止录音</button>
      </div>

      <!-- saved：保存提示 + 重录 + 下一题 -->
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
      <div class="ib-p2intro-icon">⚡</div>
      <h2 class="ib-p2intro-title">第二阶段</h2>
      <h3 class="ib-p2intro-sub">极端二选一</h3>
      <p class="ib-p2intro-desc">
        接下来每题都是两个极端选项，<br>
        大家各选一边，选完再聊聊为什么。
      </p>
      <div class="ib-p2intro-preview">
        <span class="ib-p2intro-opt ib-p2intro-opt--a">A</span>
        <span class="ib-p2intro-vs">VS</span>
        <span class="ib-p2intro-opt ib-p2intro-opt--b">B</span>
      </div>
      <button class="ib-btn ib-btn--primary ib-btn--lg" @click="startPhase2">
        我准备好了
      </button>
    </div>

    <!-- ── PHASE 2 ──────────────────────────────────────────────── -->
    <div
      v-else-if="screen === 'phase2'"
      class="ib-screen ib-p2"
      :class="{ 'ib-screen--exit': exiting }"
    >
      <div class="ib-topbar">
        <div class="ib-progress">
          <div
            class="ib-progress-fill ib-progress-fill--orange"
            :style="{ width: `${(p2Step / p2Questions.length) * 100}%` }"
          ></div>
        </div>
        <div class="ib-topbar-labels">
          <span class="ib-phase-badge ib-phase-badge--orange">极端二选一</span>
          <span class="ib-step-tag">第 {{ p2Step + 1 }} 题 / {{ p2Questions.length }} 题</span>
        </div>
      </div>

      <div class="ib-options" :key="p2Step">
        <button
          class="ib-option ib-option--a"
          :class="{
            'ib-option--chosen': p2MyVote === 'a',
            'ib-option--dim': p2MyVote !== null && p2MyVote !== 'a',
          }"
          @click="p2Vote('a')"
        >
          <span class="ib-option-letter">A</span>
          <span class="ib-option-text">{{ p2Q.a }}</span>
          <span v-if="p2MyVote === 'a'" class="ib-option-check">✓</span>
        </button>

        <div class="ib-vs">VS</div>

        <button
          class="ib-option ib-option--b"
          :class="{
            'ib-option--chosen': p2MyVote === 'b',
            'ib-option--dim': p2MyVote !== null && p2MyVote !== 'b',
          }"
          @click="p2Vote('b')"
        >
          <span class="ib-option-letter">B</span>
          <span class="ib-option-text">{{ p2Q.b }}</span>
          <span v-if="p2MyVote === 'b'" class="ib-option-check">✓</span>
        </button>
      </div>

      <!-- Votes section（投票后出现）-->
      <Transition name="ib-rise">
        <div v-if="p2MyVote !== null" class="ib-votes">
          <div class="ib-votes-row">
            <!-- 自己的票 -->
            <div class="ib-vote-chip">
              <div class="ib-avatar" :style="{ background: MEMBERS[0]!.bg }">{{ MEMBERS[0]!.initial }}</div>
              <span
                class="ib-vote-tag"
                :class="p2MyVote === 'a' ? 'ib-vote-tag--a' : 'ib-vote-tag--b'"
              >{{ p2MyVote.toUpperCase() }}</span>
            </div>
            <!-- 模拟其他成员的票 -->
            <template v-for="sv in p2SimVotes" :key="sv.id">
              <div class="ib-vote-chip">
                <div class="ib-avatar" :style="{ background: memberById(sv.id)?.bg }">
                  {{ memberById(sv.id)?.initial }}
                </div>
                <span
                  class="ib-vote-tag"
                  :class="sv.choice === 'a' ? 'ib-vote-tag--a' : 'ib-vote-tag--b'"
                >{{ sv.choice.toUpperCase() }}</span>
              </div>
            </template>
            <!-- 等待中的成员 -->
            <template v-if="p2SimVotes.length < 2">
              <div
                v-for="i in (2 - p2SimVotes.length)"
                :key="`wait-${i}`"
                class="ib-vote-chip ib-vote-chip--waiting"
              >
                <div class="ib-avatar ib-avatar--muted">?</div>
                <span class="ib-vote-tag ib-vote-tag--wait">…</span>
              </div>
            </template>
          </div>

          <!-- 汇总结果 -->
          <Transition name="ib-rise">
            <div v-if="p2AllVoted" class="ib-result">
              <div class="ib-result-bar">
                <div
                  class="ib-result-seg ib-result-seg--a"
                  :style="{ flex: p2CountA }"
                >{{ p2CountA }}人选A</div>
                <div
                  class="ib-result-seg ib-result-seg--b"
                  :style="{ flex: p2CountB }"
                >{{ p2CountB }}人选B</div>
              </div>
            </div>
          </Transition>
        </div>
      </Transition>

      <button
        class="ib-btn ib-btn--primary"
        :class="{ 'ib-btn--disabled': !p2CanNext }"
        :disabled="!p2CanNext"
        @click="nextP2"
      >
        {{ p2Step < p2Questions.length - 1 ? '下一题 →' : '完成破冰 ✓' }}
      </button>
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

.ib-progress-fill--orange {
  background: linear-gradient(90deg, #f59e0b, #f97316);
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

.ib-phase-badge--orange {
  color: #92400e;
  background: #fffbeb;
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

.ib-avatar--muted {
  background: #d1d5db !important;
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

.ib-btn--secondary {
  background: var(--app-bg-elevated);
  color: var(--app-text-primary);
  border: 1.5px solid var(--app-border);
}

.ib-btn--secondary:hover {
  border-color: var(--app-primary);
  color: var(--app-primary);
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

.ib-mic-hint {
  margin: 0;
  font-size: 15px;
  color: var(--app-text-muted);
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
  animation: ib-pulse 1.5s ease-in-out infinite;
}

@keyframes ib-pulse {
  0%, 100% { transform: scale(1); }
  50%       { transform: scale(1.08); }
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
  line-height: 1.7;
}

.ib-p2intro-preview {
  display: flex;
  align-items: center;
  gap: 16px;
}

.ib-p2intro-opt {
  width: 64px;
  height: 64px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: 800;
  color: #fff;
}

.ib-p2intro-opt--a {
  background: linear-gradient(135deg, #f59e0b, #d97706);
}

.ib-p2intro-opt--b {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}

.ib-p2intro-vs {
  font-size: 15px;
  font-weight: 800;
  color: var(--app-text-muted);
  letter-spacing: 0.05em;
}

/* ── PHASE 2 ─────────────────────────────────────────────────────── */
.ib-p2 {
  width: 100%;
}

.ib-options {
  width: 100%;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 12px;
  animation: ib-q-enter 0.3s ease;
}

.ib-option {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 36px 24px;
  border-radius: 18px;
  border: none;
  cursor: pointer;
  font-family: inherit;
  min-height: 220px;
  transition: transform 0.2s ease, opacity 0.25s ease, box-shadow 0.2s ease;
  color: #fff;
}

.ib-option--a {
  background: linear-gradient(145deg, #fbbf24, #d97706);
  box-shadow: 0 4px 16px rgba(217, 119, 6, 0.25);
}

.ib-option--b {
  background: linear-gradient(145deg, #60a5fa, #2563eb);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.25);
}

.ib-option:not(.ib-option--chosen):not(.ib-option--dim):hover {
  transform: translateY(-3px);
}

.ib-option--chosen {
  transform: translateY(-4px) scale(1.02);
  outline: 3px solid rgba(255,255,255,0.6);
  outline-offset: 2px;
}

.ib-option--dim {
  opacity: 0.38;
  transform: scale(0.97);
}

.ib-option-letter {
  font-size: 13px;
  font-weight: 800;
  opacity: 0.7;
  letter-spacing: 0.05em;
}

.ib-option-text {
  font-size: 20px;
  font-weight: 700;
  line-height: 1.4;
  text-align: center;
}

.ib-option-check {
  position: absolute;
  top: 12px;
  right: 14px;
  font-size: 18px;
  font-weight: 800;
}

.ib-vs {
  font-size: 13px;
  font-weight: 800;
  color: var(--app-text-muted);
  letter-spacing: 0.08em;
  user-select: none;
}

/* ── Votes section ──────────────────────────────────────────────── */
.ib-votes {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ib-votes-row {
  display: flex;
  gap: 16px;
  justify-content: center;
  flex-wrap: wrap;
}

.ib-vote-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.ib-vote-chip--waiting {
  opacity: 0.5;
}

.ib-vote-tag {
  font-size: 12px;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: 999px;
}

.ib-vote-tag--a {
  background: #fef3c7;
  color: #92400e;
}

.ib-vote-tag--b {
  background: #dbeafe;
  color: #1e40af;
}

.ib-vote-tag--wait {
  background: #f1f5f9;
  color: #94a3b8;
}

.ib-result {
  width: 100%;
}

.ib-result-bar {
  display: flex;
  height: 36px;
  border-radius: 10px;
  overflow: hidden;
  gap: 2px;
}

.ib-result-seg {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  min-width: 0;
  transition: flex 0.5s ease;
  border-radius: 8px;
}

.ib-result-seg--a {
  background: linear-gradient(90deg, #fbbf24, #d97706);
}

.ib-result-seg--b {
  background: linear-gradient(90deg, #60a5fa, #2563eb);
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
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.ib-rise-enter-from,
.ib-rise-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
