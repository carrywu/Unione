<template>
  <span class="math-text" :class="{ 'math-text-empty': !tokens.length }">
    <template v-if="tokens.length">
      <template v-for="(token, index) in tokens" :key="`${token.type}-${index}`">
        <span v-if="token.type === 'text'">{{ token.text }}</span>
        <span v-else-if="token.type === 'operator'" class="math-inline math-operator">{{ token.text }}</span>
        <span v-else class="math-inline math-var">
          <span class="math-base">{{ token.base }}</span><sub class="math-subscript">{{ token.subscript }}</sub>
        </span>
      </template>
    </template>
    <template v-else>{{ fallback }}</template>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { tokenizeMathText } from '@/utils/mathText';

const props = withDefaults(defineProps<{
  text?: unknown;
  fallback?: string;
}>(), {
  text: () => '',
  fallback: '',
});

const tokens = computed(() => tokenizeMathText(props.text, props.fallback));
</script>
