<template>
  <div class="page">
    <PageHeader />
    <div class="panel form-panel">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="题库名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="科目" prop="subject">
          <el-select v-model="form.subject" class="full">
            <el-option label="行测" value="行测" />
            <el-option label="申论" value="申论" />
            <el-option label="公基" value="公基" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源机构" prop="source">
          <el-input v-model="form.source" />
        </el-form-item>
        <el-form-item label="年份" prop="year">
          <el-input-number v-model="form.year" :min="2000" :max="2100" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleSubmit">提交</el-button>
          <el-button @click="router.push('/banks')">取消</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FormInstance, FormRules } from 'element-plus';
import { ElMessage } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { createBank, getBankDetail, updateBank } from '@/api/bank';
import PageHeader from '@/components/PageHeader.vue';

const route = useRoute();
const router = useRouter();
const formRef = ref<FormInstance>();
const loading = ref(false);
const bankId = String(route.params.id || '');
const form = reactive({
  name: '',
  subject: '行测',
  source: '',
  year: new Date().getFullYear(),
});
const rules: FormRules = {
  name: [{ required: true, message: '请输入题库名称', trigger: 'blur' }],
  subject: [{ required: true, message: '请选择科目', trigger: 'change' }],
  year: [{ required: true, message: '请输入年份', trigger: 'change' }],
};

async function loadDetail() {
  if (!bankId) return;
  const bank = await getBankDetail(bankId);
  Object.assign(form, {
    name: bank.name,
    subject: bank.subject,
    source: bank.source,
    year: bank.year,
  });
}

async function handleSubmit() {
  await formRef.value?.validate();
  loading.value = true;
  try {
    if (bankId) {
      await updateBank(bankId, form);
      ElMessage.success('已保存');
    } else {
      await createBank(form);
      ElMessage.success('已创建');
    }
    await router.push('/banks');
  } finally {
    loading.value = false;
  }
}

onMounted(loadDetail);
</script>

<style scoped>
.form-panel {
  width: 640px;
  padding: 24px;
}

.full {
  width: 100%;
}
</style>
