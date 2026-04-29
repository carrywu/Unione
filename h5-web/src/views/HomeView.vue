<template>
  <div class="home-page safe-bottom">
    <NavBar title="公考刷题" :back="false">
      <template #right>
        <button class="icon-btn" type="button" aria-label="我的" @click="router.push('/profile')">
          <AppIcon name="user" :size="22" />
        </button>
      </template>
    </NavBar>

    <LoadingState v-if="loading" />

    <main v-else class="home-content animate-fade-in">
      <section class="hero-section">
        <div class="hero-card">
          <div class="hero-content">
            <span class="hero-badge">
              <AppIcon name="clock" :size="14" />
              每日一练
            </span>
            <h2 class="hero-title">今天先稳住正确率</h2>
            <p class="hero-desc">今日已完成 {{ stats.today_answered || 0 }} 题，连续 {{ stats.streak_days || 0 }} 天打卡</p>
            <div class="hero-actions">
              <button class="hero-primary" :disabled="!firstBankId" @click="startBank(firstBankId)">
                <AppIcon name="play" :size="16" />
                开始练习
              </button>
              <button class="hero-secondary" @click="router.push('/wrong')">复盘错题</button>
            </div>
          </div>
          <div class="hero-panel" aria-hidden="true">
            <span class="hero-panel-label">Accuracy</span>
            <strong>{{ accuracyRate }}%</strong>
            <div class="hero-panel-line"><span :style="{ width: `${Math.max(8, accuracyRate)}%` }" /></div>
          </div>
        </div>
      </section>

      <section class="metric-strip">
        <div class="metric-item">
          <strong>{{ stats.total_answered || 0 }}</strong>
          <span>累计做题</span>
        </div>
        <div class="metric-item">
          <strong>{{ stats.wrong_count || 0 }}</strong>
          <span>错题待清</span>
        </div>
        <div class="metric-item">
          <strong>{{ banks.length }}</strong>
          <span>可练题本</span>
        </div>
      </section>

      <!-- Learning Progress Card -->
      <section class="card progress-card">
        <div class="progress-header">
          <div class="section-heading" style="margin-bottom: 0;">
            <span class="section-title">当前学习计划</span>
          </div>
          <button class="link-btn" @click="router.push('/profile')">
            查看统计
            <AppIcon name="chevron-right" :size="14" />
          </button>
        </div>
        <div class="progress-body">
          <div class="ring-chart">
            <svg viewBox="0 0 36 36" class="ring-svg">
              <path class="ring-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
              <path class="ring-fill" :stroke-dasharray="`${accuracyRate}, 100`" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
            </svg>
            <div class="ring-center">
              <span class="ring-value">{{ accuracyRate }}%</span>
            </div>
          </div>
          <div class="progress-info">
            <h4 class="progress-subject">{{ firstBank?.name || '行测全科 · 综合训练' }}</h4>
            <p class="progress-meta">已累计答题 {{ stats.total_answered || 0 }} 题</p>
            <button class="btn-primary" :disabled="!firstBankId" @click="startBank(firstBankId)">继续学习</button>
          </div>
        </div>
      </section>

      <!-- Hot Sections Bento -->
      <section>
        <div class="section-heading">
          <span class="section-title">热门板块</span>
        </div>
        <div class="bento-grid">
          <!-- Large item: span 2 cols -->
          <div class="bento-card bento-wide tap-surface" role="button" tabindex="0" @click="startBank(firstBankId)" @keyup.enter="startBank(firstBankId)">
            <div class="bento-wide-inner">
              <div class="bento-wide-body">
                <div class="bento-wide-icon">
                  <span class="mini-icon mini-icon-secondary"><AppIcon name="practice" :size="18" /></span>
                  <span>快速练习</span>
                </div>
                <p class="bento-wide-desc">随机组卷，限时作答</p>
                <span class="bento-wide-tag">15题 · 约20分钟</span>
              </div>
              <span class="btn-pill-sm" aria-hidden="true">开始</span>
            </div>
          </div>
          <!-- Small item 1 -->
          <div class="bento-card tap-surface" role="button" tabindex="0" @click="router.push('/wrong')" @keyup.enter="router.push('/wrong')">
            <span class="icon-tile icon-tile-success"><AppIcon name="error-book" :size="24" /></span>
            <div>
              <h4 class="bento-title">错题复盘</h4>
              <p class="bento-desc">针对性消灭薄弱项</p>
            </div>
          </div>
          <!-- Small item 2 -->
          <div class="bento-card tap-surface" role="button" tabindex="0" @click="router.push('/bank')" @keyup.enter="router.push('/bank')">
            <span class="icon-tile icon-tile-primary"><AppIcon name="bank" :size="24" /></span>
            <div>
              <h4 class="bento-title">题库管理</h4>
              <p class="bento-desc">选择专项题本训练</p>
            </div>
          </div>
        </div>
      </section>

      <!-- Smart Recommendations -->
      <section>
        <div class="section-heading">
          <AppIcon name="spark" :size="18" />
          <span class="section-title">智能推荐</span>
        </div>
        <div class="recommend-list">
          <!-- Weakness item -->
          <div
            class="rec-card tap-surface"
            :class="{ loading: recommendationLoading }"
            role="button"
            tabindex="0"
            @click="startRecommendation"
            @keyup.enter="startRecommendation"
          >
            <div class="rec-icon rec-icon-blue">
              <span v-if="recommendationLoading" class="rec-spinner" />
              <AppIcon v-else :name="recommendedWeakness ? 'target' : 'wrong'" :size="22" />
            </div>
            <div class="rec-body">
              <div class="rec-header">
              <h4 class="rec-title">{{ recommendedWeakness?.bank_name || '错题巩固 · 随机练习' }}</h4>
                <span class="rec-badge-warn">{{ recommendedWeakness ? '薄弱项' : '错题' }}</span>
              </div>
              <p class="rec-desc">{{ recommendedWeakness ? `${recommendedWeakness.subject} 正确率 ${recommendedWeakness.accuracy_rate}%` : '基于错题本生成针对性训练' }}</p>
              <div class="rec-meta">
                <span><AppIcon name="clock" :size="14" /> 15 分钟</span>
                <span class="rec-meta-sep">|</span>
                <span><AppIcon name="document" :size="14" /> {{ recommendedWeakness?.answered || 10 }} 题记录</span>
              </div>
            </div>
            <span class="rec-btn" aria-hidden="true">
              <AppIcon name="play" :size="18" />
            </span>
          </div>
          <!-- Regular item -->
          <div class="rec-card tap-surface" role="button" tabindex="0" @click="startBank(firstBankId)" @keyup.enter="startBank(firstBankId)">
            <div class="rec-icon rec-icon-green">
              <AppIcon name="book" :size="22" />
            </div>
            <div class="rec-body">
              <div class="rec-header">
                <h4 class="rec-title">{{ firstBank?.name || '每日一练' }}</h4>
              </div>
              <p class="rec-desc">{{ firstBank ? `${firstBank.subject}，共 ${firstBank.total_count || 0} 题` : '选择一个已发布题库开始练习' }}</p>
              <div class="rec-meta">
                <span><AppIcon name="chart" :size="14" /> 今日 {{ stats.today_answered || 0 }} 题</span>
              </div>
            </div>
            <span class="rec-btn" aria-hidden="true">
              <AppIcon name="play" :size="18" />
            </span>
          </div>
        </div>
      </section>

      <!-- Subject Categories -->
      <section>
        <div class="section-heading">
          <span class="section-title">行测科目</span>
        </div>
        <div class="subject-grid">
          <button
            v-for="subject in subjects"
            :key="subject.name"
            class="subject-card card"
            @click="openSubject(subject.bankId)"
          >
            <div class="subject-icon" :style="{ background: subject.bg, color: subject.color }">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" v-html="subject.icon" />
            </div>
            <div class="subject-info">
              <h4 class="subject-name">{{ subject.name }}</h4>
              <p class="subject-count">{{ subject.count }} 题</p>
            </div>
            <AppIcon class="subject-arrow" name="chevron-right" :size="16" />
          </button>
        </div>
      </section>
    </main>

    <BottomNavBar />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { getBanks, type Bank } from '@/api/bank';
