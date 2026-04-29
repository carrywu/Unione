<template>
  <div class="analysis-page">
    <!-- TopAppBar -->
    <header class="top-bar">
      <button class="icon-btn" @click="router.back()">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5m7-7-7 7 7 7"/></svg>
      </button>
      <h1 class="top-title">全部解析</h1>
      <span class="top-spacer" />
    </header>

    <main class="analysis-content">
      <van-empty v-if="!allQuestions.length" description="暂无答题记录">
        <template #image>
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="var(--color-outline-variant)" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </template>
      </van-empty>

      <template v-else>
        <article
          v-for="(item, idx) in allQuestions"
          :key="item.question.id"
          class="analysis-card animate-fade-in"
          :class="[`stagger-${Math.min(idx + 1, 5)}`, item.isCorrect ? 'card-correct' : 'card-wrong']"
        >
          <!-- Header Row -->
          <div class="card-header">
            <div class="card-header-left">
              <span class="card-qnum">Q{{ idx + 1 }}.</span>
              <span v-if="item.isCorrect" class="badge-correct">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                正确
              </span>
              <span v-else class="badge-wrong">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                错误
              </span>
            </div>
            <button
              class="note-chip"
              type="button"
              @pointerdown.prevent="openNotePanel(item.question.id)"
              @click="openNotePanel(item.question.id)"
            >
              查看笔记
            </button>
            <!-- Difficulty stars -->
            <div class="stars" :aria-label="`Difficulty: ${item.difficulty} out of 5`">
              <svg v-for="s in 5" :key="s" width="16" height="16" viewBox="0 0 24 24" :fill="s <= item.difficulty ? 'var(--color-secondary-container)' : 'none'" :stroke="s <= item.difficulty ? 'var(--color-secondary-container)' : 'var(--color-outline-variant)'" stroke-width="1.5"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            </div>
          </div>

          <!-- Question stem -->
          <p class="card-stem">{{ item.question.content }}</p>
          <div v-if="imagesFor(item.question, 'stem').length" class="card-images">
            <img
              v-for="(image, imageIndex) in imagesFor(item.question, 'stem')"
              :key="`stem-${imageIndex}`"
              :src="image.src"
              :alt="image.caption || '题目图片'"
            />
          </div>
          <div v-if="imagesFor(item.question, 'options').length" class="card-images">
            <img
              v-for="(image, imageIndex) in imagesFor(item.question, 'options')"
              :key="`options-${imageIndex}`"
              :src="image.src"
              :alt="image.caption || '选项图片'"
            />
          </div>

          <!-- Answer Comparison -->
          <div :class="['answer-compare', item.isCorrect ? 'compare-correct' : 'compare-wrong']">
            <div class="compare-row">
              <span class="compare-label">你的答案</span>
              <span :class="['compare-value', item.isCorrect ? 'text-correct' : 'text-wrong']">{{ item.userAnswer }}. {{ item.userAnswerLabel }}</span>
            </div>
            <div class="compare-divider" />
            <div class="compare-row compare-row-right">
              <span class="compare-label">正确答案</span>
              <span class="compare-value text-primary">{{ item.answer }}. {{ item.answerLabel }}</span>
            </div>
          </div>

          <!-- Detailed Explanation -->
          <div
            v-if="item.analysis || imagesFor(item.question, 'analysis').length || item.question.analysis_image_url"
            class="explanation-box"
          >
            <h4 class="explanation-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-primary-container)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
              解析
            </h4>
            <div v-if="imagesFor(item.question, 'analysis').length" class="card-images explanation-images">
              <img
                v-for="(image, imageIndex) in imagesFor(item.question, 'analysis')"
                :key="`analysis-${imageIndex}`"
                :src="image.src"
                :alt="image.caption || '解析图片'"
              />
            </div>
            <img
              v-for="(image, imageIndex) in answerAnalysisImages(item.question)"
              :key="`answer-analysis-${imageIndex}`"
              class="explanation-image"
              :src="image"
              alt="解析图片"
            />
            <p class="explanation-text">{{ item.analysis || '暂无文字解析' }}</p>
          </div>

          <!-- Knowledge Tags -->
          <div class="tag-row">
            <span v-if="item.question.bank?.subject" class="tag">{{ item.question.bank.subject }}</span>
            <span class="tag">{{ item.question.type === 'judge' ? '判断题' : '单选题' }}</span>
          </div>
        </article>
      </template>
    </main>

    <!-- Bottom Nav -->
    <nav class="bottom-nav">
      <button class="nav-btn" @click="router.push('/')">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        <span>练习</span>
      </button>
      <button class="nav-btn" @click="router.push('/bank')">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/></svg>
        <span>题库</span>
      </button>
      <button class="nav-btn active">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
        <span>解析</span>
      </button>
      <button class="nav-btn" @click="router.push('/wrong')">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        <span>错题</span>
      </button>
    </nav>

    <div v-if="showNotePanel" class="note-backdrop" @click="showNotePanel = false">
      <div class="note-panel" @click.stop>
        <div class="note-panel-head">
          <h3>题目笔记</h3>
          <button type="button" @click="showNotePanel = false">关闭</button>
        </div>
        <p class="note-hint">笔记保存在本机，换设备后不会同步。</p>
        <textarea v-model="noteDraft" class="note-textarea" placeholder="还没有笔记，可以记录易错点、公式或做题思路。" />
        <button class="note-save" type="button" @click="saveCurrentNote">保存笔记</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showSuccessToast } from 'vant';
