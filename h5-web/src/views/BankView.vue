<template>
  <div class="bank-page safe-bottom">
    <NavBar title="题库" :back="false">
      <template #right>
        <button class="icon-btn" type="button" aria-label="我的" @click="router.push('/profile')">
          <AppIcon name="user" :size="22" />
        </button>
      </template>
    </NavBar>

    <LoadingState v-if="loading" />

    <main v-else class="bank-content animate-fade-in">
      <!-- Search Bar -->
      <div class="search-wrap container-pad">
        <div class="search-bar">
          <AppIcon name="search" :size="20" />
          <input v-model="searchText" class="search-input" type="text" placeholder="搜索题目或考点" />
        </div>
      </div>

      <div class="daily-card container-pad">
        <div class="daily-inner">
          <div class="daily-text">
            <div class="daily-heading">
              <AppIcon name="clock" :size="20" />
              <h2 class="daily-title">今日练习</h2>
            </div>
            <p class="daily-desc">今天已完成 {{ stats.today_answered || 0 }} 题</p>
          </div>
          <button class="btn-primary" :disabled="!firstBankId" @click="startBank(firstBankId)">去练习</button>
        </div>
      </div>

      <section class="bank-overview container-pad">
        <div class="overview-card">
          <div>
            <span class="overview-kicker">Question Bank</span>
            <h2>按科目挑题本</h2>
          </div>
          <div class="overview-stats">
            <span>{{ filteredBanks.length }} 本</span>
            <span>{{ totalQuestions }} 题</span>
          </div>
        </div>
        <div class="subject-chips" role="list" aria-label="科目筛选">
          <button class="subject-chip" :class="{ active: !activeSubject }" @click="activeSubject = ''">全部</button>
          <button
            v-for="subject in xcSubjects"
            :key="subject.name"
            class="subject-chip"
            :class="{ active: activeSubject === subject.name }"
            @click="activeSubject = activeSubject === subject.name ? '' : subject.name"
          >
            {{ subject.name }}
          </button>
        </div>
      </section>

      <!-- Subject Categories Grid -->
      <section class="subject-section container-pad">
        <div class="section-heading">
          <span class="section-title">行测题库</span>
        </div>
        <div class="subject-grid-2col">
          <button
            v-for="subject in filteredSubjects"
            :key="subject.name"
            class="subject-card card"
            :class="{ 'subject-wide': subject.wide }"
            @click="startBank(subject.bankId)"
          >
            <div class="subject-icon-sm" :style="{ background: subject.bg, color: subject.color }">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="subject.icon" />
            </div>
            <div class="subject-text">
              <h3 class="subject-name">{{ subject.name }}</h3>
              <p class="subject-count">{{ subject.count }} 题</p>
            </div>
            <svg v-if="subject.wide" class="subject-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-outline-variant)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
          </button>
        </div>
      </section>

      <section class="subject-section container-pad">
        <div class="section-heading">
          <span class="section-title">全部题本</span>
        </div>
        <div class="essay-list">
          <div
            v-for="bank in filteredBanks"
            :key="bank.id"
            class="essay-card card"
            role="button"
            tabindex="0"
            @click="startBank(bank.id)"
            @keyup.enter="startBank(bank.id)"
          >
            <div class="essay-avatar essay-avatar-blue">
              <AppIcon name="document" :size="22" />
            </div>
            <div class="essay-info">
              <span class="essay-name">{{ bank.name }}</span>
              <span class="essay-meta">{{ bank.subject }} · {{ bank.year || '-' }} · {{ bank.total_count || 0 }} 题</span>
            </div>
            <button
              class="select-book-btn"
              :disabled="selectingBookId === bank.id"
              :class="{ selected: selectedBookIds.includes(bank.id) }"
              @click.stop="toggleBook(bank.id)"
            >
              {{ selectingBookId === bank.id ? '...' : selectedBookIds.includes(bank.id) ? '已选' : '选择' }}
            </button>
            <AppIcon class="essay-arrow" name="chevron-right" :size="16" />
          </div>
          <van-empty v-if="!filteredBanks.length" description="暂无匹配题本" />
        </div>
      </section>
    </main>

    <BottomNavBar />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showToast } from 'vant';
