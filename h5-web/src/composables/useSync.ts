import { onMounted, onBeforeUnmount } from 'vue';
import { batchSubmit, type SubmitPayload } from '@/api/record';

function keyOf(bankId: string) {
  return `quiz_records_${bankId}`;
}

export function useSync(bankId?: string) {
  function saveLocal(targetBankId: string, record: SubmitPayload) {
    const key = keyOf(targetBankId);
    const records = JSON.parse(localStorage.getItem(key) || '[]') as SubmitPayload[];
    records.push(record);
    localStorage.setItem(key, JSON.stringify(records));
  }

  async function syncPending() {
    const keys = Object.keys(localStorage).filter((key) => key.startsWith('quiz_records_'));
    for (const key of keys) {
      const records = JSON.parse(localStorage.getItem(key) || '[]') as SubmitPayload[];
      if (!records.length) continue;
      await batchSubmit(records);
      localStorage.removeItem(key);
    }
  }

  function handleOnline() {
    void syncPending();
  }

  onMounted(() => {
    window.addEventListener('online', handleOnline);
    if (navigator.onLine && bankId) void syncPending();
  });

  onBeforeUnmount(() => window.removeEventListener('online', handleOnline));

  return { saveLocal, syncPending };
}
