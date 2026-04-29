<template>
  <div class="loading-state">
    <div class="skeleton-card" v-for="n in 3" :key="n">
      <div class="skeleton-line skeleton-line-short" />
      <div class="skeleton-line skeleton-line-long" />
      <div class="skeleton-line skeleton-line-mid" />
    </div>
  </div>
</template>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-container);
}

.skeleton-card {
  padding: var(--space-md);
  border-radius: var(--radius-lg);
  background: var(--color-surface-container-lowest);
  box-shadow: var(--shadow-card);
}

.skeleton-line {
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--color-surface-container) 25%, var(--color-surface-container-high) 50%, var(--color-surface-container) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

.skeleton-line + .skeleton-line {
  margin-top: var(--space-sm);
}

.skeleton-line-short { width: 40%; }
.skeleton-line-long { width: 85%; }
.skeleton-line-mid { width: 60%; }

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