import { getStats, getWeakness, getWrongPractice } from '@/api/record';
import LoadingState from '@/components/LoadingState.vue';
import NavBar from '@/components/NavBar.vue';
import BottomNavBar from '@/components/BottomNavBar.vue';
import { showToast } from 'vant';
import { useQuizStore } from '@/stores/quiz';
import AppIcon from '@/components/AppIcon.vue';

const router = useRouter();
const quiz = useQuizStore();
const loading = ref(false);
const recommendationLoading = ref(false);
const banks = ref<Bank[]>([]);
const stats = ref({ total_answered: 0, correct_count: 0, accuracy_rate: 0, wrong_count: 0, today_answered: 0, streak_days: 0 });
const weaknessBanks = ref<Array<{ bank_id: string; bank_name: string; subject: string; answered: number; accuracy_rate: number }>>([]);

const accuracyRate = computed(() => Math.round((stats.value.accuracy_rate || 0) * 100));
const firstBank = computed(() => banks.value.find((bank) => bank.total_count > 0) || banks.value[0]);
const firstBankId = computed(() => firstBank.value?.id || '');
const recommendedWeakness = computed(() => weaknessBanks.value[0]);

const subjectIcons: Record<string, { icon: string; bg: string; color: string }> = {
  '言语理解': { icon: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>', bg: '#dbe1ff', color: '#004ac6' },
  '判断推理': { icon: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/>', bg: '#bdffdb', color: '#006242' },
  '数量关系': { icon: '<rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="12" y2="14"/>', bg: '#ffdcc5', color: '#944a00' },
  '资料分析': { icon: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>', bg: '#dbe1ff', color: '#004ac6' },
  '常识判断': { icon: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>', bg: '#e5eeff', color: '#434655' },
  default: { icon: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>', bg: '#e5eeff', color: '#434655' },
};

const subjects = computed(() => {
  const map = new Map<string, { count: number; bankId: string }>();
  banks.value.forEach((b) => {
    if (!map.has(b.subject)) map.set(b.subject, { count: 0, bankId: b.id });
    const entry = map.get(b.subject)!;
    entry.count += b.total_count || 0;
  });
  return Array.from(map.entries()).map(([name, data]) => {
    const iconConf = subjectIcons[name] || subjectIcons.default;
    return { name, count: data.count, bankId: data.bankId, ...iconConf };
  });
});

function startBank(bankId?: string) {
  if (!bankId) {
    void router.push('/bank');
    return;
  }
  void router.push(`/quiz/${bankId}`);
}

function openSubject(bankId?: string) {
  void router.push(bankId ? `/bank/${bankId}` : '/bank');
}

async function startRecommendation() {
  if (recommendationLoading.value) return;
  const weakness = recommendedWeakness.value;
  if (weakness?.bank_id) {
    startBank(weakness.bank_id);
    return;
  }
  recommendationLoading.value = true;
  try {
    const questions = (await getWrongPractice({ count: 15 })) as any[];
    if (!questions.length) {
      showToast('暂无错题，已为你打开题库');
      await router.push('/bank');
      return;
    }
    await quiz.startQuiz(questions[0].bank_id, questions);
    await router.push(`/quiz/${questions[0].bank_id}`);
  } finally {
    recommendationLoading.value = false;
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    const [bankResult, statsResult, weaknessResult] = await Promise.all([
      getBanks({ page: 1, pageSize: 100 }),
      getStats().catch(() => null),
      getWeakness().catch(() => null),
    ]);
    banks.value = bankResult.list || [];
    if (statsResult) stats.value = statsResult;
    weaknessBanks.value = weaknessResult?.weakness_banks || [];
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.home-page {
  padding-bottom: 80px;
}

.home-content {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
  padding: var(--space-md) var(--space-container) 0;
}

/* ---- Hero ---- */
.hero-section {
  margin: calc(-1 * var(--space-md)) calc(-1 * var(--space-container)) 0;
}

.hero-card {
  position: relative;
  min-height: 222px;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba(31, 78, 168, 0.94) 0%, rgba(45, 91, 209, 0.9) 54%, rgba(35, 130, 96, 0.86) 100%);
  color: var(--color-on-primary);
}

.hero-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 100%;
  max-width: 62%;
  padding: 28px var(--space-md) 30px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: fit-content;
  padding: 4px 12px;
  margin-bottom: var(--space-sm);
  border-radius: var(--radius-full);
  background: rgba(248, 250, 255, 0.16);
  border: 1px solid rgba(248, 250, 255, 0.18);
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: 500;
  color: #f7f9ff;
}

.hero-title {
  font-family: var(--font-display);
  font-size: 25px;
  font-weight: 760;
  line-height: 32px;
  color: var(--color-on-surface);
  color: #f8faff;
  margin: 0 0 8px;
}

.hero-desc {
  font-size: 14px;
  color: rgba(248, 250, 255, 0.76);
  margin: 0;
}

.hero-actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}

.hero-primary,
.hero-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 38px;
  padding: 0 15px;
  border-radius: var(--radius-full);
  border: 1px solid transparent;
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 650;
}

.hero-primary {
  background: #fbfcff;
  color: var(--color-primary-container);
}

.hero-primary:disabled {
  opacity: 0.6;
}

.hero-secondary {
  background: transparent;
  color: #f8faff;
  border-color: rgba(248, 250, 255, 0.26);
}

.hero-panel {
  position: absolute;
  right: 16px;
  bottom: 24px;
  width: 118px;
  padding: 14px;
  border-radius: 18px;
  background: rgba(248, 250, 255, 0.14);
  border: 1px solid rgba(248, 250, 255, 0.2);
}

.hero-panel-label {
  display: block;
  color: rgba(248, 250, 255, 0.68);
  font-size: 11px;
  line-height: 14px;
}

.hero-panel strong {
  display: block;
  margin: 3px 0 10px;
  color: #fbfcff;
  font-size: 24px;
  line-height: 28px;
}

.hero-panel-line {
  height: 6px;
  overflow: hidden;
  border-radius: var(--radius-full);
  background: rgba(248, 250, 255, 0.18);
}

.hero-panel-line span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--color-secondary-fixed);
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-sm);
}