import { useQuizStore } from '@/stores/quiz';
import { normalizeImageSources, questionImagesFor, type QuestionImageSlot } from '@/utils/questionImages';
import { getQuestionNote, saveQuestionNote } from '@/utils/questionNotes';

const router = useRouter();
const quiz = useQuizStore();
const showNotePanel = ref(false);
const activeNoteQuestionId = ref('');
const noteDraft = ref('');

interface AnalysisItem {
  question: any;
  isCorrect: boolean;
  userAnswer: string;
  userAnswerLabel: string;
  answer: string;
  answerLabel: string;
  analysis: string;
  difficulty: number;
}

function optionLabel(question: any, key: string): string {
  if (!question || !key) return key;
  if (question.type === 'judge') {
    return key === 'T' ? '正确' : key === 'F' ? '错误' : key;
  }
  const map: Record<string, string | undefined> = {
    A: question.option_a, B: question.option_b,
    C: question.option_c, D: question.option_d,
  };
  return map[key] || key;
}

function difficultyStars(question: any): number {
  if (question.difficulty !== undefined) return question.difficulty;
  // fallback: hash-based pseudo-random 2-5
  const h = (question.id || '').split('').reduce((s: number, c: string) => s + c.charCodeAt(0), 0);
  return 2 + (h % 4);
}

function imagesFor(question: any, slot: QuestionImageSlot) {
  return questionImagesFor(question?.images, slot, 'stem');
}

function answerAnalysisImages(question: any) {
  const sources = normalizeImageSources([...(question?.analysis_image_urls || []), question?.analysis_image_url]);
  return Array.from(new Set(sources));
}

function openNotePanel(questionId: string) {
  activeNoteQuestionId.value = questionId;
  noteDraft.value = getQuestionNote(questionId);
  showNotePanel.value = true;
}

function saveCurrentNote() {
  if (!activeNoteQuestionId.value) return;
  saveQuestionNote(activeNoteQuestionId.value, noteDraft.value);
  showSuccessToast('笔记已保存');
  showNotePanel.value = false;
}

const allQuestions = computed<AnalysisItem[]>(() =>
  quiz.questions.map((q) => {
    const record = quiz.answers[q.id];
    const correctAnswer = record?.answer || q.answer || '';
    const userAnswer = record?.user_answer || '';
    return {
      question: q,
      isCorrect: record?.is_correct === true || userAnswer === correctAnswer,
      userAnswer,
      userAnswerLabel: optionLabel(q, userAnswer),
      answer: correctAnswer,
      answerLabel: optionLabel(q, correctAnswer),
      analysis: record?.analysis || q.analysis || '',
      difficulty: difficultyStars(q),
    };
  }),
);
</script>

<style scoped>
.analysis-page {
  min-height: 100dvh;
  background: var(--color-bg);
  padding-bottom: 80px;
}

.analysis-page :deep(.van-overlay) {
  z-index: 80;
}

/* ---- Top Bar ---- */
.top-bar {
  position: sticky;
  top: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--space-container);
  background: var(--color-surface-container-lowest);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.top-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-primary-container);
}

.icon-btn {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border: none;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--color-primary-container);
  cursor: pointer;
  transition: background 0.15s;
}
.icon-btn:active { background: var(--color-surface-container); }

.top-spacer {
  width: 36px;
  height: 36px;
}

/* ---- Content ---- */
.analysis-content {
  padding: var(--space-md) var(--space-container);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  max-width: 480px;
  margin: 0 auto;
}

/* ---- Analysis Card ---- */
.analysis-card {
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  box-shadow: var(--shadow-card);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.card-wrong {
  position: relative;
  overflow: hidden;
  box-shadow: var(--shadow-card-hover);
}
.card-wrong::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--color-error);
  border-radius: 0 2px 2px 0;
}

/* ---- Card Header ---- */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-sm);
}

.card-header-left {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.card-qnum {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-on-surface);
}

