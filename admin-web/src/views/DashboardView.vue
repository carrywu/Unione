<template>
  <div class="page">
    <PageHeader>
      <template #actions>
        <div class="header-actions">
          <el-button :icon="Upload" @click="router.push('/banks')">上传题本</el-button>
          <el-button type="primary" :icon="EditPen" @click="router.push('/workbench')">进入制卷</el-button>
        </div>
      </template>
    </PageHeader>

    <section class="hero-panel">
      <div>
        <p class="eyebrow">今日工作台</p>
        <h2>把解析结果快速整理成可发布题库</h2>
        <p class="hero-copy">关注待处理题本、作答质量和题库发布进度。入口集中在这里，少跳转，多处理。</p>
      </div>
      <div class="hero-metrics">
        <div>
          <span>{{ overview.active_users_today }}</span>
          <small>今日活跃</small>
        </div>
        <div>
          <span>{{ overview.total_answered_today }}</span>
          <small>今日作答</small>
        </div>
      </div>
    </section>

    <div class="dashboard-panel">
      <div v-for="metric in metrics" :key="metric.label" class="metric-tile">
        <div class="metric-icon">
          <el-icon><component :is="metric.icon" /></el-icon>
        </div>
        <div>
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}{{ metric.suffix || '' }}</strong>
        </div>
      </div>
    </div>

    <div class="panel list-panel">
      <div class="section-head">
        <div>
          <h3>题库使用情况</h3>
          <p>按作答次数和正确率观察题库质量。</p>
        </div>
        <el-button link type="primary" @click="router.push('/banks')">管理题库</el-button>
      </div>
      <el-table :data="bankUsage" size="small">
        <el-table-column prop="name" label="题库" min-width="220" />
        <el-table-column prop="subject" label="科目" width="100" />
        <el-table-column prop="answer_count" label="作答次数" width="120" />
        <el-table-column prop="user_count" label="用户数" width="100" />
        <el-table-column prop="avg_accuracy_rate" label="正确率" width="100">
          <template #default="{ row }">
            <span class="accuracy">{{ row.avg_accuracy_rate }}%</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { Collection, EditPen, Finished, TrendCharts, Upload, User } from '@element-plus/icons-vue';
import { getAdminOverview, getBankUsage, type AdminOverview } from '@/api/stats';
import PageHeader from '@/components/PageHeader.vue';

const router = useRouter();
const overview = reactive<AdminOverview>({
  total_users: 0,
  active_users_today: 0,
  active_users_week: 0,
  new_users_today: 0,
  new_users_week: 0,
  total_banks: 0,
  published_banks: 0,
  total_questions: 0,
  published_questions: 0,
  total_answered_today: 0,
  total_answered_week: 0,
  total_answered_all: 0,
  avg_accuracy_rate: 0,
});
const bankUsage = ref<Record<string, unknown>[]>([]);

const metrics = computed(() => [
  { label: '注册用户', value: overview.total_users, icon: User },
  { label: '已发布题库', value: overview.published_banks, icon: Collection },
  { label: '已发布题目', value: overview.published_questions, icon: Finished },
  { label: '平均正确率', value: overview.avg_accuracy_rate, suffix: '%', icon: TrendCharts },
]);

onMounted(async () => {
  Object.assign(overview, await getAdminOverview());
  bankUsage.value = await getBankUsage();
});
</script>

<style scoped>
.hero-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 176px;
  padding: 28px 30px;
  border: 1px solid oklch(84% 0.045 248);
  border-radius: var(--admin-radius);
  background:
    linear-gradient(120deg, oklch(98.5% 0.01 248), oklch(93.8% 0.04 248)),
    var(--admin-surface);
  box-shadow: var(--admin-shadow-md);
}

.eyebrow {
  margin: 0 0 10px;
  color: var(--admin-accent);
  font-size: 13px;
  font-weight: 760;
}

.hero-panel h2 {
  max-width: 720px;
  margin: 0;
  color: var(--admin-text);
  font-size: 30px;
  font-weight: 790;
  letter-spacing: 0;
  line-height: 1.2;
}

.hero-copy {
  max-width: 700px;
  margin: 12px 0 0;
  color: var(--admin-text-muted);
  line-height: 1.7;
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(120px, 1fr));
  gap: 10px;
  min-width: 280px;
}

.hero-metrics div {
  padding: 16px;
  border: 1px solid oklch(86% 0.035 248);
  border-radius: 8px;
  background: rgb(252 253 255 / 75%);
}

.hero-metrics span {
  display: block;
  color: var(--admin-text);
  font-size: 28px;
  font-weight: 790;
  line-height: 1;
}

.hero-metrics small {
  display: block;
  margin-top: 8px;
  color: var(--admin-text-faint);
}

.dashboard-panel {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.metric-tile {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 104px;
  padding: 18px;
  border: 1px solid var(--admin-border);
  border-radius: var(--admin-radius);
  background: var(--admin-surface);
  box-shadow: var(--admin-shadow-sm);
}

.metric-icon {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 8px;
  background: var(--admin-accent-soft);
  color: var(--admin-accent);
  font-size: 20px;
}

.metric-tile span {
  display: block;
  color: var(--admin-text-faint);
  font-size: 13px;
}

.metric-tile strong {
  display: block;
  margin-top: 6px;
  color: var(--admin-text);
  font-size: 28px;
  font-weight: 780;
  line-height: 1;
}

.list-panel {
  margin-top: 16px;
  padding: 18px;
}

.header-actions,
.section-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-head {
  justify-content: space-between;
  margin-bottom: 14px;
}

h3 {
  margin: 0;
  color: var(--admin-text);
  font-size: 17px;
  font-weight: 740;
}

.section-head p {
  margin: 5px 0 0;
  color: var(--admin-text-faint);
  font-size: 13px;
}

.accuracy {
  color: var(--admin-success);
  font-weight: 700;
}
</style>
