import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getCartApi, addCartApi, updateCartQuantityApi, deleteCartItemApi } from '@/api/cart'
import type { CartItem, CartAdd, CartUpdateQuantity } from '@/types'
import { useUserStore } from './user'
import { ElMessage } from 'element-plus'

export const useCartStore = defineStore('cart', () => {
  // state
  const cartItems = ref<CartItem[]>([])
  const loading = ref(false)

  // getters
  const totalCount = computed(() => {
    const list = Array.isArray(cartItems.value) ? cartItems.value : []
    return list.reduce((sum, item) => sum + (item.quantity || 0), 0)
  })

  const totalPrice = computed(() => {
    const list = Array.isArray(cartItems.value) ? cartItems.value : []
    return list.reduce((sum, item) => sum + (item.subtotal || 0), 0)
  })

  const selectedItems = computed(() => {
    // 默认全部选中，如需选择功能可扩展
    return Array.isArray(cartItems.value) ? cartItems.value : []
  })

  // actions
  async function fetchCart() {
    const userStore = useUserStore()
    const userId = userStore.userId

    if (!userId && !userStore.isLoggedIn) {
      cartItems.value = []
      return
    }
    loading.value = true
    try {
      const res: any = await getCartApi(userId)
      // 响应拦截器已把 res = axios 的 res.data，即后端的 { code, msg, data }
      // 所以真实数组在 res.data 里，兜底为空数组
      const list = res?.data
      cartItems.value = Array.isArray(list) ? list : []
    } catch (error) {
      console.error('获取购物车失败:', error)
      cartItems.value = []
    } finally {
      loading.value = false
    }
  }

  async function addItem(productId: number, quantity: number = 1) {
    const userStore = useUserStore()
    const userId = userStore.userId

    if (!userStore.isLoggedIn) {
      ElMessage.warning('请先登录')
      return false
    }

    loading.value = true
    try {
      const data: CartAdd = { product_id: productId, quantity }
      await addCartApi(data, userId)
      ElMessage.success('已添加到购物车')
      await fetchCart()
      return true
    } catch (error) {
      console.error('添加购物车失败:', error)
      return false
    } finally {
      loading.value = false
    }
  }

  async function updateQuantity(cartItemId: number, quantity: number) {
    const userStore = useUserStore()
    const userId = userStore.userId

    if (quantity < 1) {
      await removeItem(cartItemId)
      return
    }

    loading.value = true
    try {
      const data: CartUpdateQuantity = { quantity }
      await updateCartQuantityApi(cartItemId, data, userId)
      await fetchCart()
    } catch (error) {
      console.error('更新购物车数量失败:', error)
    } finally {
      loading.value = false
    }
  }


  async function removeItem(cartItemId: number) {
    const userStore = useUserStore()
    const userId = userStore.userId

    loading.value = true
    try {
      await deleteCartItemApi(cartItemId, userId)
      ElMessage.success('已移除商品')
      await fetchCart()
    } catch (error) {
      console.error('删除购物车商品失败:', error)
    } finally {
      loading.value = false
    }
  }

  function clearCart() {
    cartItems.value = []
  }

  return {
    cartItems,
    loading,
    totalCount,
    totalPrice,
    selectedItems,
    fetchCart,
    addItem,
    updateQuantity,
    removeItem,
    clearCart
  }
})