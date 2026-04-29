<template>
  <div class="profile-page">
    <!-- Gradient Header -->
    <div class="profile-hero">
      <div v-if="auth.token" class="profile-info">
        <div class="avatar-wrap">
          <img v-if="avatar" :src="avatar" class="avatar-img" alt="avatar" />
          <div v-else class="avatar-placeholder">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-primary-container)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          </div>
        </div>
        <div class="profile-details">
          <h1 class="profile-name">{{ auth.userInfo?.nickname || '备考学子' }}</h1>
        </div>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-on-surface-variant)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
      </div>

      <div v-else class="login-prompt" @click="router.push('/login')">
        <div class="avatar-placeholder">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-primary-container)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        </div>
        <div class="profile-details">
          <h1 class="profile-name">点击登录</h1>
          <p class="profile-meta">登录后查看学习统计</p>
        </div>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-on-surface-variant)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
      </div>

      <!-- Stats -->
      <div class="hero-stats">
        <div class="hero-stat">
          <span class="hero-stat-num">{{ stats.streak_days || 0 }}</span>
          <span class="hero-stat-label">学习天数</span>
        </div>
        <div class="hero-stat hero-stat-bordered">
          <span class="hero-stat-num">{{ stats.total_answered || 0 }}</span>
          <span class="hero-stat-label">做题总数</span>
        </div>
        <div class="hero-stat">
          <span class="hero-stat-num">{{ accuracyRate }}%</span>
          <span class="hero-stat-label">正确率</span>
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <main class="profile-content">
      <!-- Bento Function Cards -->
      <section class="bento-func card">
        <div class="bento-grid">
          <div class="bento-wrong" @click="router.push('/wrong')">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="var(--color-error)" stroke="none"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
            <span class="bento-label">错题本</span>
            <span class="bento-badge bento-badge-red">新 {{ wrongCount }}</span>
          </div>
          <div class="bento-right-col">
            <div class="bento-row" @click="router.push('/bank')">
              <div class="bento-row-icon bento-icon-orange">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              </div>
              <div class="bento-row-text">
                <span class="bento-label">我的题本</span>
                <span class="bento-desc">{{ selectedBooks.length }} 个已选题本</span>
              </div>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-outline)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
            </div>
            <div class="bento-row" @click="router.push('/wrong')">
              <div class="bento-row-icon bento-icon-green">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/></svg>
              </div>
              <div class="bento-row-text">
                <span class="bento-label">本周练习</span>
                <span class="bento-desc">{{ stats.this_week_answered || 0 }} 题</span>
              </div>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-outline)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
            </div>
          </div>
        </div>
      </section>

      <section v-if="auth.token" class="menu-list card">
        <button v-for="item in menuItems" :key="item.label" class="menu-item" @click="item.action">
          <div class="menu-icon" :style="{ background: item.iconBg, color: item.iconColor }">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="item.icon" />
          </div>
          <span class="menu-label">{{ item.label }}</span>
          <span v-if="item.badge" class="menu-badge">{{ item.badge }}</span>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-outline)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
        </button>
      </section>

      <section class="book-list card">
        <div class="book-list-head">
          <span>已选题本</span>
          <button @click="router.push('/bank')">管理</button>
        </div>
        <div v-if="selectedBooks.length" class="book-items">
          <button v-for="book in selectedBooks" :key="book.id" class="book-item" @click="router.push(`/quiz/${book.id}`)">
            <span>{{ book.name }}</span>
            <small>{{ book.subject }} · {{ book.total_count || 0 }} 题</small>
          </button>
        </div>
        <p v-else class="book-empty">还没有选择题本，先去题库挑一个开始练。</p>
      </section>
    </main>

    <BottomNavBar />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { getQuestionBooks } from '@/api/auth';
import type { Bank } from '@/api/bank';
import { getStats } from '@/api/record';
import BottomNavBar from '@/components/BottomNavBar.vue';
import { useAuthStore } from '@/stores/auth';

const router = useRouter();
const auth = useAuthStore();

const stats = reactive({
  total_answered: 0,
  correct_count: 0,
  accuracy_rate: 0,
  wrong_count: 0,
  today_answered: 0,
  this_week_answered: 0,
  streak_days: 0,
});
const selectedBooks = ref<Bank[]>([]);

const avatar = computed(() => String(auth.userInfo?.avatar || ''));
const wrongCount = computed(() => stats.wrong_count || 0);
const accuracyRate = computed(() => Math.round((stats.accuracy_rate || 0) * 100));

const menuItems = computed(() => [
  {
    label: '学习统计',
    icon: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    iconBg: 'var(--color-surface-container-high)',
    iconColor: 'var(--color-outline)',
    badge: '',
    action: () => router.push('/wrong'),
  },
  {
    label: '退出登录',
    icon: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    iconBg: 'var(--color-error-container)',
    iconColor: 'var(--color-error)',
    badge: '',
    action: handleLogout,
  },
]);