.metric-item {
  display: grid;
  gap: 2px;
  padding: 13px 10px;
  border: 1px solid rgba(115, 118, 134, 0.14);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  text-align: center;
}

.metric-item strong {
  font-size: 18px;
  line-height: 24px;
  color: var(--color-on-surface);
}

.metric-item span {
  font-size: 12px;
  color: var(--color-on-surface-variant);
}

/* ---- Progress Card ---- */
.progress-card {
  padding: var(--space-md);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}

.progress-header .section-heading {
  margin-bottom: 0;
}

.link-btn {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  border: none;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--color-primary-container);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}
.link-btn:active { background: var(--color-surface-container); }

.progress-body {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.ring-chart {
  position: relative;
  width: 64px;
  height: 64px;
  flex-shrink: 0;
}

.ring-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.ring-bg {
  fill: none;
  stroke: var(--color-surface-container-high);
  stroke-width: 3.8;
}
.ring-fill {
  fill: none;
  stroke: var(--color-primary-container);
  stroke-width: 3.8;
  stroke-linecap: round;
  transition: stroke-dasharray 0.5s ease;
}

.ring-center {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ring-value {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--color-primary-container);
}

.progress-info {
  flex: 1;
  min-width: 0;
}

.progress-subject {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-on-surface);
  margin: 0 0 2px;
}

