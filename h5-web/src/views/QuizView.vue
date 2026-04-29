<template>
  <div class="quiz-page">
    <!-- Header -->
    <header class="quiz-header">
      <button class="icon-btn" type="button" aria-label="退出练习" @click="handleBack">
        <AppIcon name="arrow-left" :size="24" />
      </button>
      <h1 class="quiz-title">智能练习</h1>
      <div class="timer-badge">
        <AppIcon name="clock" :size="16" />
        <span>{{ mmss }}</span>
      </div>
    </header>

    <!-- Progress bar -->
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: `${quiz.progress}%` }" />
    </div>

    <LoadingState v-if="quiz.status === 'loading'" />

    <main v-else-if="!question" class="quiz-empty">
      <van-empty description="当前题库暂无可练习题目">
        <template #image>
          <svg width="88" height="88" viewBox="0 0 24 24" fill="none" stroke="var(--color-outline-variant)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
        </template>
        <button class="empty-action" @click="router.replace('/bank')">选择其他题库</button>
      </van-empty>
    </main>

    <main v-else-if="question" class="quiz-body animate-fade-in">
      <!-- Material Card -->
      <section v-if="question.material?.content" class="material-card">
        <div class="material-header">
          <span class="material-icon"><AppIcon name="book" :size="16" /></span>
          <span class="material-label">材料阅读</span>
        </div>
        <p class="material-text">{{ question.material.content }}</p>
        <img
          v-for="(image, index) in materialImages"
          :key="`material-${index}`"
          :src="image.src"
          :alt="image.caption || '材料图片'"
          class="question-image"
          @click="showImagePreview(previewSources(materialImages), index)"
        />
      </section>

      <!-- Question Card -->
      <section class="question-card">
        <div class="question-header">
          <div class="question-meta">
            <span class="pill pill-primary">{{ question.type === 'judge' ? '判断' : '单选' }}</span>
            <span class="question-num">{{ quiz.currentIndex + 1 }} / {{ quiz.questions.length }}</span>
          </div>
        </div>
        <h3 class="question-stem">{{ question.content }}</h3>

        <!-- Images -->
        <img
          v-for="(image, index) in stemImages"
          :key="index"
          :src="image.src"
          :alt="image.caption || '题目图片'"
          class="question-image"
          @click="showImagePreview(previewSources(stemImages), index)"
        />

        <!-- Options -->
        <div v-if="optionImages.length" class="option-image-strip">
          <img
            v-for="(image, index) in optionImages"
            :key="`option-image-${index}`"
            :src="image.src"
            :alt="image.caption || '选项图片'"
            class="question-image"
            @click="showImagePreview(previewSources(optionImages), index)"
          />
        </div>
        <div class="options-list">
          <button
            v-for="option in options"
            :key="option.value"
            class="option-card"
            :class="optionClass(option.value)"
            :disabled="quiz.status === 'submitted'"
            @click="quiz.status === 'answering' && (selectedAnswer = option.value)"
          >
            <span class="option-letter" :class="optionLetterClass(option.value)">{{ option.value }}</span>
            <span class="option-label">{{ option.label }}</span>
            <AppIcon
              v-if="quiz.status === 'submitted' && currentResult?.answer === option.value"
              class="option-icon option-icon-correct"
              name="check"
              :size="20"
              :stroke-width="2.5"
            />
            <AppIcon
              v-else-if="quiz.status === 'submitted' && currentResult?.user_answer === option.value && currentResult?.answer !== option.value"
              class="option-icon option-icon-wrong"
              name="wrong"
              :size="20"
              :stroke-width="2.5"
            />
          </button>
        </div>

        <!-- Analysis -->
        <div v-if="quiz.status === 'submitted'" class="analysis-card">
          <div class="analysis-header">
            <AppIcon name="spark" :size="18" />
            <span>解析详情</span>
            <button class="analysis-note-btn" type="button" @pointerdown.prevent="openNotePanel" @click="openNotePanel">查看笔记</button>
          </div>
          <p class="analysis-answer">正确答案：{{ answerLabel(currentResult?.answer || '') }}</p>
          <p class="analysis-text">{{ currentResult?.analysis || '暂无解析' }}</p>
          <img
            v-for="(image, index) in analysisImages"
            :key="`analysis-image-${index}`"
            class="analysis-image"
            :src="image.src"
            :alt="image.caption || '解析图片'"
            @click="showImagePreview(previewSources(analysisImages), index)"
          />
          <img
            v-for="(image, index) in answerAnalysisImages"
            :key="`answer-analysis-image-${index}`"
            class="analysis-image"
            :src="image"
            alt="解析图片"
            @click="showImagePreview(answerAnalysisImages, index)"
          />
        </div>
      </section>
    </main>

    <!-- Bottom Action Bar -->
    <div v-if="question" class="bottom-bar safe-panel">
      <button class="btn-outline" @click="showAnswerSheet = true">
        <AppIcon name="document" :size="20" />
        <span>答题卡</span>
      </button>
      <button class="btn-outline" @pointerdown.prevent="openNotePanel" @click="openNotePanel">
        <AppIcon name="note" :size="20" />
        <span>笔记</span>
      </button>

      <button v-if="quiz.status === 'answering'" class="btn-primary-wide" :disabled="!selectedAnswer" @click="handleSubmit">
        提交答案
      </button>
      <button v-else class="btn-primary-wide" @click="handleNext">
        <span>{{ quiz.isFinished ? '查看结果' : '下一题' }}</span>
        <AppIcon name="chevron-right" :size="18" />
      </button>
    </div>

    <!-- Answer Sheet Overlay -->
    <van-overlay :show="showAnswerSheet" @click="showAnswerSheet = false">
      <div class="sheet-panel" @click.stop>
        <h3 class="sheet-title">答题卡</h3>
        <div class="sheet-grid">
          <button
            v-for="(q, index) in quiz.questions"
            :key="q.id"
            class="sheet-num"
            :class="{
              'sheet-answered': quiz.answers[q.id]?.user_answer,
              'sheet-current': index === quiz.currentIndex,
            }"
            @click="quiz.goToQuestion(index); showAnswerSheet = false"
          >
            {{ index + 1 }}
          </button>
        </div>
        <button class="btn-primary-wide sheet-close" @click="showAnswerSheet = false">关闭</button>
      </div>
    </van-overlay>

    <div v-if="showNotePanel" class="note-backdrop" @click="showNotePanel = false">
      <div class="note-panel" @click.stop>
        <div class="note-panel-head">
          <h3>题目笔记</h3>
          <button type="button" @click="showNotePanel = false">关闭</button>
        </div>
        <p class="note-hint">笔记保存在本机，换设备后不会同步。</p>
        <textarea v-model="noteDraft" class="note-textarea" placeholder="还没有笔记，可以记录易错点、公式或做题思路。" />
        <button class="btn-primary-wide note-save" type="button" @click="saveCurrentNote">保存笔记</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { showDialog, showImagePreview, showSuccessToast } from 'vant';
