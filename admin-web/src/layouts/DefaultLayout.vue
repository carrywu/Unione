<template>
  <el-container class="layout">
    <el-aside width="248px" class="sidebar">
      <div class="brand">
        <div class="brand-mark">考</div>
        <div>
          <div class="brand-title">刷题管理</div>
          <div class="brand-subtitle">题库解析与审核</div>
        </div>
      </div>
      <el-menu router :default-active="route.path" class="menu">
        <el-menu-item index="/dashboard">
          <el-icon><DataBoard /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/banks">
          <el-icon><Collection /></el-icon>
          <span>题库管理</span>
        </el-menu-item>
        <el-menu-item index="/materials">
          <el-icon><Document /></el-icon>
          <span>材料管理</span>
        </el-menu-item>
        <el-menu-item index="/pdf/tasks">
          <el-icon><Upload /></el-icon>
          <span>解析任务</span>
        </el-menu-item>
        <el-menu-item index="/workbench">
          <el-icon><EditPen /></el-icon>
          <span>沉浸式制卷</span>
        </el-menu-item>
        <el-menu-item index="/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item index="/system">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-title">
          <span>{{ route.meta.title || '管理后台' }}</span>
          <small>{{ routeHint }}</small>
        </div>
        <div class="user">
          <span class="user-chip">{{ nickname }}</span>
          <el-button text :icon="SwitchButton" @click="handleLogout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Collection, DataBoard, Document, EditPen, Setting, SwitchButton, Upload, User } from '@element-plus/icons-vue';
import { useAuthStore } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const nickname = computed(() => String(authStore.userInfo?.nickname || '管理员'));
const routeHint = computed(() => {
  if (route.path.includes('/review')) return '题库审核工作流';
  if (route.path.includes('/upload')) return 'PDF 顺序解析';
  if (route.path.includes('/questions')) return '题目维护';
  return '后台工作台';
});

async function handleLogout() {
  await authStore.logout();
  await router.replace('/login');
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
  background: var(--admin-bg);
}

.layout :deep(.el-container) {
  min-width: 0;
}

.sidebar {
  border-right: 1px solid var(--admin-border);
  background:
    linear-gradient(180deg, oklch(99% 0.006 248) 0%, oklch(96.6% 0.014 248) 100%);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 76px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--admin-border);
  color: var(--admin-text);
}

.brand-mark {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border: 1px solid oklch(79% 0.08 248);
  border-radius: 8px;
  background: var(--admin-accent);
  color: oklch(98.5% 0.006 248);
  font-weight: 800;
}

.brand-title {
  font-size: 17px;
  font-weight: 750;
  line-height: 1.25;
}

.brand-subtitle {
  margin-top: 3px;
  color: var(--admin-text-faint);
  font-size: 12px;
}

.menu {
  border-right: 0;
  padding: 12px;
  background: transparent;
}

.menu :deep(.el-menu-item) {
  height: 42px;
  margin-bottom: 4px;
  border-radius: 8px;
  color: var(--admin-text-muted);
}

.menu :deep(.el-menu-item:hover) {
  background: var(--admin-accent-soft);
  color: var(--admin-accent);
}

.menu :deep(.el-menu-item.is-active) {
  background: oklch(93.5% 0.045 248);
  color: var(--admin-accent);
  font-weight: 700;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  border-bottom: 1px solid var(--admin-border);
  background: rgb(252 253 255 / 88%);
  backdrop-filter: blur(12px);
}

.header-title {
  display: flex;
  flex-direction: column;
  gap: 3px;
  color: var(--admin-text);
  font-weight: 700;
}

.header-title small {
  color: var(--admin-text-faint);
  font-size: 12px;
  font-weight: 500;
}

.user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-chip {
  padding: 5px 10px;
  border: 1px solid var(--admin-border);
  border-radius: 999px;
  background: var(--admin-surface);
  color: var(--admin-text-muted);
  font-size: 13px;
}

.main {
  padding: 0;
  background: transparent;
  min-width: 0;
}

@media (max-width: 920px) {
  .sidebar {
    width: 76px !important;
  }

  .brand {
    justify-content: center;
    padding: 14px 10px;
  }

  .brand-title,
  .brand-subtitle,
  .menu :deep(.el-menu-item span) {
    display: none;
  }

  .menu {
    padding: 10px;
  }

  .menu :deep(.el-menu-item) {
    justify-content: center;
    padding: 0;
  }

  .header {
    padding: 0 14px;
  }

  .header-title small,
  .user-chip {
    display: none;
  }
}
</style>