.progress-meta {
  font-size: 12px;
  color: var(--color-on-surface-variant);
  margin: 0 0 10px;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-primary-container);
  color: var(--color-on-primary);
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-primary:active { transform: scale(0.97); opacity: 0.9; }
.btn-primary:disabled {
  opacity: 0.55;
  transform: none;
}

/* ---- Bento Grid ---- */
.bento-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-card-gutter);
}

.bento-wide {
  grid-column: span 2;
}

.bento-card {
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-low);
  border: 1px solid rgba(195, 198, 215, 0.25);
  cursor: pointer;
}
.bento-card:active { background: var(--color-surface-container-high); }
.bento-card:hover {
  box-shadow: var(--shadow-card-hover);
}

.bento-wide-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}

.bento-wide-body {
  flex: 1;
  min-width: 0;
}

.bento-wide-icon {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-on-surface);
}

.mini-icon {
  display: inline-grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: var(--radius-full);
}

.mini-icon-secondary {
  background: var(--color-secondary-fixed);
  color: var(--color-secondary);
}

.bento-wide-desc {
  font-size: 13px;
  color: var(--color-on-surface-variant);
  margin: 0 0 4px;
}

.bento-wide-tag {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-secondary);
}

.bento-card svg {
  flex-shrink: 0;
  margin-bottom: var(--space-sm);
}

