import request from '@/utils/request'
import type { Order, OrderCreate } from '@/types'

export function createOrder(data: OrderCreate, userId?: number) {
  return request.post<Order>('/orders', data, { params: { user_id: userId } })
}

export function getMyOrders(userId?: number) {
  return request.get<Order[]>('/orders', { params: { user_id: userId } })
}

export function getOrderDetail(orderId: number, userId?: number) {
  return request.get<Order>(`/orders/${orderId}`, { params: { user_id: userId } })
}