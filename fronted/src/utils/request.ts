import axios, { type AxiosInstance } from 'axios'
import { ElMessage } from 'element-plus'

// 创建axios实例
const service: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 10000
})

// 不需要token的接口白名单
const noTokenUrls = ['/user/login', '/user/register']

// 请求拦截器
service.interceptors.request.use(
  (config) => {
    const url = config.url || ''
    // 不在白名单则携带token
    if (!noTokenUrls.some(item => url.includes(item))) {
      const token = localStorage.getItem('token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
    }
    return config
  },
  (err) => Promise.reject(err)
)

// 响应拦截器
service.interceptors.response.use(
  (res) => res.data,
  (err) => {
    // 401 未登录/Token失效
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      location.href = '/login'
      ElMessage.warning('登录已失效，请重新登录')
    } else {
      ElMessage.error(err.response?.data?.msg || err.response?.data?.message || '请求失败')
    }
    return Promise.reject(err)
  }
)

export default service
