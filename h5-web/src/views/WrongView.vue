<template>
  <div class="wrong-page safe-bottom">
    <NavBar title="错题解析" />

    <main class="wrong-content">
      <section v-if="wrongStats" class="wrong-summary">
        <div>
          <strong>{{ wrongStats.total_wrong }}</strong>
          <span>未掌握</span>
        </div>
        <div>
          <strong>{{ wrongStats.mastered_count }}</strong>
          <span>已掌握</span>
        </div>
        <div>
          <strong>{{ wrongStats.by_bank.length }}</strong>
          <span>涉及题本</span>
        </div>
      </section>

      <LoadingState v-if="loading" />

      <van-empty v-else-if="!filteredRecords.length" description="暂无错题">
        <template #image>
          <AppIcon name="wrong" :size="80" :stroke-width="1.1" />
        </template>
      </van-empty>

      <template v-else>
        <article
          v-for="(record, idx) in filteredRecords"
          :key="record.id"
          class="mistake-card animate-fade-in"
          :class="`stagger-${Math.min(idx + 1, 5)}`"
          :style="{ '--stagger': idx }"
        >
          <!-- Header -->
          <div class="mistake-header">
            <span class="pill-error">单选题</span>
            <span class="mistake-num">Question {{ idx + 1 }}</span>
            <button
              class="note-chip"
              type="button"
              @pointerdown.prevent="openNotePanel(record.question?.id)"
              @click="openNotePanel(record.question?.id)"
            >
              查看笔记
            </button>
          </div>

          <!-- Stem -->
          <p class="mistake-stem"><MathText :text="record.question?.content" fallback="题目加载中..." /></p>
          <div v-if="imagesFor(record.question, 'stem').length" class="mistake-images">
            <img
              v-for="(image, imageIndex) in imagesFor(record.question, 'stem')"
              :key="`stem-${imageIndex}`"
              :src="image.src"
              :alt="image.caption || '题目图片'"
            />
          </div>
          <div v-if="imagesFor(record.question, 'options').length" class="mistake-images">
            <img
              v-for="(image, imageIndex) in imagesFor(record.question, 'options')"
              :key="`options-${imageIndex}`"
              :src="image.src"
              :alt="image.caption || '选项图片'"
            />
          </div>

          <!-- Answer Comparison -->
          <div class="answer-compare">
            <!-- User's wrong answer -->
            <div class="answer-row answer-wrong">
              <AppIcon name="wrong" :size="18" />
              <div class="answer-row-text">
                <span class="answer-row-opt">
                  <span>{{ record.user_answer }}. </span><MathText :text="optionLabel(record.question, record.user_answer)" fallback="未作答" />
                </span>
                <p class="answer-row-label">你的答案</p>
              </div>
            </div>
            <!-- Correct answer -->
            <div class="answer-row answer-right">
              <AppIcon name="check" :size="18" />
              <div class="answer-row-text">
                <span class="answer-row-opt">
                  <span>{{ record.question?.answer }}. </span><MathText :text="optionLabel(record.question, record.question?.answer)" fallback="未给出" />
                </span>
                <p class="answer-row-label">正确答案</p>
              </div>
            </div>
          </div>

          <!-- Analysis -->
          <div
            v-if="record.question?.analysis || imagesFor(record.question, 'analysis').length || record.question?.analysis_image_url"
            class="analysis-box"
          >
            <div class="analysis-box-header">
              <AppIcon name="spark" :size="16" />
              <span>解析</span>
            </div>
            <p><MathText :text="record.question.analysis" fallback="暂无文字解析" /></p>
            <div v-if="imagesFor(record.question, 'analysis').length" class="mistake-images analysis-images">
              <img
                v-for="(image, imageIndex) in imagesFor(record.question, 'analysis')"
                :key="`analysis-${imageIndex}`"
                :src="image.src"
                :alt="image.caption || '解析图片'"
              />
            </div>
            <img
              v-for="(image, imageIndex) in answerAnalysisImages(record.question)"
              :key="`answer-analysis-${imageIndex}`"
              class="analysis-image"
              :src="image"
              alt="解析图片"
            />
          </div>

          <!-- Knowledge Tags -->
          <div class="knowledge-tags">
            <span v-if="record.question?.bank?.subject" class="tag">{{ record.question.bank.subject }}</span>
            <span class="tag">{{ record.question?.type === 'judge' ? '判断题' : '单选题' }}</span>
          </div>

          <!-- Actions -->
          <div class="mistake-actions">
            <button class="btn-retry" @click="retryQuestion(record)">
              <AppIcon name="practice" :size="16" />
              重做此题
            </button>
            <button
              class="btn-master"
              @pointerdown.prevent="openNotePanel(record.question?.id)"
              @click="openNotePanel(record.question?.id)"
            >
              查看笔记
            </button>
            <button class="btn-master" @click="handleMaster(record.id)">已掌握</button>
          </div>
        </article>
      </template>
    </main>

    <!-- Bottom Actions -->
    <div v-if="records.length" class="bottom-bar safe-panel">
      <button class="btn-outline-lg" @click="handleClear">清空</button>
      <button class="btn-primary-lg" :disabled="retryLoading" @click="retryWrong">
        <span v-if="retryLoading" class="button-spinner" />
        <AppIcon v-else name="practice" :size="18" />
        {{ retryLoading ? '加载中' : '随机练习' }}
      </button>
    </div>

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
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showConfirmDialog, showSuccessToast, showToast } from 'vant';
import { clearWrong, getWrong, getWrongPractice, getWrongStats, masterWrong } from '@/api/record';
import LoadingState from '@/components/LoadingState.vue';
import NavBar from '@/components/NavBar.vue';
import AppIcon from '@/components/AppIcon.vue';
import MathText from '@/components/MathText.vue';
import { useQuizStore } from '@/stores/quiz';
import { normalizeImageSources, questionImagesFor, type QuestionImageSlot } from '@/utils/questionImages';
import { getQuestionNote, saveQuestionNote } from '@/utils/questionNotes';

