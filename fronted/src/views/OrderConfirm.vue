<template>
  <div class="order-confirm">
    <h2 class="page-title">确认订单</h2>

    <div v-loading="loading" class="confirm-container">
      <!-- 收货地址 -->
      <div class="section">
        <h3 class="section-title">收货地址</h3>
        <el-form
          ref="formRef"
          :model="addressForm"
          :rules="addressRules"
          label-width="80px"
          class="address-form"
        >
          <el-form-item label="收货人" prop="receiver_name">
            <el-input v-model="addressForm.receiver_name" placeholder="请输入收货人姓名" />
          </el-form-item>
          <el-form-item label="手机号" prop="receiver_phone">
            <el-input v-model="addressForm.receiver_phone" placeholder="请输入手机号" />
          </el-form-item>
          <el-form-item label="收货地址" prop="receiver_address">
            <el-input
              v-model="addressForm.receiver_address"
              type="textarea"
              :rows="2"
              placeholder="请输入详细收货地址"
            />
          </el-form-item>
        </el-form>
      </div>
       <!-- 商品清单 -->
      <div class="section">
        <h3 class="section-title">商品清单</h3>
        <div class="goods-list">
          <div
            v-for="item in orderItems"
            :key="item.product_id"
            class="goods-item"
          >
            <div class="goods-image">
              <img
                :src="item.product?.image_url || PLACEHOLDER_IMG['80x80']"
                :alt="item.product?.name"
              />
            </div>
            <div class="goods-info">
              <div class="goods-name">{{ item.product?.name || '商品名称' }}</div>
              <div class="goods-price">¥{{ Number(item.product?.price || 0).toFixed(2) }}</div>
            </div>
            <div class="goods-quantity">x{{ item.quantity }}</div>
            <div class="goods-subtotal">
              ¥{{ (Number(item.product?.price || 0) * item.quantity).toFixed(2) }}
            </div>
          </div>
        </div>
      </div>
           <!-- 订单备注 -->
      <div class="section">
        <h3 class="section-title">订单备注</h3>
        <el-input
          v-model="addressForm.remark"
          type="textarea"
          :rows="3"
          placeholder="选填，可填写您的特殊需求"
        />
      </div>

      <!-- 价格汇总 -->
      <div class="section summary-section">
        <div class="summary-row">
          <span class="summary-label">商品总数：</span>
          <span class="summary-value">{{ totalQuantity }} 件</span>
        </div>
        <div class="summary-row">
          <span class="summary-label">商品金额：</span>
          <span class="summary-value">¥{{ totalAmount.toFixed(2) }}</span>
        </div>
        <div class="summary-row total-row">
          <span class="summary-label">应付金额：</span>
          <span class="summary-total">¥{{ totalAmount.toFixed(2) }}</span>
        </div>
      </div>
    </div>
    <!-- 底部提交栏 -->
    <div class="submit-bar">
      <div class="submit-info">
        <span>应付：</span>
        <span class="submit-total">¥{{ totalAmount.toFixed(2) }}</span>
      </div>
      <el-button
        type="danger"
        size="large"
        class="submit-btn"
        :loading="submitting"
        @click="handleSubmit"
      >
        提交订单
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createOrder } from '@/api/order'
import { getProductDetail } from '@/api/product'
import { useCartStore } from '@/stores/cart'
import { useUserStore } from '@/stores/user'
import { PLACEHOLDER_IMG } from '@/constants/placeholder'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import type { OrderItemCreate, Product } from '@/types'
const route = useRoute()
const router = useRouter()
const cartStore = useCartStore()
const userStore = useUserStore()

const formRef = ref<FormInstance>()
const loading = ref(false)
const submitting = ref(false)

const addressForm = reactive({
  receiver_name: '',
  receiver_phone: '',
  receiver_address: '',
  remark: ''
})
const addressRules: FormRules = {
  receiver_name: [
    { required: true, message: '请输入收货人姓名', trigger: 'blur' }
  ],
  receiver_phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号', trigger: 'blur' }
  ],
  receiver_address: [
    { required: true, message: '请输入收货地址', trigger: 'blur' }
  ]
}

// 订单商品列表（带商品信息）
const orderItems = ref<(OrderItemCreate & { product?: Product })[]>([])

const totalQuantity = computed(() => {
  return orderItems.value.reduce((sum, item) => sum + item.quantity, 0)
})