import { getBanks, type Bank } from '@/api/bank';
import { getQuestionBooks, selectQuestionBooks } from '@/api/auth';
import { getStats, getWrongPractice } from '@/api/record';
import LoadingState from '@/components/LoadingState.vue';
import NavBar from '@/components/NavBar.vue';
import BottomNavBar from '@/components/BottomNavBar.vue';
import { useQuizStore } from '@/stores/quiz';
import AppIcon from '@/components/AppIcon.vue';

const router = useRouter();
const quiz = useQuizStore();
const loading = ref(false);
const searchText = ref('');
const activeSubject = ref('');
const banks = ref<Bank[]>([]);
const stats = ref({ today_answered: 0 });
const selectedBookIds = ref<string[]>([]);
const selectingBookId = ref('');
const firstBankId = computed(() => banks.value.find((bank) => bank.total_count > 0)?.id || banks.value[0]?.id || '');

const subjectConfig: Record<string, { icon: string; bg: string; color: string; wide?: boolean }> = {
  '言语理解': { icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>', bg: '#dbe1ff', color: '#004ac6' },
  '判断推理': { icon: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>', bg: '#bdffdb', color: '#006242' },
  '数量关系': { icon: '<rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="12" y2="14"/>', bg: '#ffdcc5', color: '#944a00' },
  '资料分析': { icon: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>', bg: '#dbe1ff', color: '#004ac6' },
  '常识判断': { icon: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>', bg: '#e5eeff', color: '#434655', wide: true },
  default: { icon: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>', bg: '#e5eeff', color: '#434655' },
};

const xcSubjects = computed(() => {
  const map = new Map<string, { count: number; bankId: string }>();
  banks.value.forEach((b) => {
    if (!map.has(b.subject)) map.set(b.subject, { count: 0, bankId: b.id });
    map.get(b.subject)!.count += b.total_count || 0;
  });
  return Array.from(map.entries()).map(([name, data]) => ({
    name,
    count: data.count,
    bankId: data.bankId,
    ...(subjectConfig[name] || subjectConfig.default),
  }));
});

const filteredBanks = computed(() => {
  const keyword = searchText.value.trim().toLowerCase();
  return banks.value.filter((bank) => {
    if (activeSubject.value && bank.subject !== activeSubject.value) return false;
    if (!keyword) return true;
    return [bank.name, bank.subject, bank.source, String(bank.year || '')]
      .filter(Boolean)
      .some((text) => String(text).toLowerCase().includes(keyword));
  });
});

const totalQuestions = computed(() => filteredBanks.value.reduce((sum, bank) => sum + Number(bank.total_count || 0), 0));

const filteredSubjects = computed(() => {
  const allowedSubjects = new Set(filteredBanks.value.map((bank) => bank.subject));
  return xcSubjects.value.filter((subject) => allowedSubjects.has(subject.name));
});

function startBank(bankId?: string) {
  if (!bankId) return;
  void router.push(`/quiz/${bankId}`);
}

async function retryWrong() {
  const questions = (await getWrongPractice({ count: 20 }).catch(() => [])) as any[];
  if (!questions.length) {
    showToast('暂无错题，已为你打开题库练习');
    if (firstBankId.value) startBank(firstBankId.value);
    return;
  }
  await quiz.startQuiz(questions[0].bank_id, questions);
  await router.push(`/quiz/${questions[0].bank_id}`);
}

async function toggleBook(bankId: string) {
  if (selectingBookId.value) return;
  selectingBookId.value = bankId;
  const next = selectedBookIds.value.includes(bankId)
    ? selectedBookIds.value.filter((id) => id !== bankId)
    : [...selectedBookIds.value, bankId];
  try {
    const books = await selectQuestionBooks(next);
    selectedBookIds.value = books.map((book) => book.id);
    showToast(selectedBookIds.value.includes(bankId) ? '已加入我的题本' : '已取消选择');
  } finally {
    selectingBookId.value = '';
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    const [bankResult, statsResult, selectedBooks] = await Promise.all([
      getBanks({ page: 1, pageSize: 100 }),
      getStats().catch(() => null),
      getQuestionBooks().catch(() => []),
    ]);
    banks.value = bankResult.list || [];
    if (statsResult) stats.value = statsResult as any;
    selectedBookIds.value = selectedBooks.map((book) => book.id);
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.bank-page {
  padding-bottom: 80px;
}

.bank-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding-top: var(--space-md);
  padding-bottom: var(--space-md);
}

/* ---- Search ---- */
.search-wrap {
  margin-bottom: 0;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  height: 44px;
  padding: 0 var(--space-md);
  border-radius: var(--radius-full);
  background: var(--color-surface-container-lowest);
  border: 1px solid rgba(195, 198, 215, 0.3);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.03);
  color: var(--color-outline);
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-family: var(--font-body);
  font-size: 14px;
  color: var(--color-on-surface);
}

.search-input::placeholder {
  color: var(--color-outline);
}

/* ---- Daily Card ---- */
.daily-inner {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-primary-fixed);
  border: 1px solid rgba(45, 91, 209, 0.14);
  overflow: hidden;
}

.daily-blur-bg {
  display: none;
}

.bank-overview {
  display: grid;
  gap: var(--space-sm);
}

.overview-card {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-inverse-surface);
  color: var(--color-inverse-on-surface);
}

.overview-kicker {
  display: block;
  margin-bottom: 4px;
  color: rgba(234, 241, 255, 0.62);
  font-size: 11px;
  font-weight: 700;
}

.overview-card h2 {
  margin: 0;
  font-size: 20px;
  line-height: 27px;
}

.overview-stats {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-end;
  color: rgba(234, 241, 255, 0.78);
  font-size: 12px;
  white-space: nowrap;
}

.subject-chips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}

.subject-chips::-webkit-scrollbar {
  display: none;
}

.subject-chip {
  flex: 0 0 auto;
  height: 34px;
  padding: 0 14px;
  border: 1px solid rgba(115, 118, 134, 0.18);
  border-radius: var(--radius-full);
  background: var(--color-surface-container-lowest);
  color: var(--color-on-surface-variant);
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 600;
}

.subject-chip.active {
  background: var(--color-primary-container);
  color: var(--color-on-primary);
  border-color: var(--color-primary-container);
}

.daily-text {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.daily-heading {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.daily-heading svg {
  color: var(--color-secondary-container);
}

.daily-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-on-surface);
  margin: 0;
}

.daily-desc {
  font-size: 14px;
  color: var(--color-outline);
  margin: 0;
}

/* ---- Subject Grid ---- */
.subject-grid-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-card-gutter);
}