.badge-correct {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  background: rgba(0, 125, 85, 0.1);
  color: var(--color-tertiary-container);
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: 500;
}

.badge-wrong {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 10px;
  border-radius: var(--radius-full);
  background: var(--color-error-container);
  color: var(--color-on-error-container);
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: 500;
}

.stars {
  display: flex;
  gap: 1px;
}

.note-chip {
  margin-left: auto;
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-full);
  background: var(--color-surface-bright);
  color: var(--color-primary-container);
  cursor: pointer;
  flex: 0 0 auto;
  font-size: 12px;
  padding: 4px 10px;
}

/* ---- Stem ---- */
.card-stem {
  font-size: 16px;
  font-weight: 600;
  line-height: 26px;
  color: var(--color-on-surface);
  margin: var(--space-sm) 0;
}

.card-images {
  display: grid;
  gap: var(--space-sm);
}

.card-images img,
.explanation-image {
  width: 100%;
  max-height: 220px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-bright);
  object-fit: contain;
}

.explanation-images,
.explanation-image {
  margin-bottom: var(--space-sm);
}

/* ---- Answer Compare ---- */
.answer-compare {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
}

.compare-correct {
  background: var(--color-surface-bright);
  border: 1px solid var(--color-outline-variant);
}
.compare-correct .compare-value { font-weight: 500; }

.compare-wrong {
  background: rgba(186, 26, 26, 0.06);
  border: 1px solid var(--color-error-container);
}

.compare-row {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.compare-row-right {
  text-align: right;
}

.compare-label {
  font-size: 12px;
  color: var(--color-on-surface-variant);
}

.compare-value {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  margin-top: 2px;
}

.text-correct { color: var(--color-tertiary-container); }
.text-wrong { color: var(--color-error); }
.text-primary { color: var(--color-primary-container); }

.compare-divider {
  width: 1px;
  height: 32px;
  background: var(--color-outline-variant);
  opacity: 0.4;
}

/* ---- Explanation ---- */
.explanation-box {
  padding-top: var(--space-sm);
  border-top: 1px solid var(--color-surface-variant);
}

.explanation-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-on-surface);
  margin: 0 0 6px;
}

.explanation-text {
  font-size: 14px;
  line-height: 22px;
  color: var(--color-on-surface-variant);
  margin: 0;
}

/* ---- Tags ---- */
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--color-surface-variant);
}

.tag {
  padding: 2px 10px;
  border-radius: var(--radius-full);
  background: var(--color-surface-variant);
  font-size: 12px;
  color: var(--color-on-surface);
}

/* ---- Bottom Nav ---- */
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  max-width: 750px;
  margin: 0 auto;
  display: flex;
  justify-content: space-around;
  align-items: center;
  height: 64px;
  padding: 0 8px calc(8px + env(safe-area-inset-bottom));
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  z-index: 50;
}

.nav-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 16px;
  border: none;
  border-radius: var(--radius-xl);
  background: transparent;
  color: var(--color-outline);
  cursor: pointer;
  transition: all 0.2s;
  font-family: var(--font-display);
  font-size: 10px;
  font-weight: 500;
}

.nav-btn.active {
  color: var(--color-primary-container);
  background: rgba(37, 99, 235, 0.08);
}
.nav-btn:active { transform: scale(0.95); }

.note-panel {
  position: fixed;
  bottom: 0;
  left: 50%;
  width: 100%;
  max-width: 750px;
  transform: translateX(-50%);
  border-radius: 24px 24px 0 0;
  background: var(--color-surface-container-lowest);
  padding: 20px var(--space-container) calc(20px + env(safe-area-inset-bottom));
}

.note-backdrop {
  position: fixed;
  inset: 0;
  z-index: 90;
  background: rgba(17, 24, 39, 0.42);
}

.note-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.note-panel-head h3 {
  margin: 0;
  color: var(--color-on-surface);
  font-family: var(--font-display);
  font-size: 18px;
}

.note-panel-head button {
  border: 0;
  background: transparent;
  color: var(--color-primary-container);
  font-size: 14px;
}

.note-hint {
  margin: 8px 0 12px;
  color: var(--color-on-surface-variant);
  font-size: 12px;
}

.note-textarea {
  width: 100%;
  min-height: 160px;
  resize: vertical;
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-md);
  background: var(--color-surface-bright);
  color: var(--color-on-surface);
  font: inherit;
  line-height: 1.6;
  padding: 12px;
}

.note-save {
  width: 100%;
  margin-top: 12px;
  border: 0;
  border-radius: var(--radius-full);
  background: var(--color-primary-container);
  color: var(--color-on-primary);
  cursor: pointer;
  font-family: var(--font-display);
  font-size: 14px;
  padding: 14px 24px;
}
</style>