const totalAmount = computed(() => {
  return orderItems.value.reduce((sum, item) => {
    return sum + Number(item.product?.price || 0) * item.quantity
  }, 0)
})
async function initOrderItems() {
  loading.value = true
  try {
    const { cart_item_ids, product_id, quantity } = route.query

    if (cart_item_ids) {
      // 从购物车结算
      const ids = String(cart_item_ids).split(',').map(Number)
      const cartItems = cartStore.cartItems.filter(item => ids.includes(item.id))

      orderItems.value = cartItems.map(item => ({
        product_id: item.product_id,
        quantity: item.quantity,
        product: item.product
      }))
       } else if (product_id) {
      // 立即购买
      const pid = Number(product_id)
      const qty = Number(quantity) || 1

      // 获取商品详情
      const res: any = await getProductDetail(pid)
      const product = res.data || res

      orderItems.value = [{
        product_id: pid,
        quantity: qty,
        product
      }]
    }
  } catch (error) {
    console.error('初始化订单商品失败:', error)
    ElMessage.error('获取商品信息失败')
  } finally {
    loading.value = false
  }
}
async function handleSubmit() {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
  } catch (e) {
    // ⭐⭐⭐ Element Plus 的 validate 在校验失败时会 throw ⭐⭐⭐
    // 这里的 e 就是 {receiver_name: [{message:"xxx"}], receiver_phone:[...], ...}
    // 表单下面已经有红色错误提示了，所以我们什么都不用做，直接 return
    // （不要走下面的 catch，否则会误弹出「创建订单失败」）
    console.warn('表单校验未通过:', e)
    return
  }

  // ---- 走到这里说明表单校验通过了，下面才是创建订单的逻辑 ----
  if (orderItems.value.length === 0) {
    ElMessage.warning('没有可结算的商品')
    return
  }

  try {
    submitting.value = true

    const orderData = {
      items: orderItems.value.map(item => ({
        product_id: item.product_id,
        quantity: item.quantity
      })),
      receiver_name: addressForm.receiver_name,
      receiver_phone: addressForm.receiver_phone,
      receiver_address: addressForm.receiver_address,
      remark: addressForm.remark || null
    }

    // ⭐⭐⭐ 关键：createOrder 的返回值里就包含新订单的 id！⭐⭐⭐
    // request 拦截器已把后端 {code, msg, data} 里的 data 解出来给我们
    // 所以 res.id / res.data.id 就是新订单的主键 ID
    const res: any = await createOrder(orderData, userStore.userId)
    const newOrderId = res?.data?.id ?? res?.id
    ElMessage.success('订单创建成功')

    // 清空购物车中已结算的商品（如果是从购物车来的）
    if (route.query.cart_item_ids) {
      cartStore.fetchCart()
    }

    // ✅ 按你的需求：下单成功后跳「订单详情页」（不是订单列表了）
    // 路由：/orders/{订单ID}，例如 /orders/15
    if (newOrderId) {
      router.push(`/orders/${newOrderId}`)
    } else {
      // 拿不到订单 ID 时兜底：回订单列表页（一般不会走到这里）
      router.push('/orders')
    }
  } catch (error: any) {
    // 现在这个 catch 才是真正捕获「后端创建订单失败」的错误
    console.error('创建订单失败:', error)
    const msg = error?.response?.data?.msg || error?.message || '创建订单失败'
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  initOrderItems()
})
</script>
<style scoped>
.order-confirm {
  padding: 24px 0 100px;
}

.page-title {
  margin: 0 0 20px;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.confirm-container {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.section {
  padding: 24px;
  border-bottom: 1px solid #f2f6fc;
}
.section:last-child {
  border-bottom: none;
}

.section-title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.address-form {
  max-width: 500px;
}

.goods-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.goods-item {
  display: grid;
  grid-template-columns: 80px 1fr 100px 120px;
  align-items: center;
  gap: 16px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}
.goods-image {
  width: 80px;
  height: 80px;
  border-radius: 4px;
  overflow: hidden;
  background: #f0f0f0;
}

.goods-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.goods-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.goods-name {
  font-size: 14px;
  color: #303133;
  line-height: 1.4;
}
.goods-price {
  font-size: 14px;
  color: #909399;
}

.goods-quantity {
  text-align: center;
  font-size: 14px;
  color: #606266;
}

.goods-subtotal {
  text-align: right;
  font-size: 16px;
  font-weight: 600;
  color: #f56c6c;
}

.summary-section {
  background: #fafafa;
}
.summary-row {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 14px;
  color: #606266;
}

.summary-row:last-child {
  margin-bottom: 0;
}

.summary-label {
  min-width: 80px;
  text-align: right;
}

.total-row {
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}

.summary-total {
  font-size: 24px;
  font-weight: 700;
  color: #f56c6c;
}
.submit-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 20px;
  padding: 16px 40px;
  background: #fff;
  border-top: 1px solid #ebeef5;
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.04);
  z-index: 100;
}

.submit-info {
  display: flex;
  align-items: baseline;
  gap: 4px;
  font-size: 14px;
  color: #606266;
}

.submit-total {
  font-size: 24px;
  font-weight: 700;
  color: #f56c6c;
}
.submit-btn {
  width: 140px;
  height: 44px;
  font-size: 16px;
}
</style>