.subject-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding: var(--space-md);
  border: none;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
}

.subject-card:active {
  background: var(--color-surface-container-low);
}

.subject-wide {
  grid-column: span 2;
  flex-direction: row;
  align-items: center;
}

.subject-icon-sm {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
}

.subject-text {
  flex: 1;
  min-width: 0;
}

.subject-name {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-on-surface);
  margin: 0 0 2px;
}

.subject-count {
  font-size: 12px;
  color: var(--color-outline);
  margin: 0;
}

.subject-arrow {
  flex-shrink: 0;
}

/* ---- Essay List ---- */
.essay-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.essay-card {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md);
  border: none;
  cursor: pointer;
  transition: transform 0.15s;
  text-align: left;
}

.essay-card:active {
  transform: scale(0.98);
}

.essay-card:hover {
  box-shadow: var(--shadow-card-hover);
}

.essay-avatar {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.essay-avatar-blue {
  background: var(--color-surface-container);
  color: var(--color-primary-container);
}

.essay-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.essay-name {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-on-surface);
}

.essay-meta {
  font-size: 12px;
  color: var(--color-outline);
  margin-top: 2px;
}

.select-book-btn {
  flex-shrink: 0;
  padding: 5px 10px;
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-full);
  background: var(--color-surface-container-lowest);
  color: var(--color-on-surface-variant);
  font-size: 12px;
}

.select-book-btn.selected {
  border-color: var(--color-primary-container);
  background: var(--color-primary-fixed);
  color: var(--color-primary-container);
}

.essay-arrow {
  color: var(--color-outline-variant);
  flex-shrink: 0;
}

/* ---- Shared ---- */
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

.btn-primary {
  position: relative;
  z-index: 1;
  padding: 10px 24px;
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
  white-space: nowrap;
}

.btn-primary:active {
  transform: scale(0.97);
}

.card {
  border: 1px solid rgba(195, 198, 215, 0.3);
}
</style>