import { submitAnswer } from '@/api/record';
import LoadingState from '@/components/LoadingState.vue';
import AppIcon from '@/components/AppIcon.vue';
import { useCountdown } from '@/composables/useCountdown';
import { useSync } from '@/composables/useSync';
import { useQuizStore } from '@/stores/quiz';
import { normalizeImageSources, questionImagesFor, type NormalizedQuestionImage } from '@/utils/questionImages';
import { getQuestionNote, saveQuestionNote } from '@/utils/questionNotes';

const route = useRoute();
const router = useRouter();
const quiz = useQuizStore();
const bankId = String(route.params.bankId);
const selectedAnswer = ref('');
const showAnswerSheet = ref(false);
const showNotePanel = ref(false);
const noteDraft = ref('');
const { saveLocal } = useSync(bankId);

const { timeLeft, start } = useCountdown(30 * 60, async () => {
  await showDialog({ message: '时间到，自动提交' });
  quiz.finishQuiz();
  await router.replace('/result');
});

const question = computed(() => quiz.currentQuestion);
const currentResult = computed(() => (question.value ? quiz.answers[question.value.id] : null));
const answerAnalysisImages = computed(() => {
  const sources = normalizeImageSources([
    ...(currentResult.value?.analysis_image_urls || []),
    currentResult.value?.analysis_image_url,
    ...(question.value?.analysis_image_urls || []),
    question.value?.analysis_image_url,
  ]);
  return Array.from(new Set(sources));
});

