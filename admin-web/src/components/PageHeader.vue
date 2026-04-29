<template>
  <div class="page-header">
    <div>
      <el-breadcrumb separator="/">
        <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
        <el-breadcrumb-item v-for="item in items" :key="item">{{ item }}</el-breadcrumb-item>
      </el-breadcrumb>
      <h1>{{ title }}</h1>
    </div>
    <slot name="actions" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();
const title = computed(() => String(route.meta.title || ''));
const items = computed(() => (title.value && title.value !== '首页' ? [title.value] : []));
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.page-header h1 {
  margin: 9px 0 0;
  color: var(--admin-text);
  font-size: 25px;
  font-weight: 760;
  letter-spacing: 0;
  line-height: 1.2;
}

.page-header :deep(.el-breadcrumb__inner) {
  color: var(--admin-text-faint);
  font-size: 12px;
}
</style>
