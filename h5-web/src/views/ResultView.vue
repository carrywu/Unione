<template>
  <div class="result-page">
    <NavBar title="练习报告" />

    <main class="result-content animate-fade-in">
      <!-- Score Ring -->
      <section class="card score-card">
        <div class="ring-wrap">
          <div class="ring-chart">
            <svg viewBox="0 0 36 36">
              <path class="ring-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
              <path class="ring-fill" :stroke-dasharray="`${accuracy}, 100`" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
            </svg>
            <div class="ring-center">
              <span class="ring-label">答对</span>
              <span class="ring-value">{{ correct }}<small>/{{ total }}</small></span>
            </div>
          </div>
        </div>

        <div class="score-meta">
          <div class="meta-row">
            <span class="meta-key">练习类型</span>
            <span class="meta-val">专项智能练习</span>
          </div>
          <div class="meta-row">
            <span class="meta-key">难度</span>
            <div class="stars">
              <svg v-for="i in 5" :key="i" width="16" height="16" viewBox="0 0 24 24" :fill="i <= 3 ? 'var(--color-secondary-container)' : 'none'" :stroke="i <= 3 ? 'var(--color-secondary-container)' : 'var(--color-outline-variant)'" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              <span class="meta-val">4.3</span>
            </div>
          </div>
          <div class="meta-row">
            <span class="meta-key">交卷时间</span>
            <span class="meta-val">{{ submitTime }}</span>
          </div>
        </div>
      </section>

      <!-- Exam Stats -->
      <section class="card stats-card">
        <div class="section-heading">
          <span class="section-title">考试情况</span>
        </div>
        <div class="stats-grid-5">
          <div class="stat-item">
            <span class="stat-label">一共</span>
            <span class="stat-num">{{ total }}<small>题</small></span>
          </div>
          <div class="stat-item">
            <span class="stat-label">答对</span>
            <span class="stat-num stat-green">{{ correct }}<small>题</small></span>
          </div>
          <div class="stat-item">
            <span class="stat-label">答错</span>
            <span class="stat-num stat-red">{{ wrong }}<small>题</small></span>
          </div>
          <div class="stat-item">
            <span class="stat-label">未答</span>
            <span class="stat-num stat-gray">{{ unanswered }}<small>题</small></span>
          </div>
          <div class="stat-item">
            <span class="stat-label">总用时</span>
            <span class="stat-num">{{ timeUsed }}<small>分</small></span>
          </div>
        </div>
      </section>

      <!-- Answer Key -->
      <section class="card answer-key-card">
        <div class="answer-key-header">
          <div class="section-heading" style="margin-bottom:0">
            <span class="section-title">答题情况</span>
          </div>
          <span class="answer-key-total">共 {{ total }} 题</span>
        </div>
        <div class="answer-grid">
          <div
            v-for="(q, index) in quiz.questions"
            :key="q.id"
            class="answer-num"
            :class="answerClass(q.id)"
          >
            {{ index + 1 }}
          </div>
        </div>
      </section>

      <section class="card ai-card">
        <div class="ai-header">
          <AppIcon name="spark" :size="22" />
          <span class="section-title">练习建议</span>
        </div>
        <div class="ai-bubble">
          <div class="ai-avatar">
            <AppIcon name="target" :size="24" :stroke-width="1.6" />
          </div>
          <div class="ai-text">
            <p>{{ practiceAdvice }}</p>
          </div>
        </div>
      </section>

      <!-- Action Buttons -->
      <div class="result-actions safe-panel">
        <button class="btn-outline-lg" @click="router.push('/analysis')">
          <AppIcon name="book" :size="20" />
          全部解析
        </button>
        <button class="btn-primary-lg" @click="router.replace(`/quiz/${quiz.bankId}`)">
          <AppIcon name="practice" :size="20" />
          再练一次
        </button>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import NavBar from '@/components/NavBar.vue';
import AppIcon from '@/components/AppIcon.vue';
import { useQuizStore } from '@/stores/quiz';

const router = useRouter();
const quiz = useQuizStore();

const total = computed(() => quiz.questions.length);
const correct = computed(() => quiz.correctCount);
const wrong = computed(() => quiz.wrongAnswers.length);
const unanswered = computed(() => total.value - correct.value - wrong.value);
const accuracy = computed(() => (total.value ? Math.round((correct.value / total.value) * 100) : 0));
const timeUsed = computed(() => Math.max(1, Math.floor((Date.now() - quiz.startedAt) / 60000)));
const practiceAdvice = computed(() => {
  if (!total.value) return '先完成一组练习，再查看针对性的复盘建议。';
  if (accuracy.value >= 85) return '本组正确率较高，可以继续提高速度，并复盘耗时最长的题目。';
  if (wrong.value > 0) return `本组错了 ${wrong.value} 题，建议先看全部解析，再从错题本重做一遍。`;
  return '本组已完成，建议继续保持每日练习节奏。';
});
const submitTime = computed(() => {
  const d = new Date();
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
});