const mmss = computed(() => {
  const m = Math.floor(timeLeft.value / 60).toString().padStart(2, '0');
  const s = (timeLeft.value % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
});

const options = computed(() => {
  if (!question.value) return [];
  if (question.value.type === 'judge') {
    return [
      { value: 'T', label: '正确' },
      { value: 'F', label: '错误' },
    ];
  }
  return [
    { value: 'A', label: question.value.option_a || '' },
    { value: 'B', label: question.value.option_b || '' },
    { value: 'C', label: question.value.option_c || '' },
    { value: 'D', label: question.value.option_d || '' },
  ].filter((o) => o.label);
});

const stemImages = computed(() => questionImagesFor(question.value?.images, 'stem', 'stem'));
const optionImages = computed(() => questionImagesFor(question.value?.images, 'options', 'stem'));
const analysisImages = computed(() => questionImagesFor(question.value?.images, 'analysis', 'stem'));

const materialImages = computed(() =>
  questionImagesFor(question.value?.material?.images, 'material', 'material'),
);

watch(question, () => {
  selectedAnswer.value = question.value ? quiz.answers[question.value.id]?.user_answer || '' : '';
  if (showNotePanel.value) noteDraft.value = getQuestionNote(question.value?.id);
});

function optionClass(value: string) {
  if (quiz.status !== 'submitted') {
    return { 'opt-selected': selectedAnswer.value === value };
  }
  return {
    'opt-correct': currentResult.value?.answer === value,
    'opt-wrong': currentResult.value?.user_answer === value && currentResult.value?.answer !== value,
  };
}

function optionLetterClass(value: string) {
  if (quiz.status !== 'submitted') {
    return { 'letter-selected': selectedAnswer.value === value };
  }
  return {
    'letter-correct': currentResult.value?.answer === value,
    'letter-wrong': currentResult.value?.user_answer === value && currentResult.value?.answer !== value,
  };
}

function answerLabel(value: string) {
  if (!question.value) return value;
  if (question.value.type === 'judge') return value === 'T' ? '正确' : value === 'F' ? '错误' : value;
  return value;
}

function previewSources(images: NormalizedQuestionImage[]) {
  return images.map((image) => image.src);
}

function openNotePanel() {
  noteDraft.value = getQuestionNote(question.value?.id);
  showNotePanel.value = true;
}

function saveCurrentNote() {
  if (!question.value) return;
  saveQuestionNote(question.value.id, noteDraft.value);
  showSuccessToast('笔记已保存');
  showNotePanel.value = false;
}

function handleBack() {
  showDialog({ title: '退出练习', message: '退出后当前进度不会保存，确定退出吗？' }).then(() => router.back()).catch(() => {});
}

async function handleSubmit() {
  if (!question.value) return;
  const payload = {
    question_id: question.value.id,
    user_answer: selectedAnswer.value,
    time_spent: Math.floor((Date.now() - quiz.startedAt) / 1000),
  };
  saveLocal(bankId, payload);
  const result = navigator.onLine ? await submitAnswer(payload) : null;
  quiz.submitAnswer({
    ...payload,
    is_correct: result?.is_correct,
    answer: result?.answer || question.value.answer,
    analysis: result?.analysis || question.value.analysis,
    analysis_image_url: result?.analysis_image_url || question.value.analysis_image_url,
    analysis_image_urls: result?.analysis_image_urls || question.value.analysis_image_urls,
  });
}

async function handleNext() {
  if (quiz.isFinished) {
    quiz.finishQuiz();
    await router.replace('/result');
  } else {
    quiz.nextQuestion();
  }
}

onMounted(async () => {
  if (!(quiz.bankId === bankId && quiz.questions.length)) {
    await quiz.startQuiz(bankId);
  }
  if (quiz.questions.length) start();
});
</script>

<style scoped>
.quiz-page {
  min-height: 100dvh;
  background: var(--color-bg);
}

.quiz-page :deep(.van-overlay) {
  z-index: 80;
}

/* ---- Header ---- */
.quiz-header {
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

.quiz-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-primary-container);
  margin: 0;
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
}