const router = useRouter();
const quiz = useQuizStore();
const loading = ref(false);
const retryLoading = ref(false);
const records = ref<any[]>([]);
const wrongStats = ref<Awaited<ReturnType<typeof getWrongStats>> | null>(null);
const showNotePanel = ref(false);
const activeNoteQuestionId = ref('');
const noteDraft = ref('');

const filteredRecords = computed(() => records.value);

function optionEntries(question: any) {
  if (!question) return [];
  const direct = question.options && typeof question.options === 'object'
    ? Object.entries(question.options).map(([k, v]) => ({ key: k, value: String(v) }))
    : [];
  if (direct.length) return direct;
  return [
    { key: 'A', value: question.option_a },
    { key: 'B', value: question.option_b },
    { key: 'C', value: question.option_c },
    { key: 'D', value: question.option_d },
  ].filter((o) => o.value).map((o) => ({ key: o.key, value: String(o.value) }));
}

function optionLabel(question: any, key: string) {
  if (!question) return key;
  const entries = optionEntries(question);
  const found = entries.find((e: any) => e.key === key);
  return found ? found.value : key;
}

function imagesFor(question: any, slot: QuestionImageSlot) {
  return questionImagesFor(question?.images, slot, 'stem');
}

function answerAnalysisImages(question: any) {
  const sources = normalizeImageSources([...(question?.analysis_image_urls || []), question?.analysis_image_url]);
  return Array.from(new Set(sources));
}

function openNotePanel(questionId?: string) {
  if (!questionId) {
    showToast('题目加载中，暂时无法查看笔记');
    return;
  }
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

async function fetchWrong() {
  loading.value = true;
  try {
    const [result, stats] = await Promise.all([
      getWrong({ page: 1, pageSize: 100 }),
      getWrongStats().catch(() => null),
    ]);
    records.value = (result as any).list || [];
    wrongStats.value = stats;
  } finally {
    loading.value = false;
  }
}

async function retryWrong() {
  if (retryLoading.value) return;
  retryLoading.value = true;
  try {
    const questions = (await getWrongPractice({ count: 20 })) as any[];
    if (!questions.length) {
      showToast('暂无可练错题');
      return;
    }
    await quiz.startQuiz(questions[0].bank_id, questions);
    await router.push(`/quiz/${questions[0].bank_id}`);
  } finally {
    retryLoading.value = false;
  }
}

async function retryQuestion(record: any) {
  if (!record.question) return;
  const bankId = record.question.bank_id;
  if (!bankId) {
    showToast('题目缺少题库信息');
    return;
  }
  await quiz.startQuiz(bankId, [record.question]);
  await router.push(`/quiz/${bankId}`);
}

async function handleMaster(id: string) {
  await masterWrong(id);
  showSuccessToast('已标记掌握');
  await fetchWrong();
}

async function handleClear() {
  await showConfirmDialog({ title: '清空错题', message: '确认清空当前所有错题？' });
  await clearWrong();
  showSuccessToast('已清空');
  await fetchWrong();
}

onMounted(fetchWrong);
</script>

<style scoped>
.wrong-page {
  min-height: 100dvh;
  background: var(--color-bg);
  padding-bottom: 80px;
}

.wrong-page :deep(.van-overlay) {
  z-index: 80;
}

/* ---- Content ---- */
.wrong-content {
  padding: var(--space-md) var(--space-container);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.wrong-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-sm);
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  box-shadow: var(--shadow-card);
}