function answerClass(questionId: string) {
  const answer = quiz.answers[questionId];
  if (!answer?.user_answer) return 'ans-unanswered';
  return answer.is_correct || answer.user_answer === answer.answer ? 'ans-correct' : 'ans-wrong';
}
</script>

<style scoped>
.result-page {
  min-height: 100dvh;
  background: var(--color-bg);
}

.result-content {
  padding: var(--space-md) var(--space-container);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding-bottom: 100px;
}

/* ---- Score Card ---- */
.score-card {
  padding: var(--space-lg) var(--space-md);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.ring-wrap {
  margin-bottom: var(--space-md);
}

.ring-chart {
  position: relative;
  width: 120px;
  height: 120px;
}

.ring-chart svg { width: 100%; height: 100%; transform: rotate(-90deg); }

.ring-bg {
  fill: none;
  stroke: var(--color-surface-container);
  stroke-width: 3.8;
}

.ring-fill {
  fill: none;
  stroke: var(--color-primary-container);
  stroke-width: 3.8;
  stroke-linecap: round;
  transition: stroke-dasharray 0.6s ease;
}

.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.ring-label {
  font-size: 14px;
  color: var(--color-on-surface-variant);
}

.ring-value {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--color-primary-container);
}

.ring-value small {
  font-size: 14px;
  font-weight: 400;
  color: var(--color-on-surface-variant);
}

.score-meta {
  width: 100%;
  padding: var(--space-md);
  border-radius: var(--radius-sm);
  background: var(--color-surface-container-low);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.meta-key {
  font-size: 14px;
  color: var(--color-on-surface-variant);
}

.meta-val {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-on-surface);
}

.stars { display: flex; align-items: center; gap: 2px; }

/* ---- Stats Grid ---- */
.stats-card {
  padding: var(--space-md);
}

.stats-grid-5 {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--space-sm);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: var(--space-sm);
  border-radius: var(--radius-sm);
  background: var(--color-surface-bright);
  border: 1px solid var(--color-surface-container);
}

.stat-label {
  font-size: 12px;
  color: var(--color-on-surface-variant);
}

.stat-num {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--color-on-surface);
}

.stat-num small {
  font-size: 12px;
  font-weight: 400;
}

.stat-green { color: var(--color-tertiary-container); }
.stat-red { color: var(--color-error); }
.stat-gray { color: var(--color-outline); }

/* ---- Answer Key ---- */
.answer-key-card {
  padding: var(--space-md);
}

.answer-key-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}

.answer-key-total {
  font-size: 14px;
  color: var(--color-on-surface-variant);
}

.answer-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--space-card-gutter);
  justify-items: center;
}

.answer-num {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
}

.ans-correct {
  border: 1px solid var(--color-tertiary-container);
  background: rgba(0, 125, 85, 0.1);
  color: var(--color-tertiary-container);
}

.ans-wrong {
  border: 1px solid var(--color-error);
  background: var(--color-error-container);
  color: var(--color-error);
}

.ans-unanswered {
  border: 1px solid var(--color-outline-variant);
  background: var(--color-surface-bright);
  color: var(--color-outline);
}

/* ---- AI Card ---- */
.ai-card {
  padding: var(--space-md);
  position: relative;
  overflow: hidden;
}

.ai-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

.ai-bubble {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
}

.ai-avatar {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--color-primary-fixed);
  flex-shrink: 0;
}

.ai-text {
  flex: 1;
  padding: var(--space-md);
  border-radius: var(--radius-sm);
  background: var(--color-surface-container-low);
}

.ai-text p {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--color-on-surface);
}

.ai-text strong {
  color: var(--color-primary-container);
  font-weight: 600;
}

/* ---- Bottom Actions ---- */
.result-actions {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  max-width: 750px;
  margin: 0 auto;
  display: flex;
  gap: var(--space-sm);
  padding: 12px var(--space-container) calc(12px + env(safe-area-inset-bottom));
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.btn-outline-lg {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: 14px 16px;
  border: 1px solid var(--color-primary-container);
  border-radius: var(--radius-full);
  background: var(--color-surface-container-lowest);
  color: var(--color-primary-container);
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn-outline-lg:active { transform: scale(0.97); }

.btn-primary-lg {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: 14px 16px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-primary-container);
  color: var(--color-on-primary);
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn-primary-lg:active { transform: scale(0.97); }

/* ---- Shared ---- */
.card {
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  box-shadow: var(--shadow-card);
}
</style>
