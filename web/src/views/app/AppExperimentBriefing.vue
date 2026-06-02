<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

const groupId = typeof route.query.group_id === 'string' ? route.query.group_id : ''

const currentSlide = ref(0)
const TOTAL_SLIDES = 5

function next() {
  if (currentSlide.value < TOTAL_SLIDES - 1) currentSlide.value++
}

function prev() {
  if (currentSlide.value > 0) currentSlide.value--
}

function goTo(index: number) {
  currentSlide.value = index
}

function startIcebreaker() {
  router.push(`/app/icebreaker?group_id=${encodeURIComponent(groupId)}`)
}

function handleKey(e: KeyboardEvent) {
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next()
  if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') prev()
}

import { onMounted, onUnmounted } from 'vue'
onMounted(() => window.addEventListener('keydown', handleKey))
onUnmounted(() => window.removeEventListener('keydown', handleKey))
</script>

<template>
  <div class="slide-root">

    <!-- Slide 0：欢迎 -->
    <div v-if="currentSlide === 0" class="slide slide-welcome">
      <div class="slide-inner center">
        <div class="welcome-badge">研究实验</div>
        <h1 class="welcome-title">探索 AI 辅助小组讨论</h1>
        <p class="welcome-desc">
          这是一次关于<strong>面对面小组讨论</strong>的研究实验<br />
          你将与另外两名小组成员共同完成一个协同任务<br />
          不同小组会被随机分配到不同的实验条件
        </p>
        <div class="welcome-duration">
          <span class="duration-icon">⏱</span>
          <span>预计总时长约 <strong>60 分钟</strong></span>
        </div>
      </div>
    </div>

    <!-- Slide 1：实验流程 -->
    <div v-if="currentSlide === 1" class="slide slide-steps">
      <div class="slide-inner">
        <h2 class="slide-title">实验流程</h2>
        <div class="flow-list">
          <div class="flow-item">
            <div class="flow-num">01</div>
            <div class="flow-text">
              <span class="flow-name">注册 &amp; 登录 &amp; 加入小组</span>
              <span class="flow-sub">打开叮叮 App，用英文用户名注册，登录后选择本次小组进入</span>
            </div>
          </div>
          <div class="flow-item">
            <div class="flow-num">02</div>
            <div class="flow-text">
              <span class="flow-name">破冰环节</span>
              <span class="flow-sub">自我介绍 + 故事接龙，让大家互相了解</span>
            </div>
          </div>
          <div class="flow-item flow-item-highlight">
            <div class="flow-num">03</div>
            <div class="flow-text">
              <span class="flow-name">实验任务 <em>（核心环节）</em></span>
              <span class="flow-sub">5 分钟个人独立任务 + 30 分钟小组讨论</span>
            </div>
          </div>
          <div class="flow-item">
            <div class="flow-num">04</div>
            <div class="flow-text">
              <span class="flow-name">量表填写</span>
              <span class="flow-sub">在叮叮 App「量表」页填写 SRCC 和 PCS，共 2 份</span>
            </div>
          </div>
          <div class="flow-item">
            <div class="flow-num">05</div>
            <div class="flow-text">
              <span class="flow-name">访谈</span>
              <span class="flow-sub">实验人员与小组进行约 10～15 分钟的半结构性访谈</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Slide 2：实验任务说明 -->
    <div v-if="currentSlide === 2" class="slide slide-task">
      <div class="slide-inner">
        <h2 class="slide-title">实验任务</h2>
        <div class="task-blocks">
          <div class="task-block task-block-blue">
            <div class="task-block-header">
              <span class="task-block-icon">✏️</span>
              <span class="task-block-tag">阶段一</span>
            </div>
            <div class="task-block-name">个人独立任务</div>
            <div class="task-block-time">⏱ 5 分钟</div>
            <ul class="task-block-list">
              <li>实验人员发给你一张任务题目</li>
              <li>在<strong>白纸上独立完成排序</strong></li>
              <li>此阶段<strong>不能与其他成员交流</strong></li>
              <li>计时器倒计时结束后进入下一阶段</li>
            </ul>
          </div>
          <div class="task-block task-block-green">
            <div class="task-block-header">
              <span class="task-block-icon">💬</span>
              <span class="task-block-tag">阶段二</span>
            </div>
            <div class="task-block-name">小组讨论</div>
            <div class="task-block-time">⏱ 30 分钟</div>
            <ul class="task-block-list">
              <li>与小组成员共同讨论，分享各自的排序理由</li>
              <li>可以使用<strong>便利贴</strong>辅助整理思路</li>
              <li>讨论结束前，在 <strong>A3 纸</strong>上写下小组共认可的最终答案</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- Slide 3：实验条件 -->
    <div v-if="currentSlide === 3" class="slide slide-conditions">
      <div class="slide-inner">
        <h2 class="slide-title">实验条件</h2>
        <p class="slide-subtitle">你的小组会被随机分配到以下三种条件之一</p>
        <div class="cond-grid">
          <div class="cond-card">
            <div class="cond-icon">🚫</div>
            <div class="cond-name">无辅助小组</div>
            <div class="cond-desc">
              登录完成后将手机交还研究员<br />
              讨论期间<strong>不使用手机</strong><br />
              讨论结束后归还用于填写量表
            </div>
          </div>
          <div class="cond-card">
            <div class="cond-icon">🥽</div>
            <div class="cond-name">智能眼镜小组</div>
            <div class="cond-desc">
              讨论全程<strong>佩戴智能眼镜</strong><br />
              通过眼镜/叮叮收到 AI 推送的摘要与概念词<br />
              点击关键词可即时查询详细解释
            </div>
          </div>
          <div class="cond-card">
            <div class="cond-icon">📱</div>
            <div class="cond-name">APP 通知小组</div>
            <div class="cond-desc">
              讨论中可随时查看叮叮上的<strong>讨论实录</strong><br />
              收到即时 AI 建议通知<br />
              可查看摘要栏与概念词解释
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Slide 4：注意事项 + 开始 -->
    <div v-if="currentSlide === 4" class="slide slide-notes">
      <div class="slide-inner center">
        <h2 class="slide-title">注意事项</h2>
        <ul class="notes-list">
          <li>
            <span class="notes-icon">🔇</span>
            实验全程请将手机设为静音，不使用自己的个人电子设备（实验人员会统一设置）
          </li>
          <li>
            <span class="notes-icon">💬</span>
            讨论过程中请<strong>自然交流</strong>，无需刻意改变说话方式
          </li>
          <li>
            <span class="notes-icon">🙋</span>
            如有任何疑问，随时告知实验人员
          </li>
        </ul>
        <div class="start-area">
          <p class="start-hint">准备好了吗？</p>
          <button class="start-btn" @click="startIcebreaker">开始破冰 →</button>
        </div>
      </div>
    </div>

    <!-- Navigation -->
    <div class="nav-bar">
      <button class="nav-btn" :disabled="currentSlide === 0" @click="prev">‹</button>
      <div class="nav-dots">
        <button
          v-for="i in TOTAL_SLIDES"
          :key="i"
          class="dot"
          :class="{ active: currentSlide === i - 1 }"
          @click="goTo(i - 1)"
        />
      </div>
      <button class="nav-btn" :disabled="currentSlide === TOTAL_SLIDES - 1" @click="next">›</button>
    </div>

    <!-- Keyboard hint -->
    <div class="key-hint">← → 方向键翻页</div>

  </div>
