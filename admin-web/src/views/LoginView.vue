<template>
  <div class="login-page">
    <el-form ref="formRef" :model="form" :rules="rules" class="login-panel" label-position="top">
      <h1>刷题管理后台</h1>
      <el-form-item label="手机号" prop="phone">
        <el-input v-model="form.phone" size="large" />
      </el-form-item>
      <el-form-item label="密码" prop="password">
        <el-input v-model="form.password" size="large" type="password" show-password />
      </el-form-item>
      <el-button type="primary" size="large" class="login-button" :loading="loading" @click="handleLogin">
        登录
      </el-button>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus';
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const router = useRouter();
const authStore = useAuthStore();
const formRef = ref<FormInstance>();
const loading = ref(false);
const form = reactive({
  phone: '',
  password: '',
});
const rules: FormRules = {
  phone: [{ required: true, message: '请输入手机号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
};

async function handleLogin() {
  await formRef.value?.validate();
  loading.value = true;
  try {
    await authStore.login(form.phone, form.password);
    await router.replace('/dashboard');
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  background: #eef2f7;
}

.login-panel {
  width: 380px;
  padding: 28px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 18px 40px rgb(15 23 42 / 8%);
}

.login-panel h1 {
  margin: 0 0 24px;
  font-size: 24px;
  letter-spacing: 0;
}

.login-button {
  width: 100%;
}
</style>
