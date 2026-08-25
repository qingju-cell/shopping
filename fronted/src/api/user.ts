import request from '@/utils/request'
import type { UserLogin, UserRegister, UserInfo } from '@/types'

// 登录
export function loginApi(data: UserLogin) {
  return request.post<UserInfo>('/user/login', data)
}
// 注册
export function registerApi(data: UserRegister) {
  return request.post<UserInfo>('/user/register', data)
}
// 根据id获取用户
export function getUserByIdApi(userId: number) {
  return request.get<UserInfo>(`/user/${userId}`)
}