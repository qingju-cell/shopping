// ============================================================
// ai.ts —— AI 智能客服模块的前端 API 封装
// 对应后端接口：app/api/ai.py
// ============================================================

import request from '@/utils/request'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp?: number
  loading?: boolean
  intent?: string
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
  intent: 'product' | 'chat' | 'service' | 'abuse' | 'unknown'
  /** 登录用户首次聊天后由后端返回，用于后续续聊。 */
  session_id?: string
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