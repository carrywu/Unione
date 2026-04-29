<template>
  <el-image
    class="image-preview"
    :src="src"
    :preview-src-list="[src]"
    fit="cover"
    preview-teleported
  />
</template>

<script setup lang="ts">
defineProps<{
  src: string;
}>();
</script>

<style scoped>
.image-preview {
  width: 96px;
  height: 96px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #f5f7fa;
}
</style>
