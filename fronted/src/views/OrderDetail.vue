<!--
  OrderDetail.vue —— 「订单详情」独立页面（下单成功后跳这里）
  功能：从路由参数拿到订单 ID → 调接口拉订单详情 → 完整展示订单信息 + 商品清单 + 收货信息
  代码来源：90% 复用了 OrderList.vue 里的「详情弹窗」代码，避免重复写
-->
<template>
  <div class="order-detail-page">
    <!-- 顶部面包屑（返回按钮 + 页面标题） -->
    <div class="page-header">
      <el-button @click="goBack" :icon="ArrowLeft">返回订单列表</el-button>
      <h2 class="page-title">订单详情</h2>
    </div>

    <!-- 加载中状态（转圈） -->
    <div v-loading="loading" class="detail-container">
      <template v-if="order">
        <!-- ====== 订单状态横幅（顶部大色块，突出显示状态） ====== -->
        <div :class="['status-banner', `status-${order.status}`]">
          <div class="banner-left">
            <el-icon size="32" class="banner-icon">
              <!-- 根据状态显示不同图标：已完成=对勾，待支付=时钟，已发货=货车... -->
              <CircleCheck v-if="order.status === 4" />
              <Clock v-else-if="order.status === 0 || order.status === 1" />
              <Van v-else-if="order.status === 3" />
              <Warning v-else-if="order.status === 5" />
              <Goods v-else />
            </el-icon>
            <div class="banner-text">
              <div class="banner-status-text">
                {{ getStatusText(order.status) }}
              </div>
              <div class="banner-order-no">
                订单号：{{ order.order_no || order.id }}
              </div>
            </div>
          </div>
          <!-- 右侧操作按钮（待支付时显示「立即支付」） -->
          <div class="banner-actions">
            <el-button
              v-if="order.status === 0 || order.status === 1"
              type="primary"
              size="large"
            >
              立即支付
            </el-button>
          </div>
        </div>

        <!-- ====== 收货地址卡片 ====== -->
        <div class="detail-card">
          <h3 class="card-title">收货地址</h3>
          <div class="addr-row">
            <div class="addr-name">{{ order.receiver_name }}</div>
            <div class="addr-phone">{{ order.receiver_phone }}</div>
          </div>
          <div class="addr-detail">
            {{ order.receiver_address }}
          </div>
          <div v-if="order.remark" class="addr-remark">
            <el-tag size="small" type="info">备注</el-tag>
            {{ order.remark }}
          </div>
        </div>

        <!-- ====== 商品清单卡片 ====== -->
        <div class="detail-card">
          <h3 class="card-title">商品清单</h3>
          <div class="detail-goods-list">
            <div
              v-for="item in (order.items || (order as any).order_items)"
              :key="item.id"
              class="detail-goods-item"
            >
              <!-- 商品图 + 名称（左边） -->
              <div class="detail-goods-left" @click="goToProduct(item.product_id)">
                <img
                  :src="item.product?.image_url || PLACEHOLDER_IMG['80x80']"
                  class="detail-goods-img"
                  :alt="item.product_name"
                />
                <div class="detail-goods-meta">
                  <div class="detail-goods-name">{{ item.product_name || '商品名称' }}</div>
                  <div class="detail-goods-price">
                    ¥{{ Number(item.product_price ?? item.price).toFixed(2) }}
                  </div>
                </div>
              </div>
              <!-- 数量 + 小计（右边） -->
              <div class="detail-goods-right">
                <div class="detail-goods-qty">× {{ item.quantity }}</div>
                <div class="detail-goods-subtotal">
                  ¥{{ Number(item.subtotal ?? (item.product_price ?? item.price) * item.quantity).toFixed(2) }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ====== 订单信息 + 金额汇总卡片 ====== -->
        <div class="detail-card summary-card">
          <h3 class="card-title">订单信息</h3>

          <div class="detail-row">
            <span class="detail-label">订单号：</span>
            <span class="detail-value">{{ order.order_no || order.id }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">下单时间：</span>
            <span class="detail-value">{{ formatDate(order.created_at) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">订单状态：</span>
            <el-tag :type="getStatusType(order.status)" effect="light">
              {{ getStatusText(order.status) }}
            </el-tag>
          </div>

          <el-divider />

          <div class="summary-row">
            <span>商品总数：</span>
            <span class="summary-val">{{ getTotalQuantity(order) }} 件</span>
          </div>
          <div class="summary-row">
            <span>商品金额：</span>
            <span class="summary-val">¥{{ Number(order.total_amount).toFixed(2) }}</span>
          </div>
          <div class="summary-row summary-total-row">
            <span>应付金额：</span>
            <span class="summary-total">¥{{ Number(order.total_amount).toFixed(2) }}</span>
          </div>
        </div>
      </template>

      <!-- 空状态 / 加载失败状态 -->
      <div v-else-if="!loading" class="empty-state">
        <el-empty :description="errorMsg || '订单不存在或已被删除'">
          <el-button type="primary" @click="goBack">返回订单列表</el-button>
        </el-empty>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  CircleCheck,
  Clock,
  Van,
  Warning,
  Goods,
} from '@element-plus/icons-vue'
import { getOrderDetail } from '@/api/order'
import { useUserStore } from '@/stores/user'
import { PLACEHOLDER_IMG } from '@/constants/placeholder'
import { ElMessage } from 'element-plus'
import type { Order } from '@/types'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const order = ref<Order | null>(null)
const errorMsg = ref('')

/** 从路由参数拿订单 ID（例如 /orders/12 → 12） */
function getOrderIdFromRoute(): number | null {
  const rawId = route.params.id
  const id = Number(rawId)
  return Number.isNaN(id) || id <= 0 ? null : id
}

/** 调接口加载订单详情 */
async function fetchDetail() {
  const orderId = getOrderIdFromRoute()
  if (!orderId) {
    errorMsg.value = '订单参数无效'
    return
  }
  loading.value = true
  try {
    const res: any = await getOrderDetail(orderId, userStore.userId)
    order.value = res?.data || res
  } catch (e: any) {
    console.error('获取订单详情失败:', e)
    errorMsg.value = e?.response?.data?.msg || '获取订单详情失败'
    ElMessage.error(errorMsg.value)
  } finally {
    loading.value = false
  }
}

// ===== 下面 4 个工具函数完全复用 OrderList.vue 的逻辑 =====
function getStatusText(status: number): string {
  const statusMap: Record<number, string> = {
    0: '待支付',
    1: '待支付',
    2: '已支付',
    3: '已发货',
    4: '已完成',
    5: '已取消',
  }
  return statusMap[status] || '未知状态'
}
function getStatusType(status: number): string {
  const typeMap: Record<number, string> = {
    0: 'warning',
    1: 'warning',
    2: 'primary',
    3: 'info',
    4: 'success',
    5: 'info',
  }
  return typeMap[status] || 'info'
}
function getTotalQuantity(order: Order): number {
  const items = (order as any).items || (order as any).order_items
  if (!items) return 0
  return items.reduce((sum: number, item: any) => sum + item.quantity, 0)
}
function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ===== 跳转相关 =====
function goToProduct(productId: number) {
  router.push(`/products/${productId}`)
}
function goBack() {
  // 如果有历史记录就返回上一页，没有就回订单列表
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/orders')
  }
}

onMounted(() => {
  fetchDetail()
})
</script>

<style scoped>
.order-detail-page {
  padding: 24px 0 100px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}
.detail-container {
  min-height: 500px;
}

/* ====== 顶部状态横幅 ====== */
.status-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 32px;
  border-radius: 8px;
  margin-bottom: 20px;
  color: #fff;
}
.status-banner.status-0,
.status-banner.status-1 {
  background: linear-gradient(135deg, #ff9800 0%, #f56c6c 100%);
}
.status-banner.status-2 {
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
}
.status-banner.status-3 {
  background: linear-gradient(135deg, #909399 0%, #a0cfff 100%);
}
.status-banner.status-4 {
  background: linear-gradient(135deg, #67c23a 0%, #85ce61 100%);
}
.status-banner.status-5 {
  background: linear-gradient(135deg, #606266 0%, #909399 100%);
}
.banner-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.banner-icon {
  opacity: 0.95;
}
.banner-status-text {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.3;
}
.banner-order-no {
  margin-top: 6px;
  font-size: 13px;
  opacity: 0.9;
}

/* ====== 内容卡片（通用） ====== */
.detail-card {
  background: #fff;
  border-radius: 8px;
  padding: 24px 32px;
  margin-bottom: 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}
.card-title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  padding-left: 10px;
  border-left: 3px solid #409eff;
}

/* ====== 收货地址 ====== */
.addr-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
}
.addr-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.addr-phone {
  font-size: 14px;
  color: #606266;
}
.addr-detail {
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  margin-bottom: 8px;
}
.addr-remark {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #909399;
}

/* ====== 商品清单（一行 = 图 + 信息 / 数量 + 小计） ====== */
.detail-goods-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.detail-goods-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}
.detail-goods-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  cursor: pointer;
}
.detail-goods-img {
  width: 72px;
  height: 72px;
  border-radius: 4px;
  object-fit: cover;
  background: #f0f0f0;
  flex-shrink: 0;
}
.detail-goods-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.detail-goods-name {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.detail-goods-price {
  font-size: 13px;
  color: #909399;
}
.detail-goods-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  flex-shrink: 0;
  min-width: 120px;
}
.detail-goods-qty {
  font-size: 13px;
  color: #606266;
}
.detail-goods-subtotal {
  font-size: 16px;
  font-weight: 700;
  color: #f56c6c;
}

/* ====== 订单信息 / 金额汇总 ====== */
.summary-card .detail-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  font-size: 14px;
}
.summary-card .detail-label {
  width: 80px;
  color: #909399;
  text-align: right;
  flex-shrink: 0;
}
.summary-card .detail-value {
  color: #303133;
  flex: 1;
  word-break: break-all;
}
.summary-row {
  display: flex;
  justify-content: flex-end;
  align-items: baseline;
  gap: 8px;
  padding: 6px 0;
  font-size: 14px;
  color: #606266;
}
.summary-val {
  color: #303133;
}
.summary-total-row {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}
.summary-total {
  font-size: 24px;
  font-weight: 700;
  color: #f56c6c;
}

/* ====== 空状态 ====== */
.empty-state {
  padding: 100px 0;
}
</style>