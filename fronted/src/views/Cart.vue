<template>
  <div class="cart-page">
    <h2 class="page-title">我的购物车</h2>

    <div v-loading="cartStore.loading" class="cart-container">
      <!-- 购物车列表 -->
      <div v-if="cartStore.cartItems.length > 0" class="cart-content">
        <div class="cart-header">
          <el-checkbox v-model="allSelected" @change="toggleSelectAll">全选</el-checkbox>
          <span class="header-name">商品</span>
          <span class="header-price">单价</span>
          <span class="header-quantity">数量</span>
          <span class="header-subtotal">小计</span>
          <span class="header-action">操作</span>
        </div>

        <div class="cart-items">
          <div
            v-for="item in cartStore.cartItems"
            :key="item.id"
            class="cart-item"
          >
            <el-checkbox v-model="selectedIds" :value="item.id" />

            <div class="item-info" @click="goToProduct(item.product_id)">
              <div class="item-image">
                <img
                  :src="item.product_image || PLACEHOLDER_IMG['80x80']"
                  :alt="item.product_name"
                />
              </div>
              <div class="item-name">{{ item.product_name || '商品名称' }}</div>
            </div>

            <div class="item-price">
              ¥{{ Number(item.product_price || 0).toFixed(2) }}
            </div>
                     <div class="item-quantity">
              <el-input-number
                v-model="item.quantity"
                :min="1"
                :max="999"
                size="small"
                @change="handleQuantityChange(item.id, item.quantity)"
              />
            </div>

            <div class="item-subtotal">
              ¥{{ Number(item.subtotal || 0).toFixed(2) }}
            </div>

            <div class="item-action">
              <el-button
                type="danger"
                text
                size="small"
                @click="handleRemove(item.id)"
              >
                删除
              </el-button>
            </div>
          </div>
        </div>
      </div>


      <!-- 空购物车 -->
      <div v-else class="empty-cart">
        <el-empty description="购物车空空如也">
          <el-button type="primary" @click="goShopping">去逛逛</el-button>
        </el-empty>
      </div>

      <!-- 结算栏 -->
      <div v-if="cartStore.cartItems.length > 0" class="cart-footer">
        <div class="footer-left">
          <el-checkbox v-model="allSelected" @change="toggleSelectAll">全选</el-checkbox>
          <el-button type="text" class="delete-selected" @click="handleBatchDelete">
            删除选中
          </el-button>
        </div>

        <div class="footer-right">
          <div class="total-info">
            <span>已选 <em class="count">{{ selectedCount }}</em> 件商品</span>
            <span class="total-label">合计：</span>
            <span class="total-price">¥{{ selectedTotalPrice.toFixed(2) }}</span>
          </div>
          <el-button
            type="danger"
            size="large"
            class="checkout-btn"
            :disabled="selectedCount === 0"
            @click="handleCheckout"
          >
              去结算
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useCartStore } from '@/stores/cart'
import { PLACEHOLDER_IMG } from '@/constants/placeholder'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const cartStore = useCartStore()

const selectedIds = ref<number[]>([])
const allSelected = computed({
  get() {
    return cartStore.cartItems.length > 0 && selectedIds.value.length === cartStore.cartItems.length
  },
  set(value: boolean) {
    if (value) {
      selectedIds.value = cartStore.cartItems.map(item => item.id)
    } else {
      selectedIds.value = []
    }
  }
})

const selectedCount = computed(() => selectedIds.value.length)

const selectedTotalPrice = computed(() => {
  const list = Array.isArray(cartStore.cartItems) ? cartStore.cartItems : []
  return list
    .filter(item => selectedIds.value.includes(item.id))
    .reduce((sum, item) => sum + Number(item.subtotal || 0), 0)
})
function toggleSelectAll() {
  // 通过 computed 的 setter 处理
}

async function handleQuantityChange(cartItemId: number, quantity: number) {
  await cartStore.updateQuantity(cartItemId, quantity)
}

async function handleRemove(cartItemId: number) {
  try {
    await ElMessageBox.confirm('确定要删除该商品吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await cartStore.removeItem(cartItemId)
    // 从选中列表移除
    selectedIds.value = selectedIds.value.filter(id => id !== cartItemId)
  } catch {
    // 用户取消
  }
  }

async function handleBatchDelete() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择要删除的商品')
    return
  }

  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedIds.value.length} 件商品吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    for (const id of selectedIds.value) {
      await cartStore.removeItem(id)
    }
    selectedIds.value = []
  } catch {
    // 用户取消
  }
}

function goToProduct(productId: number) {
  router.push(`/products/${productId}`)
}
function goShopping() {
  router.push('/products')
}

function handleCheckout() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择要结算的商品')
    return
  }

  // 将选中的商品 ID 传递给订单确认页
  router.push({
    path: '/order-confirm',
    query: {
      cart_item_ids: selectedIds.value.join(',')
    }
  })
}

onMounted(() => {
  cartStore.fetchCart()
})
// 监听购物车变化，同步选中状态
watch(
  () => cartStore.cartItems,
  (items) => {
    // 保留仍存在的选中项
    const validIds = items.map(item => item.id)
    selectedIds.value = selectedIds.value.filter(id => validIds.includes(id))
  },
  { deep: true }
)
</script>

<style scoped>
.cart-page {
  padding: 24px 0;
}

.page-title {
  margin: 0 0 20px;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}
.cart-container {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  min-height: 400px;
}

.cart-content {
  padding: 0 20px;
}

.cart-header {
  display: grid;
  grid-template-columns: 50px 1fr 120px 160px 120px 80px;
  align-items: center;
  padding: 16px 0;
  border-bottom: 1px solid #ebeef5;
  font-size: 14px;
  color: #909399;
  font-weight: 500;
}

.header-name {
  padding-left: 20px;
}
.header-price,
.header-quantity,
.header-subtotal,
.header-action {
  text-align: center;
}

.cart-items {
  min-height: 300px;
}

.cart-item {
  display: grid;
  grid-template-columns: 50px 1fr 120px 160px 120px 80px;
  align-items: center;
  padding: 20px 0;
  border-bottom: 1px solid #f2f6fc;
  transition: background-color 0.3s;
}
.cart-item:hover {
  background-color: #fafafa;
}

.item-info {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-left: 20px;
  cursor: pointer;
}

.item-image {
  width: 80px;
  height: 80px;
  border-radius: 4px;
  overflow: hidden;
  background: #f5f5f5;
  flex-shrink: 0;
}

.item-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.item-name {
  font-size: 14px;
  color: #303133;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.item-price,
.item-quantity,
.item-subtotal,
.item-action {
  text-align: center;
}

.item-price {
  font-size: 14px;
  color: #606266;
}

.item-subtotal {
  font-size: 16px;
  font-weight: 600;
  color: #f56c6c;
}

.item-action {
  display: flex;
  justify-content: center;
}
.empty-cart {
  padding: 80px 0;
}

.cart-footer {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: #fff;
  border-top: 1px solid #ebeef5;
  border-radius: 0 0 8px 8px;
}
.footer-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.delete-selected {
  color: #909399;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.total-info {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 14px;
  color: #606266;
}
.total-info .count {
  color: #f56c6c;
  font-style: normal;
  font-weight: 600;
  margin: 0 2px;
}

.total-label {
  margin-left: 16px;
}

.total-price {
  font-size: 24px;
  font-weight: 700;
  color: #f56c6c;
}

.checkout-btn {
  width: 120px;
  height: 44px;
  font-size: 16px;
}
</style>