import { defineStore } from 'pinia';
import type { Bank } from '@/api/bank';

export const useBankStore = defineStore('bank', {
  state: () => ({
    currentBank: null as Bank | null,
    cache: {} as Record<string, Bank>,
  }),
  actions: {
    setCurrentBank(bank: Bank) {
      this.currentBank = bank;
      this.cache[bank.id] = bank;
    },
  },
});
