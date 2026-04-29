<template>
  <svg
    class="app-icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    v-html="paths[name] || paths.book"
  />
</template>

<script setup lang="ts">
type IconName =
  | 'arrow-left'
  | 'bank'
  | 'book'
  | 'chart'
  | 'check'
  | 'chevron-right'
  | 'clock'
  | 'document'
  | 'error-book'
  | 'note'
  | 'play'
  | 'practice'
  | 'profile'
  | 'search'
  | 'spark'
  | 'star'
  | 'target'
  | 'user'
  | 'wrong';

withDefaults(
  defineProps<{
    name: IconName;
    size?: number | string;
    strokeWidth?: number | string;
  }>(),
  {
    size: 24,
    strokeWidth: 2,
  },
);

const paths: Record<IconName, string> = {
  'arrow-left': '<path d="M19 12H5"/><path d="m12 19-7-7 7-7"/>',
  bank: '<path d="M4 21h16"/><path d="M5 21V8l7-5 7 5v13"/><path d="M9 21v-7h6v7"/><path d="M9 10h.01"/><path d="M15 10h.01"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  chart: '<path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 16v-5"/><path d="M12 16V8"/><path d="M16 16v-3"/>',
  check: '<path d="m20 6-11 11-5-5"/>',
  'chevron-right': '<path d="m9 18 6-6-6-6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  document: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h5"/>',
  'error-book': '<path d="M6 3h12a2 2 0 0 1 2 2v16l-4-2-4 2-4-2-4 2V5a2 2 0 0 1 2-2z"/><path d="M9 9h6"/><path d="M9 13h4"/><path d="m15 15 3 3"/><path d="m18 15-3 3"/>',
  note: '<path d="M5 3h11l3 3v15H5z"/><path d="M16 3v4h4"/><path d="M8 11h8"/><path d="M8 15h8"/><path d="M8 19h5"/>',
  play: '<path d="M7 5v14l11-7z"/>',
  practice: '<path d="M5 4h9l5 5v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M14 4v5h5"/><path d="m8 14 2 2 4-5"/>',
  profile: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  spark: '<path d="M12 2 9.4 8.8 3 12l6.4 3.2L12 22l2.6-6.8L21 12l-6.4-3.2L12 2z"/>',
  star: '<path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.8 1-6.1-4.4-4.3 6.1-.9L12 3z"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  user: '<path d="M18 20a6 6 0 0 0-12 0"/><circle cx="12" cy="8" r="4"/>',
  wrong: '<path d="M10.3 3.9 2.1 18a2 2 0 0 0 1.7 3h16.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
};
</script>

<style scoped>
.app-icon {
  display: block;
  flex-shrink: 0;
}
</style>
