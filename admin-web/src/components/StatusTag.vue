<template>
  <el-tag :type="tagType" size="small">{{ label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  status?: 'draft' | 'published';
  needsReview?: boolean;
}>();

const tagType = computed(() => {
  if (props.needsReview) return 'danger';
  if (props.status === 'published') return 'success';
  return 'info';
});

const label = computed(() => {
  if (props.needsReview) return '待审核';
  if (props.status === 'published') return '已发布';
  return '草稿';
});
</script>
