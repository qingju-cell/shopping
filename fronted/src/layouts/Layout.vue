<template>
  <div class="layout">
    <!-- 顶部导航 -->
    <header class="header">
      <div class="header-content">
        <div class="logo" @click="goHome">
          <h1>🛒 购物系统</h1>
        </div>

        <nav class="nav-menu">
          <router-link to="/products" class="nav-link">
            <el-icon><Goods /></el-icon>
            商品商城
          </router-link>
          <router-link v-if="userStore.isAdmin" to="/admin/products" class="nav-link admin-link">
            <el-icon><Setting /></el-icon>
            后台管理
          </router-link>
        </nav>

        <div class="header-right">
          <!-- 搜索框 -->
          <div class="search-box">
            <el-input
              v-model="searchKeyword"
              placeholder="搜索商品..."
              size="default"
              clearable
              @keyup.enter="handleSearch"
              @clear="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </div>
                   <!-- 购物车 -->
          <router-link to="/cart" class="cart-link">
            <el-badge :value="cartStore.totalCount" :hidden="cartStore.totalCount === 0" class="cart-badge">
              <el-icon class="cart-icon"><ShoppingCart /></el-icon>
            </el-badge>
            <span>购物车</span>
          </router-link>

          <!-- 用户菜单 -->
          <el-dropdown v-if="userStore.isLoggedIn" @command="handleUserCommand">
            <div class="user-info">
              <el-avatar :size="32" :class="['user-avatar', userStore.isAdmin ? 'admin-avatar' : '']">
                {{ userStore.userInfo?.username?.charAt(0) || 'U' }}
              </el-avatar>
              <div class="username-wrap">
                <span class="username">{{ userStore.userInfo?.username || '用户' }}</span>
                <el-tag v-if="userStore.isAdmin" type="danger" size="small" effect="dark" class="admin-tag">管理员</el-tag>
              </div>
              <el-icon class="arrow-icon"><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>
                  个人中心
                </el-dropdown-item>
                <el-dropdown-item command="orders">
                  <el-icon><List /></el-icon>
                  我的订单
                </el-dropdown-item>
                <el-dropdown-item v-if="userStore.isAdmin" command="admin">
                  <el-icon><Setting /></el-icon>
                  管理后台
                </el-dropdown-item>
                <el-dropdown-item divided command="logout">
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

            <div v-else class="auth-links">
            <router-link to="/login" class="auth-link">登录</router-link>
            <span class="divider">|</span>
            <router-link to="/register" class="auth-link">注册</router-link>
          </div>
        </div>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="main">
      <div class="container">
        <router-view />
      </div>
    </main>

    <!-- 页脚 -->
    <footer class="footer">
      <div class="footer-content">
        <p>© 2024 购物系统 - 前端演示项目</p>
      </div>
    </footer>

    <!-- AI 智能客服悬浮窗（右下角） -->
    <AIChatWidget />
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useCartStore } from '@/stores/cart'
import AIChatWidget from '@/components/AIChatWidget.vue'
import {
  Search,
  ShoppingCart,
  User,
  Goods,
  ArrowDown,
  List,
  SwitchButton,
  Setting
} from '@element-plus/icons-vue'


const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const cartStore = useCartStore()

const searchKeyword = ref('')

function goHome() {
  router.push('/products')
}

function handleSearch() {
  router.push({
    path: '/products',
    query: { keyword: searchKeyword.value }
  })
}
function handleUserCommand(command: string) {
  switch (command) {
    case 'profile':
      router.push('/profile')
      break
    case 'orders':
      router.push('/orders')
      break
    case 'admin':
      router.push('/admin/products')
      break
    case 'logout':
      userStore.logout()
      router.push('/login')
      break
  }
}

onMounted(() => {
  // 初始化用户信息
  userStore.initUserInfo()

  // 如果已登录，加载购物车
  if (userStore.isLoggedIn) {
    cartStore.fetchCart()
  }

  // 从 URL 获取搜索关键词
  if (route.query.keyword) {
    searchKeyword.value = String(route.query.keyword)
  }
})
</script>
<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.header {
  position: sticky;
  top: 0;
  z-index: 1000;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 40px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}
.logo {
  cursor: pointer;
}

.logo h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  white-space: nowrap;
}

.nav-menu {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  margin-left: 40px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  color: #606266;
  text-decoration: none;
  font-size: 15px;
  border-radius: 6px;
  transition: all 0.3s;
}

.nav-link:hover,
.nav-link.router-link-active {
  color: #409eff;
  background: #ecf5ff;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 24px;
}

.search-box {
  width: 280px;
}

.cart-link {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #606266;
  text-decoration: none;
  font-size: 14px;
  transition: color 0.3s;
}

.cart-link:hover {
  color: #409eff;
}

.cart-icon {
  font-size: 20px;
}

.cart-badge {
  display: flex;
  align-items: center;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background-color 0.3s;
}

.user-info:hover {
  background: #f5f7fa;
}

.user-avatar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  font-weight: 600;
}
.admin-avatar {
  background: linear-gradient(135deg, #f56c6c 0%, #c0392b 100%);
}

.username-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  line-height: 1;
}

.username {
  font-size: 14px;
  color: #303133;
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-tag {
  font-size: 10px;
  padding: 0 4px;
  height: 14px;
  line-height: 12px;
  border-radius: 3px;
  margin-top: 1px;
}

.admin-link {
  color: #f56c6c !important;
  font-weight: 600;
}
.admin-link:hover,
.admin-link.router-link-active {
  background: #fef0f0 !important;
  color: #f56c6c !important;
}

.arrow-icon {
  font-size: 12px;
  color: #909399;
}

.auth-links {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.auth-link {
  color: #606266;
  text-decoration: none;
  transition: color 0.3s;
}

.auth-link:hover {
  color: #409eff;
}

.divider {
  color: #dcdfe6;
}

.main {
  flex: 1;
  background: #f5f7fa;
}

.container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 40px;
}

.footer {
  background: #fff;
  border-top: 1px solid #ebeef5;
  padding: 24px 0;
}

.footer-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 40px;
  text-align: center;
}
.footer-content p {
  margin: 0;
  font-size: 13px;
  color: #909399;
}
</style>