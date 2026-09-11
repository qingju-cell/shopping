// ============================================================
// ai.ts —— AI 智能客服模块的前端 API 封装
// 对应后端接口：app/api/ai.py
// ============================================================

import request from '@/utils/request'

/** 后端返回给聊天卡片的实时商品摘要。 */
export interface RecommendedProduct {
  id: number
  product_code: string
  name: string
  price: number
  stock: number
  image_url: string
}

/** 收货信息齐全后，后端返回给当前用户核对的订单草稿；它还不是订单。 */
export interface OrderDraftConfirmation {
  status: 'ready_for_confirmation'
  items: Array<{
    product_id: number
    product_code: string
    product_name: string
    quantity: number
    unit_price: number
    subtotal: number
  }>
  total_amount: number
  receiver_name: string
  receiver_phone: string
  receiver_address: string
  remark: string
  can_confirm: boolean
}

/** 用户确认提交后才会出现；id 可用于跳到已有的订单详情和支付页面。 */
export interface CreatedOrderSummary {
  id: number
  order_no: string
  total_amount: number
  status: 'pending_payment'
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp?: number
  loading?: boolean
  intent?: string
  /** 仅 AI 商品咨询消息携带；历史消息没有该字段也完全正常。 */
  recommendedProducts?: RecommendedProduct[]
  /** 仅下单信息收集完成的 AI 消息携带；用于渲染“确认提交”前的核对单。 */
  orderDraft?: OrderDraftConfirmation
  /** AI 创建真实订单后携带；历史消息没有它时不会显示跳转按钮。 */
  createdOrder?: CreatedOrderSummary
}

export interface AIChatRequest {
  question: string
  history?: ChatMessage[]
  user_id?: number
  /** 首次不传；后续请求传回后端返回的值，表示继续同一段对话。 */
  session_id?: string
}

export interface AIChatResponse {
  answer: string
  intent: 'product' | 'chat' | 'service' | 'abuse' | 'purchase' | 'unknown'
  /** 登录用户首次聊天后由后端返回，用于后续续聊。 */
  session_id?: string
  /** 后端 snake_case 字段；组件收到后转存为消息的 camelCase 字段。 */
  recommended_products: RecommendedProduct[]
  /** 后端 snake_case 字段；还未创建真实订单。 */
  order_draft?: OrderDraftConfirmation | null
  /** 后端 snake_case 字段；其中 id 是订单详情路由使用的真实主键。 */
  created_order?: CreatedOrderSummary | null
}

interface ChatHistoryMessage {
  role: 'user' | 'ai'
  content: string
  time?: string
}

export interface AIChatHistoryResponse {
  user_id: number
  session_id: string
  total: number
  messages: ChatHistoryMessage[]
}

export function aiChatApi(data: AIChatRequest) {
  return request.post<AIChatResponse>('/ai/chat', data, {
    timeout: 100000
  })
}

/** 读取某一段已持久化的聊天记录；仅在登录用户且已有 session_id 时调用。 */
export function aiChatHistoryApi(userId: number, sessionId: string) {
  return request.get<AIChatHistoryResponse>('/ai/history', {
    params: { user_id: userId, session_id: sessionId, limit: 20 }
  })
}
