import request from '@/utils/request'
import type { CartItem, CartAdd, CartUpdateQuantity } from '@/types'

// 查询购物车
export function getCartApi(userId?: number) {
  return request.get<CartItem[]>('/cart', { params: { user_id: userId } })
}

// 添加购物车
export function addCartApi(data: CartAdd, userId?: number) {
  return request.post<CartItem>('/cart', data, { params: { user_id: userId } })
}

// 修改购物车数量
export function updateCartQuantityApi(
  cartItemId: number,
  data: CartUpdateQuantity,
  userId?: number
) {
  return request.put<CartItem>(`/cart/${cartItemId}`, data, { params: { user_id: userId } })
}

// 删除购物车项
export function deleteCartItemApi(cartItemId: number, userId?: number) {
  return request.delete<any>(`/cart/${cartItemId}`, { params: { user_id: userId } })
}