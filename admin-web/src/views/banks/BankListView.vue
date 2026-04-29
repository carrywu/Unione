<template>
  <div class="page">
    <PageHeader />
    <div class="panel list-panel">
      <div class="toolbar">
        <el-button type="primary" @click="router.push('/banks/create')">新建题库</el-button>
        <el-input
          v-model="query.keyword"
          class="search"
          clearable
          placeholder="搜索题库名称"
          @keyup.enter="fetchBanks"
          @clear="fetchBanks"
        />
        <el-button @click="fetchBanks">搜索</el-button>
      </div>

      <el-table v-loading="loading" :data="banks" row-key="id">
        <el-table-column prop="name" label="题库名称" min-width="220">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/banks/${row.id}/questions`)">
              {{ row.name }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column prop="subject" label="科目" width="110" />
        <el-table-column prop="source" label="来源机构" width="140" />
        <el-table-column prop="year" label="年份" width="100" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <StatusTag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column prop="total_count" label="题目数" width="100" />
        <el-table-column label="操作" width="380" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/banks/${row.id}/edit`)">编辑</el-button>
            <el-button link type="primary" @click="router.push(`/banks/${row.id}/upload`)">上传 PDF</el-button>
            <el-button link type="primary" @click="router.push(`/banks/${row.id}/answer-book`)">解析册匹配</el-button>
            <el-button link type="success" @click="handlePublish(row.id)">发布</el-button>
            <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.pageSize"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="fetchBanks"
          @size-change="fetchBanks"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus';
import { onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { deleteBank, getBanks, publishBank, type Bank } from '@/api/bank';
import PageHeader from '@/components/PageHeader.vue';
import StatusTag from '@/components/StatusTag.vue';

const router = useRouter();
const loading = ref(false);
const banks = ref<Bank[]>([]);
const total = ref(0);
const query = reactive({
  page: 1,
  pageSize: 10,
  keyword: '',
});

async function fetchBanks() {
  loading.value = true;
  try {
    const result = await getBanks(query);
    banks.value = result.list;
    total.value = result.total;
  } finally {
    loading.value = false;
  }
}

async function handlePublish(id: string) {
  await ElMessageBox.confirm('确认发布该题库？', '发布题库', { type: 'warning' });
  await publishBank(id);
  ElMessage.success('已发布');
  await fetchBanks();
}

async function handleDelete(id: string) {
  await ElMessageBox.confirm('确认删除该题库？', '删除题库', { type: 'warning' });
  await deleteBank(id);
  ElMessage.success('已删除');
  await fetchBanks();
}

onMounted(fetchBanks);
</script>

<style scoped>
.list-panel {
  padding: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.search {
  width: 260px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
