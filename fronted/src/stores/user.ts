import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { loginApi , registerApi , getUserByIdApi } from '@/api/user'
import type { UserLogin, UserRegister, UserInfo } from '@/types'
import { ElMessage } from 'element-plus'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(localStorage.getItem('token') || '')
  const userInfo = ref<UserInfo | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => !!token.value && !!userInfo.value?.id)
  const userId = computed(() => userInfo.value?.id)
  const isAdmin = computed(() => userInfo.value?.role === 'admin')

  function extractUserInfo(res: any): UserInfo | null {
    if (!res) return null
    // 兼容多种结构：res本身就是用户对象 / res.data / res.user / res.data.user
    const candidates = [res, res.data, res.user, res.data?.user]
    for (const c of candidates) {
      if (c && typeof c === 'object' && (c.id || c.username)) {
        return c as UserInfo
      }
    }
    return null
  }

  function extractToken(res: any): string {
    if (!res) return ''
    if (typeof res.token === 'string' && res.token) return res.token
    if (typeof res.access_token === 'string' && res.access_token) return res.access_token
    if (typeof res.data?.token === 'string' && res.data.token) return res.data.token
    // 后端暂不签发 token 时，用 user.id 作临时占位（仅用于 isLoggedIn 判断，配合白名单接口使用）
    const user = extractUserInfo(res)
    if (user?.id) return `uid-${user.id}`
    return ''
  }

  async function login(formData: UserLogin) {
    loading.value = true
    try {
      const res: any = await loginApi(formData)

      const tokenValue = extractToken(res)
      const userData = extractUserInfo(res)

      if (tokenValue) {
        token.value = tokenValue
        localStorage.setItem('token', tokenValue)
      }
      if (userData) {
        userInfo.value = userData
        localStorage.setItem('userInfo', JSON.stringify(userData))
      }
      ElMessage.success(`登录成功${userData?.role === 'admin' ? '（管理员）' : ''}`)
      return res
    } finally {
      loading.value = false
    }
  }

  async function register(formData: UserRegister) {
    loading.value = true
    try {
      const res = await registerApi(formData)
      ElMessage.success('注册成功，请登录')
      return res
    } finally {
      loading.value = false
    }
  }

  async function fetchUserInfo(userId: number) {
    try {
      const res: any = await getUserByIdApi(userId)
      const userData = extractUserInfo(res)
      if (userData) {
        userInfo.value = userData
        localStorage.setItem('userInfo', JSON.stringify(userData))
      }
      return userData
    } catch (error) {
      console.error('获取用户信息失败:', error)
    }
  }

  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    ElMessage.success('已退出登录')
  }

  function initUserInfo() {
    const savedUserInfo = localStorage.getItem('userInfo')
    if (savedUserInfo) {
      try {
        const parsed = JSON.parse(savedUserInfo)
        if (parsed && (parsed.id || parsed.username)) {
          userInfo.value = parsed
        }
      } catch (e) {
        console.error('解析用户信息失败', e)
      }
    }
    const savedToken = localStorage.getItem('token')
    if (savedToken && !token.value) {
      token.value = savedToken
    }
  }

  return {
    token,
    userInfo,
    loading,
    isLoggedIn,
    userId,
    isAdmin,
    login,
    register,
    fetchUserInfo,
    logout,
    initUserInfo
  }
})