</template>

<style scoped>
/* ── Root ── */
.slide-root {
  position: fixed;
  inset: 0;
  background: #0f172a;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── Slide base ── */
.slide {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 80px 24px;
  overflow: hidden;
}

.slide-inner {
  width: 100%;
  max-width: 1100px;
}

.slide-inner.center {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* ── Slide 0 Welcome ── */
.slide-welcome {
  background: linear-gradient(135deg, #1e3a8a 0%, #1e1b4b 60%, #0f172a 100%);
}

.welcome-badge {
  display: inline-block;
  background: rgba(96, 165, 250, 0.2);
  color: #93c5fd;
  border: 1px solid rgba(96, 165, 250, 0.4);
  border-radius: 100px;
  padding: 8px 24px;
  font-size: 22px;
  letter-spacing: 2px;
  margin-bottom: 32px;
}

.welcome-title {
  font-size: 56px;
  font-weight: 800;
  color: #fff;
  margin: 0 0 28px;
  line-height: 1.2;
}

.welcome-desc {
  font-size: 28px;
  color: #cbd5e1;
  line-height: 1.8;
  margin: 0 0 40px;
}

.welcome-desc strong {
  color: #93c5fd;
}

.welcome-duration {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: rgba(255,255,255,0.08);
  border-radius: 12px;
  padding: 14px 32px;
  font-size: 26px;
  color: #e2e8f0;
}

.duration-icon {
  font-size: 26px;
}

.welcome-duration strong {
  color: #fbbf24;
}

/* ── Slide 1 Steps ── */
.slide-steps {
  background: #0f172a;
}

.slide-title {
  font-size: 40px;
  font-weight: 800;
  color: #f1f5f9;
  margin: 0 0 32px;
  padding-bottom: 16px;
  border-bottom: 3px solid #2563eb;
}

.slide-subtitle {
  font-size: 24px;
  color: #94a3b8;
  margin: -16px 0 28px;
}

.flow-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.flow-item {
  display: flex;
  align-items: center;
  gap: 24px;
  background: rgba(255,255,255,0.05);
  border-radius: 14px;
  padding: 18px 28px;
  border: 1px solid rgba(255,255,255,0.08);
}

.flow-item-highlight {
  background: rgba(37, 99, 235, 0.15);
  border-color: rgba(37, 99, 235, 0.4);
}

.flow-num {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  background: #2563eb;
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
}

.flow-item-highlight .flow-num {
  background: #3b82f6;
  box-shadow: 0 0 0 4px rgba(59,130,246,0.25);
}

.flow-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.flow-name {
  font-size: 26px;
  font-weight: 600;
  color: #f1f5f9;
}

.flow-name em {
  font-style: normal;
  color: #fbbf24;
  font-size: 22px;
  margin-left: 8px;
}

.flow-sub {
  font-size: 21px;
  color: #94a3b8;
}

/* ── Slide 2 Task ── */
.slide-task {
  background: #0f172a;
}

.task-blocks {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.task-block {
  border-radius: 16px;
  padding: 28px 32px;
}

.task-block-blue {
  background: rgba(37, 99, 235, 0.12);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.task-block-green {
  background: rgba(5, 150, 105, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.task-block-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.task-block-icon {
  font-size: 24px;
}

.task-block-tag {
  font-size: 18px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.task-block-name {
  font-size: 30px;
  font-weight: 700;
  color: #f1f5f9;
  margin-bottom: 6px;
}

.task-block-time {
  font-size: 23px;
  color: #fbbf24;
  margin-bottom: 18px;
}

.task-block-list {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-block-list li {
  font-size: 22px;
  color: #cbd5e1;
  line-height: 1.5;
}

.task-block-list strong {
  color: #f1f5f9;
}

/* ── Slide 3 Conditions ── */
.slide-conditions {
  background: #0f172a;
}

.cond-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.cond-card {
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 16px;
  padding: 28px 24px;
  text-align: center;
}

.cond-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.cond-name {
  font-size: 26px;
  font-weight: 700;
  color: #f1f5f9;
  margin-bottom: 14px;
}

.cond-desc {
  font-size: 21px;
  color: #94a3b8;
  line-height: 1.8;
}

.cond-desc strong {
  color: #e2e8f0;
}

/* ── Slide 4 Notes ── */
.slide-notes {
  background: linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%);
}

.notes-list {
  list-style: none;
  padding: 0;
  margin: 0 0 48px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  text-align: left;
  max-width: 760px;
}

.notes-list li {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  background: rgba(255,255,255,0.07);
  border-radius: 14px;
  padding: 18px 24px;
  font-size: 24px;
  color: #cbd5e1;
  line-height: 1.6;
}

.notes-list strong {
  color: #f1f5f9;
}

.notes-icon {
  font-size: 24px;
  flex-shrink: 0;
  margin-top: 2px;
}

.start-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.start-hint {
  font-size: 28px;
  color: #94a3b8;
  margin: 0;
}

.start-btn {
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 16px;
  padding: 20px 64px;
  font-size: 26px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s, transform 0.1s;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.45);
  letter-spacing: 1px;
}

.start-btn:hover {
  background: #1d4ed8;
  transform: translateY(-2px);
}

.start-btn:active {
  transform: translateY(0);
}

/* ── Navigation ── */
.nav-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  padding: 16px;
  background: rgba(0,0,0,0.3);
}

.nav-btn {
  background: rgba(255,255,255,0.1);
  border: none;
  color: #fff;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  font-size: 28px;
  cursor: pointer;
  transition: background 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.nav-btn:hover:not(:disabled) {
  background: rgba(255,255,255,0.2);
}

.nav-btn:disabled {
  opacity: 0.25;
  cursor: default;
}

.nav-dots {
  display: flex;
  gap: 10px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: none;
  background: rgba(255,255,255,0.25);
  cursor: pointer;
  transition: background 0.15s, transform 0.15s;
  padding: 0;
}

.dot.active {
  background: #3b82f6;
  transform: scale(1.4);
}

/* ── Keyboard hint ── */
.key-hint {
  position: fixed;
  bottom: 72px;
  right: 24px;
  font-size: 13px;
  color: rgba(255,255,255,0.2);
  pointer-events: none;
}
</style>