.bento-card .icon-tile svg,
.bento-card .mini-icon svg,
.bento-wide-icon svg {
  margin-bottom: 0;
}

.bento-title {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-on-surface);
  margin: 0 0 2px;
}

.bento-desc {
  font-size: 12px;
  color: var(--color-on-surface-variant);
  margin: 0;
}

.btn-pill-sm {
  padding: 6px 16px;
  border: 1px solid var(--color-surface-container-highest);
  border-radius: var(--radius-full);
  background: var(--color-surface-container-lowest);
  color: var(--color-primary-container);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}
.btn-pill-sm:active { background: var(--color-surface-container); }

/* ---- Smart Recommendations ---- */
.recommend-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-card-gutter);
}

.rec-card {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  box-shadow: var(--shadow-card);
  border: 1px solid rgba(219, 225, 255, 0.5);
  cursor: pointer;
}
.rec-card:active { background: var(--color-surface-container-low); }
.rec-card:hover {
  border-color: rgba(37, 99, 235, 0.18);
  box-shadow: var(--shadow-card-hover);
}

.rec-card.loading {
  pointer-events: none;
  opacity: 0.82;
}

.rec-icon {
  width: 48px;
  height: 48px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.rec-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(37, 99, 235, 0.18);
  border-top-color: var(--color-primary-container);
  border-radius: var(--radius-full);
  animation: spin 0.7s linear infinite;
}
.rec-icon-blue {
  background: var(--color-primary-fixed);
  color: var(--color-on-primary-fixed-variant);
}
.rec-icon-green {
  background: var(--color-tertiary-fixed);
  color: var(--color-on-tertiary-fixed-variant);
}

.rec-body {
  flex: 1;
  min-width: 0;
}

.rec-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-sm);
}

.rec-title {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 500;
  color: var(--color-on-surface);
  margin: 0;
}

.rec-badge-warn {
  flex-shrink: 0;
  display: inline-block;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  background: var(--color-error-container);
  color: var(--color-on-error-container);
  font-size: 10px;
  font-weight: 500;
}

.rec-desc {
  font-size: 13px;
  color: var(--color-on-surface-variant);
  margin: 6px 0;
}

.rec-meta {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: 12px;
  color: var(--color-on-surface-variant);
}

.rec-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.rec-meta-sep {
  color: var(--color-outline-variant);
}

.rec-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 50%;
  background: var(--color-surface-container-high);
  color: var(--color-primary-container);
  cursor: pointer;
  flex-shrink: 0;
  align-self: center;
  transition: background 0.15s;
}
.rec-btn:active { background: var(--color-surface-container-highest); }
.rec-btn svg {
  margin-bottom: 0;
}

/* ---- Subject Grid ---- */
.subject-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-card-gutter);
}

.subject-card {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-md);
  border: none;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}
.subject-card:active { background: var(--color-surface-container-low); }

.subject-icon {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.subject-info {
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
  color: var(--color-outline-variant);
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
.icon-btn:active { background: var(--color-surface-container); }

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
