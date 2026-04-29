<template>
  <header class="top-bar">
    <div class="top-bar-left">
      <button v-if="back" class="icon-btn" type="button" aria-label="返回" @click="handleBack">
        <AppIcon name="arrow-left" :size="24" />
      </button>
      <slot name="left" />
      <h1 class="top-bar-title">{{ title }}</h1>
    </div>
    <div class="top-bar-right">
      <slot name="right" />
    </div>
  </header>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
import AppIcon from '@/components/AppIcon.vue';

const props = withDefaults(
  defineProps<{ title: string; back?: boolean }>(),
  { back: true },
);

const router = useRouter();

function handleBack() {
  if (props.back) router.back();
}
</script>

<style scoped>
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

.top-bar-left {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  min-width: 0;
  flex: 1;
}

.top-bar-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--color-primary-container);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-bar-right {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  flex-shrink: 0;
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
  flex-shrink: 0;
}

.icon-btn:active {
  background: var(--color-surface-container);
}
</style>
