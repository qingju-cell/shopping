// 用户相关类型
export interface UserLogin {
  username: string
  password: string
}

export interface UserRegister {
  username: string
  password: string
  email?: string | null
  phone?: string | null
}

export interface UserInfo {
  id: number
  username: string
  email?: string | null
  phone?: string | null
  avatar?: string
  role?: 'customer' | 'admin' | string
  created_at?: string
}

// 分类相关类型
export interface Category {
  id: number
  name: string
  parent_id: number
  sort: number
}

export interface CategoryCreate {
  name: string
  parent_id?: number
  sort?: number
}

export interface CategoryUpdate {
  name?: string
  parent_id?: number
  sort?: number
}

// 商品相关类型
export interface Product {
  id: number
  name: string
  description?: string | null
  price: number
  stock: number
  category_id?: number | null
  image_url?: string | null
  status?: number
  category?: Category
}

export interface ProductCreate {
  name: string
  description?: string | null
  price: number | string
  stock?: number
  category_id?: number | null
  image_url?: string | null
}

export interface ProductUpdate {
  name?: string | null
  description?: string | null
  price?: number | string | null
  stock?: number | null
  category_id?: number | null
  image_url?: string | null
}
export interface ProductListParams {
  page?: number
  page_size?: number
  category_id?: number | null
  keyword?: string
}
export interface ProductListResponse {
  list: Product[]
  items?: Product[]
  total: number
  page: number
  page_size: number
}

// 购物车相关类型（与后端返回的扁平结构对齐）
export interface CartItem {
  id: number
  product_id: number
  product_name: string
  product_price: number
  product_image?: string | null
  quantity: number
  subtotal: number
  created_at?: string
}

export interface CartAdd {
  product_id: number
  quantity?: number
}

export interface CartUpdateQuantity {
  quantity: number
}


// 订单相关类型
export interface OrderItemCreate {
  product_id: number
  quantity: number
}

export interface OrderCreate {
  items: OrderItemCreate[]
  receiver_name: string
  receiver_phone: string
  receiver_address: string
  remark?: string | null
}

export interface OrderItem {
  id: number
  product_id: number
  product_name: string
  product_price: number
  quantity: number
  subtotal: number
  product?: Product
}

export interface Order {
  id: number
  user_id: number
  order_no: string
  total_amount: number
  status: number
  receiver_name: string
  receiver_phone: string
  receiver_address: string
  remark?: string
  items?: OrderItem[]
  created_at: string
}

// 通用响应类型
export interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

// 验证错误类型
export interface ValidationError {
  loc: (string | number)[]
  msg: string
  type: string
  input?: any
  ctx?: Record<string, any>
}

export interface HTTPValidationError {
  detail: ValidationError[]
}