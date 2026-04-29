<template>
  <div class="register-page">
    <section class="register-hero" aria-label="注册说明">
      <button class="back-btn" type="button" aria-label="返回登录" @click="router.replace('/login')">
        <AppIcon name="arrow-left" :size="20" />
      </button>
      <div class="hero-copy">
        <span class="hero-kicker">Public Service Exam</span>
        <h1>建立你的刷题档案</h1>
        <p>保存题本选择、错题记录和每一次练习结果。</p>
      </div>
      <div class="hero-stats" aria-hidden="true">
        <div>
          <strong>15</strong>
          <span>分钟一组</span>
        </div>
        <div>
          <strong>3</strong>
          <span>步开始</span>
        </div>
      </div>
    </section>

    <main class="register-shell">
      <form class="register-card" @submit.prevent="handleRegister">
        <div class="form-title">
          <h2>创建账号</h2>
          <p>手机号只用于登录和保存学习进度。</p>
        </div>

        <label class="field-group" for="nickname">
          <span class="field-label">昵称</span>
          <span class="field-wrap">
            <AppIcon name="user" :size="18" />
            <input id="nickname" v-model.trim="form.nickname" class="field-input" type="text" autocomplete="nickname" placeholder="例如：备考学子" />
          </span>
        </label>

        <label class="field-group" for="phone">
          <span class="field-label">手机号</span>
          <span class="field-wrap">
            <AppIcon name="profile" :size="18" />
            <input id="phone" v-model.trim="form.phone" class="field-input" type="tel" inputmode="tel" autocomplete="tel" placeholder="请输入手机号" />
          </span>
        </label>

        <label class="field-group" for="password">
          <span class="field-label">密码</span>
          <span class="field-wrap">
            <AppIcon name="document" :size="18" />
            <input id="password" v-model="form.password" class="field-input" type="password" autocomplete="new-password" placeholder="至少 6 位密码" />
          </span>
        </label>

        <label class="field-group" for="confirmPassword">
          <span class="field-label">确认密码</span>
          <span class="field-wrap">
            <AppIcon name="check" :size="18" />
            <input id="confirmPassword" v-model="form.confirmPassword" class="field-input" type="password" autocomplete="new-password" placeholder="再次输入密码" />
          </span>
        </label>

        <p v-if="errorMessage" class="form-error">{{ errorMessage }}</p>

        <button class="btn-submit" type="submit" :disabled="loading">
          <template v-if="loading">
            <span class="spinner" />
            创建中...
          </template>
          <template v-else>
            注册并开始
            <AppIcon name="chevron-right" :size="18" />
          </template>
        </button>

        <div class="auth-switch">
          <span>已有账号？</span>
          <button type="button" @click="router.replace('/login')">去登录</button>
        </div>
      </form>
    </main>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { showToast } from 'vant';
import AppIcon from '@/components/AppIcon.vue';
import { useAuthStore } from '@/stores/auth';

const router = useRouter();
const authStore = useAuthStore();
const loading = ref(false);
const errorMessage = ref('');

const form = reactive({
  nickname: '',
  phone: '',
  password: '',
  confirmPassword: '',
});

function validateForm() {
  if (!form.nickname || !form.phone || !form.password || !form.confirmPassword) return '请完整填写注册信息';
  if (!/^1\d{10}$/.test(form.phone)) return '请输入 11 位手机号';
  if (form.password.length < 6) return '密码至少需要 6 位';
  if (form.password !== form.confirmPassword) return '两次输入的密码不一致';
  return '';
}

async function handleRegister() {
  errorMessage.value = validateForm();
  if (errorMessage.value) return;
  loading.value = true;
  try {
    await authStore.register(form.phone, form.password, form.nickname);
    showToast('注册成功');
    await router.replace('/');
  } catch (error: any) {
    errorMessage.value = error?.response?.data?.message || error?.message || '注册失败，请稍后重试';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.register-page {
  min-height: 100dvh;
  background: var(--color-bg);
}

.register-hero {
  position: relative;
  min-height: 238px;
  padding: 18px var(--space-container) 26px;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(31, 78, 168, 0.96), rgba(45, 91, 209, 0.92) 58%, rgba(35, 130, 96, 0.88));
  color: var(--color-on-primary);
}

.back-btn {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border: 1px solid rgba(248, 250, 255, 0.24);
  border-radius: var(--radius-full);
  background: rgba(248, 250, 255, 0.12);
  color: #f8faff;
}

.hero-copy {
  margin-top: 30px;
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

.hero-stats {
  position: absolute;
  right: 16px;
  bottom: 20px;
  display: grid;
  gap: 8px;
}

.hero-stats div {
  min-width: 86px;
  padding: 10px 12px;
  border: 1px solid rgba(248, 250, 255, 0.2);
  border-radius: 16px;
  background: rgba(248, 250, 255, 0.14);
}

.hero-stats strong,
.hero-stats span {
  display: block;
}

.hero-stats strong {
  color: #fbfcff;
  font-size: 18px;
  line-height: 22px;
}

.hero-stats span {
  color: rgba(248, 250, 255, 0.68);
  font-size: 11px;
}

.register-shell {
  padding: 0 var(--space-container) 28px;
  margin-top: -26px;
}

.register-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
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

.auth-switch {
  display: flex;
  justify-content: center;
  gap: 6px;
  color: var(--color-on-surface-variant);
  font-size: 14px;
}

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