.wrong-summary div {
  display: grid;
  gap: 2px;
  text-align: center;
}

.wrong-summary strong {
  color: var(--color-on-surface);
  font-family: var(--font-display);
  font-size: 20px;
}

.wrong-summary span {
  color: var(--color-on-surface-variant);
  font-size: 12px;
}

/* ---- Mistake Card ---- */
.mistake-card {
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  box-shadow: var(--shadow-card);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.mistake-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-sm);
}

.mistake-num {
  font-size: 12px;
  color: var(--color-outline);
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

.mistake-stem {
  font-size: 16px;
  font-weight: 600;
  line-height: 26px;
  color: var(--color-on-surface);
  margin: var(--space-sm) 0;
}

.mistake-images {
  display: grid;
  gap: var(--space-sm);
}

.mistake-images img {
  width: 100%;
  max-height: 220px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-bright);
  object-fit: contain;
}

.analysis-images {
  margin-top: var(--space-sm);
}

/* ---- Answer Compare ---- */
.answer-compare {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.answer-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
}

.answer-wrong {
  background: rgba(186, 26, 26, 0.08);
  border: 1px solid rgba(186, 26, 26, 0.15);
  color: var(--color-error);
}

.answer-right {
  background: rgba(0, 125, 85, 0.06);
  border: 1px solid rgba(0, 125, 85, 0.15);
  color: var(--color-tertiary-container);
}

.answer-row-text {
  flex: 1;
}

.answer-row-opt {
  font-size: 14px;
  color: var(--color-on-surface);
}

.answer-row-label {
  font-size: 11px;
  margin: 2px 0 0;
}

.answer-wrong .answer-row-label { color: var(--color-error); }
.answer-right .answer-row-label { color: var(--color-tertiary-container); }

/* ---- Analysis Box ---- */
.analysis-box {
  padding: var(--space-md);
  border-radius: var(--radius-md);
  background: var(--color-surface-container-lowest);
  border: 1px solid var(--color-surface-container-high);
}

.analysis-box-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-on-surface);
}

.analysis-box-header svg {
  color: var(--color-secondary-container);
}

.analysis-box p {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
  color: var(--color-on-surface-variant);
}

.analysis-image {
  display: block;
  width: 100%;
  margin-top: var(--space-sm);
  border-radius: var(--radius-sm);
  object-fit: contain;
  background: var(--color-surface-bright);
}

/* ---- Tags ---- */
.knowledge-tags {
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

/* ---- Actions ---- */
.mistake-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  padding-top: var(--space-sm);
}

.btn-retry {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-primary-fixed);
  color: var(--color-on-primary-fixed);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn-retry:active { opacity: 0.8; }

.btn-master {
  padding: 8px 16px;
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--color-on-surface-variant);
  font-size: 13px;
  cursor: pointer;
}

.btn-master:active { background: var(--color-surface-container-low); }

/* ---- Bottom Bar ---- */
.bottom-bar {
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
  width: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-sm);
  background: var(--color-surface-container-lowest);
  color: var(--color-on-surface-variant);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
}

.btn-primary-lg {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: 12px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-primary-container);
  color: var(--color-on-primary);
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn-primary-lg:active { transform: scale(0.97); }
.btn-primary-lg:disabled {
  opacity: 0.72;
  transform: none;
}

.button-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: var(--color-on-primary);
  border-radius: var(--radius-full);
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
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
