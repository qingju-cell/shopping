// ============================================================
// ai.ts —— AI 智能客服模块的前端 API 封装
// 对应后端接口：app/api/ai.py
// ============================================================

import request from '@/utils/request'

// ---------- 类型定义 ----------

/** 单条聊天消息 */
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp?: number
  /** 发送中状态（前端用） */
  loading?: boolean
  /** 识别到的意图（AI消息带） */
  intent?: string
}

/** AI 聊天请求 */
export interface AIChatRequest {
  question: string
  history?: ChatMessage[]
  user_id?: number
}

/** AI 聊天响应 */
export interface AIChatResponse {
  answer: string
  intent: 'product' | 'chat' | 'service' | 'abuse' | 'unknown'
}

// ---------- API 方法 ----------

/**
 * 发送消息给 AI 客服
 * @param data 请求体：包含问题和聊天历史
 * @returns AI 的回答 + 意图
 */
export function aiChatApi(data: AIChatRequest) {
  return request.post<AIChatResponse>('/ai/chat', data, {
    timeout: 100000  // AI 聊天首次请求需要初始化，可能较慢，设 60 秒
  })
}