.timer-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  background: var(--color-surface-container-low);
  color: var(--color-on-surface);
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
}

/* ---- Progress ---- */
.progress-bar {
  height: 3px;
  background: var(--color-surface-container);
}

.progress-fill {
  height: 100%;
  border-radius: 0 999px 999px 0;
  background: var(--color-primary-container);
  transition: width 0.3s ease;
}

/* ---- Body ---- */
.quiz-body {
  padding: var(--space-md) var(--space-container);
  padding-bottom: 100px;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.quiz-empty {
  min-height: calc(100dvh - 80px);
  display: grid;
  place-items: center;
  padding: var(--space-lg) var(--space-container);
}

.empty-action {
  margin-top: var(--space-md);
  padding: 10px 20px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-primary-container);
  color: var(--color-on-primary);
  font-family: var(--font-display);
  font-weight: 600;
}

/* ---- Material Card ---- */
.material-card {
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  border: 1px solid var(--color-surface-container);
  box-shadow: 0 4px 20px rgba(37, 99, 235, 0.03);
}

.material-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

.material-icon {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: var(--radius-full);
  background: var(--color-primary-fixed);
  color: var(--color-primary-container);
}

.material-label {
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 600;
  color: var(--color-on-surface);
}

.material-text {
  font-size: 16px;
  line-height: 26px;
  color: var(--color-on-surface-variant);
  text-align: justify;
  margin: 0;
}

/* ---- Question Card ---- */
.question-card {
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  border: 1px solid var(--color-surface-container);
  box-shadow: 0 4px 20px rgba(37, 99, 235, 0.03);
}

.question-header {
  margin-bottom: var(--space-md);
}

.question-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.question-num {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-on-surface);
}

.question-stem {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  line-height: 28px;
  color: var(--color-on-surface);
  margin: 0 0 var(--space-md);
}

.question-image {
  width: 100%;
  max-height: 240px;
  object-fit: contain;
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-md);
  background: #fff;
}

.option-image-strip {
  display: grid;
  gap: var(--space-sm);
  margin-bottom: var(--space-sm);
}

/* ---- Options ---- */
.options-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-card-gutter);
}

.option-card {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  width: 100%;
  padding: var(--space-md);
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-md);
  background: var(--color-surface-bright);
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}

.option-card:hover:not(:disabled) {
  border-color: rgba(37, 99, 235, 0.35);
  box-shadow: var(--shadow-card);
}

.option-card:active {
  background: var(--color-surface-container-low);
}

.option-letter {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 2px solid var(--color-outline-variant);
  border-radius: 50%;
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--color-outline-variant);
  flex-shrink: 0;
  transition: all 0.15s;
}

.option-label {
  flex: 1;
  font-size: 16px;
  line-height: 24px;
  color: var(--color-on-surface-variant);
  padding-top: 4px;
}

/* Selected */
.opt-selected {
  border: 2px solid var(--color-primary-container);
  background: var(--color-surface-container-low);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.1);
}
.opt-selected .option-label { color: var(--color-primary-container); font-weight: 500; }
.letter-selected {
  border-color: var(--color-primary-container);
  background: var(--color-primary-container);
  color: var(--color-on-primary);
}

