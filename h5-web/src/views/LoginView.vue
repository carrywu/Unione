<template>
  <div class="login-page">
    <section class="login-hero" aria-label="登录说明">
      <div class="brand-mark">
        <AppIcon name="book" :size="30" :stroke-width="1.6" />
      </div>
      <div class="hero-copy">
        <span class="hero-kicker">Public Service Exam</span>
        <h1>回到你的备考节奏</h1>
        <p>继续练习、复盘错题，保留每一次答题记录。</p>
      </div>
      <div class="hero-progress" aria-hidden="true">
        <span>Today</span>
        <strong>15 min</strong>
        <div class="progress-line"><i /></div>
      </div>
    </section>

    <main class="login-shell">
      <form class="login-card" @submit.prevent="handleLogin">
        <div class="form-title">
          <h2>登录账号</h2>
          <p>使用手机号登录，继续同步你的学习进度。</p>
        </div>

        <label class="field-group" for="phone">
          <span class="field-label">手机号</span>
          <span class="field-wrap">
            <AppIcon name="profile" :size="18" />
            <input
              id="phone"
              v-model.trim="form.phone"
              class="field-input"
              type="tel"
              inputmode="tel"
              autocomplete="tel"
              placeholder="请输入手机号"
            />
          </span>
        </label>

        <label class="field-group" for="password">
          <span class="field-label">密码</span>
          <span class="field-wrap">
            <AppIcon name="document" :size="18" />
            <input
              id="password"
              v-model="form.password"
              class="field-input"
              type="password"
              autocomplete="current-password"
              placeholder="请输入密码"
            />
          </span>
        </label>

        <p v-if="errorMessage" class="form-error">{{ errorMessage }}</p>

        <button class="btn-submit" type="submit" :disabled="loading">
          <template v-if="loading">
            <span class="spinner" />
            登录中...
          </template>
          <template v-else>
            登录并继续
            <AppIcon name="chevron-right" :size="18" />
          </template>
        </button>

        <div class="demo-account">
          <span>测试账号</span>
          <button type="button" @click="fillDemoAccount">一键填入</button>
        </div>

        <div class="auth-switch">
          <span>还没有账号？</span>
          <button type="button" @click="router.push('/register')">创建账号</button>
        </div>
      </form>
    </main>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import AppIcon from '@/components/AppIcon.vue';
import { useAuthStore } from '@/stores/auth';

const router = useRouter();
const authStore = useAuthStore();
const loading = ref(false);
const errorMessage = ref('');
const form = reactive({ phone: '', password: '' });

function validateForm() {
  if (!form.phone || !form.password) return '请输入手机号和密码';
  if (!/^1\d{10}$/.test(form.phone)) return '请输入 11 位手机号';
  return '';
}

function fillDemoAccount() {
  form.phone = '13800138000';
  form.password = '123456';
  errorMessage.value = '';
}

async function handleLogin() {
  errorMessage.value = validateForm();
  if (errorMessage.value) return;
  loading.value = true;
  try {
    await authStore.login(form.phone, form.password);
    await router.replace('/');
  } catch (error: any) {
    errorMessage.value = error?.response?.data?.message || error?.message || '登录失败，请检查账号密码';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100dvh;
  background: var(--color-bg);
}

.login-hero {
  position: relative;
  min-height: 246px;
  padding: 22px var(--space-container) 28px;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(31, 78, 168, 0.96), rgba(45, 91, 209, 0.92) 58%, rgba(35, 130, 96, 0.88));
  color: var(--color-on-primary);
}

.brand-mark {
  display: grid;
  width: 52px;
  height: 52px;
  place-items: center;
  border: 1px solid rgba(248, 250, 255, 0.24);
  border-radius: 18px;
  background: rgba(248, 250, 255, 0.14);
  color: #f8faff;
}

.hero-copy {
  margin-top: 34px;
  max-width: 280px;
}

.hero-kicker {
  display: block;
  margin-bottom: 8px;
  color: rgba(248, 250, 255, 0.7);
  font-size: 12px;
  font-weight: 700;
}

.hero-copy h1 {
  margin: 0 0 8px;
  color: #fbfcff;
  font-size: 28px;
  line-height: 36px;
}

.hero-copy p {
  margin: 0;
  color: rgba(248, 250, 255, 0.76);
  font-size: 14px;
  line-height: 22px;
}

.hero-progress {
  position: absolute;
  right: 16px;
  bottom: 24px;
  width: 112px;
  padding: 13px;
  border: 1px solid rgba(248, 250, 255, 0.2);
  border-radius: 18px;
  background: rgba(248, 250, 255, 0.14);
}

.hero-progress span {
  display: block;
  color: rgba(248, 250, 255, 0.68);
  font-size: 11px;
}

.hero-progress strong {
  display: block;
  margin: 3px 0 10px;
  color: #fbfcff;
  font-size: 22px;
  line-height: 26px;
}

.progress-line {
  height: 6px;
  overflow: hidden;
  border-radius: var(--radius-full);
  background: rgba(248, 250, 255, 0.18);
}

.progress-line i {
  display: block;
  width: 72%;
  height: 100%;
  border-radius: inherit;
  background: var(--color-secondary-fixed);
}

.login-shell {
  padding: 0 var(--space-container) 28px;
  margin-top: -26px;
}

.login-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  width: 100%;
  padding: 22px;
  border: 1px solid rgba(115, 118, 134, 0.14);
  border-radius: var(--radius-xl);
  background: var(--color-surface-container-lowest);
  box-shadow: var(--shadow-card-hover);
}

.form-title h2 {
  margin: 0 0 4px;
  font-size: 22px;
  line-height: 28px;
}

.form-title p {
  margin: 0;
  color: var(--color-on-surface-variant);
  font-size: 13px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.field-label {
  color: var(--color-on-surface);
  font-size: 14px;
  font-weight: 650;
}

.field-wrap {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  height: 52px;
  padding: 0 var(--space-md);
  border: 1px solid var(--color-outline-variant);
  border-radius: var(--radius-md);
  background: var(--color-surface-bright);
  color: var(--color-outline);
}

.field-wrap:focus-within {
  border-color: var(--color-primary-container);
}

.field-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--color-on-surface);
  font-family: var(--font-body);
  font-size: 16px;
}

.field-input::placeholder {
  color: var(--color-outline);
}

.form-error {
  margin: -4px 0 0;
  color: var(--color-error);
  font-size: 13px;
}

.btn-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  height: 52px;
  width: 100%;
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-primary-container);
  color: var(--color-on-primary);
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 650;
  box-shadow: 0 8px 20px rgba(45, 91, 209, 0.2);
}

.btn-submit:active {
  transform: scale(0.98);
}

.btn-submit:disabled {
  opacity: 0.72;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.demo-account,
.auth-switch {
  display: flex;
  justify-content: center;
  gap: 6px;
  color: var(--color-on-surface-variant);
  font-size: 14px;
}

.demo-account {
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-surface-container-low);
}

.demo-account button,
.auth-switch button {
  border: none;
  background: transparent;
  color: var(--color-primary-container);
  font: inherit;
  font-weight: 700;
  padding: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
