<template>
  <div class="product-detail" v-loading="loading">
    <div v-if="product" class="detail-container">
      <div class="product-gallery">
        <div class="main-image">
          <img
            :src="product.image_url || PLACEHOLDER_IMG['500x500']"
            :alt="product.name"
          />
        </div>
      </div>

      <div class="product-info">
        <h1 class="product-title">{{ product.name }}</h1>

        <div class="product-price-section">
          <span class="price-label">售价</span>
          <span class="price-value">¥{{ Number(product.price).toFixed(2) }}</span>
        </div>

        <div class="product-meta">
          <div class="meta-item">
            <span class="meta-label">库存：</span>
            <span class="meta-value">{{ product.stock }} 件</span>
          </div>
          <div class="meta-item" v-if="product.category">
            <span class="meta-label">分类：</span>
            <span class="meta-value">{{ product.category.name }}</span>
          </div>
        </div>

        <div class="product-description">
          <h3>商品描述</h3>
          <p>{{ product.description || '暂无商品描述' }}</p>
        </div>
                <div class="quantity-section">
          <span class="quantity-label">数量</span>
          <el-input-number
            v-model="quantity"
            :min="1"
            :max="product.stock || 99"
            size="large"
          />
        </div>

        <div class="action-buttons">
          <el-button
            size="large"
            type="primary"
            class="add-cart-btn"
            :loading="cartStore.loading"
            @click="handleAddToCart"
          >
            <el-icon><ShoppingCart /></el-icon>
            加入购物车
          </el-button>
          <el-button
            size="large"
            type="danger"
            class="buy-now-btn"
            @click="handleBuyNow"
          >
            立即购买
          </el-button>
        </div>
      </div>
    </div>

    <div v-if="!loading && !product" class="empty-state">
      <el-empty description="商品不存在" />
      <el-button type="primary" @click="goBack">返回列表</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ShoppingCart } from '@element-plus/icons-vue'
import { getProductDetail } from '@/api/product'
import { useCartStore } from '@/stores/cart'
import { PLACEHOLDER_IMG } from '@/constants/placeholder'
import type { Product } from '@/types'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const cartStore = useCartStore()

const loading = ref(false)
const product = ref<Product | null>(null)
const quantity = ref(1)
async function fetchProductDetail() {
  const productId = Number(route.params.id)
  if (!productId) return

  loading.value = true
  try {
    const res: any = await getProductDetail(productId)
    product.value = res.data || res
  } catch (error) {
    console.error('获取商品详情失败:', error)
  } finally {
    loading.value = false
  }
}

async function handleAddToCart() {
  if (!product.value) return

  const success = await cartStore.addItem(product.value.id, quantity.value)
  if (success) {
    // 可选：添加成功后跳转到购物车
  }
}

function handleBuyNow() {
  if (!product.value) return

  // 立即购买：先加入购物车，再跳转到订单确认页
  ElMessage.info('正在跳转到结算页面...')


  // 可以通过路由传参传递商品信息
  router.push({
    path: '/order-confirm',
    query: {
      product_id: product.value.id,
      quantity: quantity.value
    }
  })
}

function goBack() {
  router.push('/products')
}

onMounted(() => {
  fetchProductDetail()
})
</script>

<style scoped>
.product-detail {
  padding: 24px 0;
  min-height: 600px;
}

.detail-container {
  display: grid;
  grid-template-columns: 480px 1fr;
  gap: 40px;
  background: #fff;
  padding: 32px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.product-gallery {
  position: sticky;
  top: 24px;
}

.main-image {
  width: 100%;
  height: 480px;
  border-radius: 8px;
  overflow: hidden;
  background: #f5f5f5;
}

.main-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.product-info {
  display: flex;
  flex-direction: column;
}

.product-title {
  margin: 0 0 16px;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  line-height: 1.4;
}

.product-price-section {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 20px;
  background: linear-gradient(135deg, #fff5f5 0%, #ffe8e8 100%);
  border-radius: 8px;
  margin-bottom: 24px;
}

.price-label {
  font-size: 14px;
  color: #909399;
}

.price-value {
  font-size: 36px;
  font-weight: 700;
  color: #f56c6c;
}

.product-meta {
  display: flex;
  gap: 32px;
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid #ebeef5;
}

.meta-item {
  display: flex;
  align-items: center;
}

.meta-label {
  font-size: 14px;
  color: #909399;
}

.meta-value {
  font-size: 14px;
  color: #303133;
}

.product-description {
  margin-bottom: 32px;
}

.product-description h3 {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.product-description p {
  margin: 0;
  font-size: 14px;
  color: #606266;
  line-height: 1.8;
}

.quantity-section {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
}

.quantity-label {
  font-size: 14px;
  color: #606266;
}

.action-buttons {
  display: flex;
  gap: 16px;
  margin-top: auto;
}
.add-cart-btn,
.buy-now-btn {
  flex: 1;
  height: 48px;
  font-size: 16px;
}

.empty-state {
  text-align: center;
  padding: 80px 0;
}

.empty-state .el-button {
  margin-top: 20px;
}

@media (max-width: 960px) {
  .detail-container {
    grid-template-columns: 1fr;
  }

  .main-image {
    height: 360px;
  }
}
</style>