import request from '@/utils/request'
import { Category, CategoryCreate, CategoryUpdate } from '@/types'

export function getCategoryListApi() {
  return request.get<Category[]>('/category/')
}

export function addCategoryApi(data: CategoryCreate) {
  return request.post<Category>('/category', data)
}

export function updateCategoryApi(categoryId: number, data: CategoryUpdate) {
  return request.put<Category>(`/category/${categoryId}`, data)
}

export function deleteCategoryApi(categoryId: number) {
  return request.delete<any>(`/category/${categoryId}`)
}