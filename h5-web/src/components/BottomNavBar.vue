<template>
  <nav class="bottom-nav">
    <button
      v-for="tab in tabs"
      :key="tab.to"
      class="nav-item"
      :class="{ active: isActive(tab.to) }"
      type="button"
      :aria-current="isActive(tab.to) ? 'page' : undefined"
      @click="navigate(tab.to)"
    >
      <span class="nav-icon-wrap">
        <AppIcon :name="tab.icon" class="nav-icon" :size="23" />
      </span>
      <span class="nav-label">{{ tab.label }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import AppIcon from '@/components/AppIcon.vue';

const router = useRouter();
const route = useRoute();

const currentRoute = computed(() => route.path);

interface Tab {
  to: string;
  label: string;
  icon: InstanceType<typeof AppIcon>['$props']['name'];
}

const tabs: Tab[] = [
  { to: '/', label: '练习', icon: 'practice' },
  { to: '/bank', label: '题库', icon: 'bank' },
  { to: '/wrong', label: '错题', icon: 'wrong' },
  { to: '/profile', label: '我的', icon: 'profile' },
];

function navigate(to: string) {
  if (isActive(to)) return;
  router.push(to);
}

function isActive(to: string) {
  if (to === '/bank') return currentRoute.value.startsWith('/bank');
  if (to === '/') return currentRoute.value === '/' || currentRoute.value.startsWith('/quiz') || currentRoute.value === '/result';
  return currentRoute.value === to;
}
</script>

<style scoped>
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 50;
  display: flex;
  justify-content: space-around;
  align-items: center;
  height: 70px;
  padding: 8px 10px calc(10px + env(safe-area-inset-bottom));
  background: rgba(251, 252, 255, 0.96);
  border-top: 1px solid rgba(115, 118, 134, 0.16);
  box-shadow: 0 -10px 30px rgba(18, 24, 38, 0.06);
  max-width: 750px;
  margin: 0 auto;
}

.nav-item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  min-width: 64px;
  min-height: 50px;
  padding: 6px 11px;
  border: 1px solid transparent;
  border-radius: 18px;
  background: transparent;
  color: var(--color-outline);
  cursor: pointer;
  transition:
    color var(--duration-base) var(--ease-out),
    background-color var(--duration-base) var(--ease-out),
    transform var(--duration-fast) var(--ease-press);
}

.nav-item.active {
  color: var(--color-primary-container);
  background: var(--color-primary-fixed);
  border-color: rgba(45, 91, 209, 0.16);
}

.nav-item:active {
  transform: scale(0.95);
}

.nav-icon-wrap {
  position: relative;
  display: grid;
  width: 26px;
  height: 26px;
  place-items: center;
}

.nav-icon-wrap::after {
  content: '';
  position: absolute;
  left: 50%;
  right: auto;
  top: auto;
  bottom: -18px;
  width: 18px;
  height: 3px;
  border-radius: var(--radius-full);
  background: var(--color-primary-container);
  opacity: 0;
  transform: translateX(-50%) scaleX(0.3);
  transition:
    opacity var(--duration-base) var(--ease-out),
    transform var(--duration-base) var(--ease-out);
}

.nav-item.active .nav-icon-wrap::after {
  opacity: 1;
  transform: translateX(-50%) scaleX(1);
}

.nav-icon {
  width: 24px;
  height: 24px;
  display: block;
}

.nav-label {
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 500;
  line-height: 14px;
}
</style>