/* Correct */
.opt-correct {
  border: 2px solid var(--color-tertiary-container);
  background: rgba(0, 125, 85, 0.06);
}
.opt-correct .option-label { color: var(--color-tertiary); }
.letter-correct {
  border-color: var(--color-tertiary-container);
  background: var(--color-tertiary-container);
  color: var(--color-on-primary);
}

/* Wrong */
.opt-wrong {
  border: 2px solid var(--color-error);
  background: var(--color-error-container);
}
.opt-wrong .option-label { color: var(--color-on-error-container); }
.letter-wrong {
  border-color: var(--color-error);
  background: var(--color-error);
  color: var(--color-on-error);
}

.option-icon {
  flex-shrink: 0;
  margin-top: 6px;
}
.option-icon-correct { color: var(--color-tertiary-container); }
.option-icon-wrong { color: var(--color-error); }

/* ---- Analysis ---- */
.analysis-card {
  margin-top: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-md);
  background: linear-gradient(180deg, var(--color-primary-fixed), var(--color-surface-container-lowest));
  border: 1px solid var(--color-primary-fixed-dim);
}

.analysis-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding-bottom: var(--space-sm);
  margin-bottom: var(--space-sm);
  border-bottom: 1px solid var(--color-primary-fixed-dim);
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-on-primary-fixed-variant);
}

.analysis-header svg {
  color: var(--color-secondary-container);
}

.analysis-note-btn {
  margin-left: auto;
  border: 1px solid var(--color-primary-fixed-dim);
  border-radius: var(--radius-full);
  background: var(--color-surface-container-lowest);
  color: var(--color-primary-container);
  cursor: pointer;
  font-size: 12px;
  padding: 4px 10px;
}

.analysis-answer {
  font-weight: 700;
  color: var(--color-on-primary-fixed-variant);
  margin: 0 0 4px;
}

.analysis-text {
  font-size: 14px;
  line-height: 22px;
  color: var(--color-on-surface-variant);
  margin: 0;
}

.analysis-image {
  display: block;
  width: 100%;
  margin-top: 12px;
  border-radius: 8px;
  object-fit: contain;
  background: var(--color-surface-bright);
}

/* ---- Bottom Bar ---- */
.bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  max-width: 750px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: 12px var(--space-container) calc(12px + env(safe-area-inset-bottom));
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  z-index: 50;
}

.btn-outline {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-on-surface-variant);
  font-size: 12px;
  cursor: pointer;
}

.btn-outline:active { color: var(--color-primary-container); }

.btn-primary-wide {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: 14px 24px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-primary-container);
  color: var(--color-on-primary);
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
  transition: all 0.2s;
}

.btn-primary-wide:active { transform: scale(0.97); }
.btn-primary-wide:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ---- Answer Sheet ---- */
.sheet-panel {
  position: fixed;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 750px;
  padding: 24px var(--space-container) calc(24px + env(safe-area-inset-bottom));
  border-radius: 24px 24px 0 0;
  background: var(--color-surface-container-lowest);
}

.sheet-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-on-surface);
  margin: 0 0 var(--space-md);
  text-align: center;
}

.sheet-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}

.sheet-num {
  width: 100%;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  border: 1px solid var(--color-outline-variant);
  border-radius: 50%;
  background: var(--color-surface-bright);
  color: var(--color-outline);
  font-family: var(--font-display);
  font-size: 14px;
  cursor: pointer;
}

.sheet-answered {
  border-color: var(--color-primary-container);
  background: var(--color-primary-fixed);
  color: var(--color-on-primary-fixed-variant);
}

.sheet-current {
  border-color: var(--color-secondary-container);
  background: var(--color-secondary-fixed);
  color: var(--color-on-secondary-fixed-variant);
}

.sheet-close {
  width: 100%;
}

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
  gap: var(--space-md);
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
}
</style>
