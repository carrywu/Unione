<template>
  <div class="page">
    <PageHeader />
    <div class="panel list-panel">
      <div class="toolbar">
        <el-select v-model="bankId" class="bank-select" placeholder="选择题库" @change="fetchMaterials">
          <el-option v-for="bank in banks" :key="bank.id" :label="bank.name" :value="bank.id" />
        </el-select>
      </div>
      <el-table v-loading="loading" :data="materials" row-key="id">
        <el-table-column label="材料内容" min-width="360" show-overflow-tooltip>
          <template #default="{ row }">
            <MathText :text="row.content" fallback="材料内容缺失" />
          </template>
        </el-table-column>
        <el-table-column prop="question_count" label="子题数" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="190">
          <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" title="编辑材料" width="760px">
      <el-input v-model="form.content" type="textarea" :rows="12" />
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';
import { getBanks, type Bank } from '@/api/bank';
import { deleteMaterial, getMaterials, updateMaterial, type Material } from '@/api/material';
import MathText from '@/components/MathText.vue';
import PageHeader from '@/components/PageHeader.vue';

const loading = ref(false);
const dialogVisible = ref(false);
const banks = ref<Bank[]>([]);
const bankId = ref('');
const materials = ref<Material[]>([]);
const form = reactive<Partial<Material>>({});

async function fetchMaterials() {
  if (!bankId.value) return;
  loading.value = true;
  try {
    materials.value = (await getMaterials({ bank_id: bankId.value, page: 1, pageSize: 100 })).list;
  } finally {
    loading.value = false;
  }
}

function openEdit(material: Material) {
  Object.keys(form).forEach((key) => delete form[key as keyof Material]);
  Object.assign(form, material);
  dialogVisible.value = true;
}

async function handleSave() {
  if (!form.id) return;
  await updateMaterial(form.id, { content: form.content, images: form.images });
  ElMessage.success('已保存');
  dialogVisible.value = false;
  await fetchMaterials();
}

async function handleDelete(id: string) {
  await ElMessageBox.confirm('删除材料会解绑关联子题，确认继续？', '删除材料', { type: 'warning' });
  const result = await deleteMaterial(id);
  ElMessage.success(`已删除，解绑 ${result.unlinked_questions} 道题`);
  await fetchMaterials();
}

onMounted(async () => {
  banks.value = (await getBanks({ page: 1, pageSize: 100 })).list;
  bankId.value = banks.value[0]?.id || '';
  await fetchMaterials();
});
</script>

<style scoped>
.list-panel {
  padding: 16px;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.bank-select {
  width: 320px;
}
</style>
