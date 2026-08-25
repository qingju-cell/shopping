<template>
  <div class="profile-page">
    <h2 class="page-title">个人中心</h2>

    <div class="profile-container">
      <!-- 用户信息卡片 -->
      <div class="user-card">
        <div class="user-avatar-section">
          <el-avatar :size="80" class="big-avatar">
            {{ userStore.userInfo?.username?.charAt(0) || 'U' }}
          </el-avatar>
          <h3 class="username">{{ userStore.userInfo?.username || '用户' }}</h3>
          <p class="user-id">ID: {{ userStore.userId }}</p>
        </div>

        <div class="user-details">
          <div class="detail-item">
            <span class="detail-label">用户名</span>
            <span class="detail-value">{{ userStore.userInfo?.username || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">邮箱</span>
            <span class="detail-value">{{ userStore.userInfo?.email || '未设置' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">手机号</span>
            <span class="detail-value">{{ userStore.userInfo?.phone || '未设置' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">注册时间</span>
            <span class="detail-value">{{ formatDate(userStore.userInfo?.create_at) }}</span>
          </div>
        </div>
      </div>

      <!-- 快捷入口 -->
      <div class="quick-actions">
        <h3 class="section-title">快捷入口</h3>
        <div class="action-grid">
          <div class="action-item" @click="goToOrders">
            <div class="action-icon order-icon">
              <el-icon><List /></el-icon>
            </div>
            <span class="action-text">我的订单</span>
          </div>

          <div class="action-item" @click="goToCart">
            <div class="action-icon cart-icon">
              <el-icon><ShoppingCart /></el-icon>
            </div>
            <span class="action-text">购物车</span>
          </div>

          <div class="action-item" @click="goToProducts">
            <div class="action-icon shop-icon">
              <el-icon><Goods /></el-icon>
            </div>
            <span class="action-text">商品商城</span>
          </div>
        </div>
      </div>

      <!-- 账户操作 -->
      <div class="account-actions">
        <h3 class="section-title">账户操作</h3>
        <div class="action-list">
          <el-button type="danger" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出登录
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { List, ShoppingCart, Goods, SwitchButton } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()

function formatDate(dateStr?: string): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

function goToOrders() {
  router.push('/orders')
}

function goToCart() {
  router.push('/cart')
}

function goToProducts() {
  router.push('/products')
}
async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    userStore.logout()
    router.push('/login')
  } catch {
    // 用户取消
  }
}

onMounted(() => {
  // 如果有用户ID，刷新用户信息
  if (userStore.userId) {
    userStore.fetchUserInfo(userStore.userId)
  }
})
</script>

<style scoped>
.profile-page {
  padding: 24px 0;
}

.page-title {
  margin: 0 0 20px;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.profile-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.user-card {
  display: flex;
  gap: 40px;
  background: #fff;
  border-radius: 8px;
  padding: 32px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.user-avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  min-width: 160px;
  padding-right: 40px;
  border-right: 1px solid #ebeef5;
}

.big-avatar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  font-size: 32px;
  font-weight: 600;
}

.username {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}
.user-id {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.user-details {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 16px;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 16px;
}

.detail-label {
  min-width: 80px;
  font-size: 14px;
  color: #909399;
}

.detail-value {
  font-size: 14px;
  color: #303133;
}

.quick-actions,
.account-actions {
  background: #fff;
  border-radius: 8px;
  padding: 24px 32px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}
.section-title {
  margin: 0 0 20px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  max-width: 480px;
}

.action-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 24px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  background: #fafafa;
}

.action-item:hover {
  background: #f0f7ff;
  transform: translateY(-2px);
}
.action-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #fff;
}

.order-icon {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.cart-icon {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.shop-icon {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.action-text {
  font-size: 14px;
  color: #606266;
}
.action-list {
  display: flex;
  gap: 16px;
}
</style>