async function handleLogout() {
  auth.logout();
  await router.replace('/login');
}

onMounted(async () => {
  if (auth.token) {
    await auth.fetchProfile();
    try {
      const [nextStats, books] = await Promise.all([
        getStats().catch(() => null),
        getQuestionBooks().catch(() => []),
      ]);
      if (nextStats) Object.assign(stats, nextStats);
      selectedBooks.value = books;
    } catch { /* keep defaults */ }
  }
});
</script>

<style scoped>
.profile-page {
  min-height: 100dvh;
  background: var(--color-bg);
  padding-bottom: 80px;
}

/* ---- Hero ---- */
.profile-hero {
  background: linear-gradient(180deg, var(--color-primary-fixed) 0%, var(--color-bg) 100%);
  padding: var(--space-md) var(--space-container) var(--space-lg);
  border-radius: 0 0 32px 32px;
}

.profile-info,
.login-prompt {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: 32px;
}

.avatar-wrap {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  overflow: hidden;
  border: 2px solid var(--color-surface-container-lowest);
  flex-shrink: 0;
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-placeholder {
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--color-surface-container-lowest);
  flex-shrink: 0;
}

.profile-details {
  flex: 1;
  min-width: 0;
}

.profile-name {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 700;
  color: var(--color-on-surface);
  margin: 0 0 4px;
}

.profile-meta {
  margin: 0;
  color: var(--color-on-surface-variant);
  font-size: 14px;
}

.login-prompt { cursor: pointer; }

/* ---- Hero Stats ---- */
.hero-stats {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--space-md);
}

.hero-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.hero-stat-bordered {
  border-left: 1px solid rgba(195, 198, 215, 0.4);
  border-right: 1px solid rgba(195, 198, 215, 0.4);
}

.hero-stat-num {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-on-surface);
}

.hero-stat-label {
  font-size: 12px;
  color: var(--color-on-surface-variant);
}

/* ---- Content ---- */
.profile-content {
  padding: 0 var(--space-container) var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-top: -16px;
  position: relative;
  z-index: 1;
}

/* ---- Bento Functions ---- */
.bento-func {
  padding: var(--space-md);
}

.bento-grid {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: var(--space-sm);
}

.bento-wrong {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: var(--space-md);
  border-radius: var(--radius-sm);
  background: rgba(186, 26, 26, 0.06);
  cursor: pointer;
  position: relative;
  overflow: hidden;
}

.bento-wrong:active {
  background: rgba(186, 26, 26, 0.1);
}

.bento-label {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-on-surface);
}

.bento-badge {
  padding: 1px 8px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
}

.bento-badge-red {
  background: rgba(186, 26, 26, 0.1);
  color: var(--color-error);
}

.bento-right-col {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.bento-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  background: var(--color-surface-container);
  cursor: pointer;
}

.bento-row:active {
  background: var(--color-surface-container-high);
}

.bento-row-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  flex-shrink: 0;
}

.bento-icon-orange {
  background: rgba(253, 147, 61, 0.15);
  color: var(--color-secondary-container);
}

.bento-icon-green {
  background: rgba(0, 125, 85, 0.1);
  color: var(--color-tertiary-container);
}

.bento-row-text {
  flex: 1;
}

.bento-desc {
  display: block;
  font-size: 12px;
  color: var(--color-on-surface-variant);
}

/* ---- Menu List ---- */
.menu-list {
  overflow: hidden;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: var(--space-md);
  border: none;
  border-bottom: 1px solid var(--color-surface-container);
  background: transparent;
  cursor: pointer;
  text-align: left;
  font: inherit;
  transition: background 0.15s;
}

.menu-item:last-child {
  border-bottom: none;
}

.menu-item:active {
  background: var(--color-surface-container-low);
}

.menu-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  flex-shrink: 0;
}

.menu-label {
  flex: 1;
  font-size: 16px;
  color: var(--color-on-surface);
}

.menu-badge {
  font-size: 12px;
  color: var(--color-on-surface-variant);
}

.book-list {
  padding: var(--space-md);
}

.book-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-sm);
  font-family: var(--font-display);
  font-weight: 600;
}

.book-list-head button {
  border: none;
  background: transparent;
  color: var(--color-primary-container);
  font: inherit;
  font-size: 13px;
}

.book-items {
  display: grid;
  gap: var(--space-sm);
}

.book-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  padding: 10px 0;
  border: none;
  border-top: 1px solid var(--color-surface-container);
  background: transparent;
  color: var(--color-on-surface);
  text-align: left;
}

.book-item span {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.book-item small,
.book-empty {
  color: var(--color-on-surface-variant);
}

.book-empty {
  margin: 0;
  font-size: 13px;
  line-height: 20px;
}
</style>
