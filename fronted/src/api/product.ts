import request from '@/utils/request'
import type { Product, ProductCreate, ProductUpdate, ProductListParams, ProductListResponse } from '@/types'

export function getProducts(params?: ProductListParams) {
  return request.get<ProductListResponse>('/products', { params })
}

export function createProduct(data: ProductCreate) {
  return request.post<Product>('/products', data)
}

export function getProductDetail(productId: number) {
  return request.get<Product>(`/products/${productId}`)
}

export function updateProduct(productId: number, data: ProductUpdate) {
  return request.put<Product>(`/products/${productId}`, data)
}

export function deleteProduct(productId: number) {
  return request.delete<any>(`/products/${productId}`)
}