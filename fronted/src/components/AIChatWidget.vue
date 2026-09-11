<template>
  <!-- AI 客服悬浮组件：右下角按钮 + 聊天弹窗 -->
  <div class="ai-chat-wrapper">

    <!-- ========== 按钮：悬浮在右下角（聊天窗关闭时显示） ========== -->
    <button
      v-if="!isOpen"
      class="chat-float-btn"
      @click="openChat"
      :title="'小购 AI 客服'"
    >
      <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="chat-badge">
        <el-icon class="chat-icon" :size="28"><ChatDotRound /></el-icon>
      </el-badge>
      <span class="chat-btn-label">AI客服</span>
    </button>

    <!-- ========== 聊天弹窗（打开时显示） ========== -->
    <div v-if="isOpen" class="chat-panel">
      <!-- 顶部标题栏 -->
      <div class="chat-header">
        <div class="header-left">
          <div class="ai-avatar">
            <el-icon :size="20"><ChatDotRound /></el-icon>
          </div>
          <div class="header-info">
            <span class="ai-name">小购 AI 客服</span>
            <span class="ai-status">
              <span class="status-dot online"></span>
              在线
            </span>
          </div>
        </div>
        <div class="header-actions">
          <el-button text size="small" @click="clearHistory" title="清空聊天记录">
            <el-icon><Delete /></el-icon>
          </el-button>
          <el-button text size="small" @click="closeChat" title="关闭">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 消息列表 -->
      <div class="chat-body" ref="chatBodyRef">
        <!-- 欢迎消息 -->
        <div v-if="messages.length === 0" class="welcome-box">
          <div class="welcome-avatar">
            <el-icon :size="32"><ChatDotRound /></el-icon>
          </div>
          <h3 class="welcome-title">您好，我是小购 🤖</h3>
          <p class="welcome-desc">
            我可以帮您：<br>
            · 推荐和搜索商品<br>
            · 查询订单/物流/售后<br>
            · 解答购物相关问题
          </p>
          <!-- 常见问题快捷按钮 -->
          <div class="quick-questions">
            <el-button
              v-for="q in quickQuestions"
              :key="q"
              size="small"
              class="quick-btn"
              @click="sendQuickQuestion(q)"
            >
              {{ q }}
            </el-button>
          </div>
        </div>

        <!-- 消息循环渲染 -->
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="msg-item"
          :class="msg.role === 'user' ? 'msg-right' : 'msg-left'"
        >
          <!-- 头像 -->
          <div
            class="msg-avatar"
            :class="msg.role === 'user' ? 'user-avatar' : 'ai-avatar-small'"
          >
            <el-icon v-if="msg.role === 'assistant'" :size="16"><ChatDotRound /></el-icon>
            <span v-else>{{ usernameFirstChar }}</span>
          </div>

          <!-- 消息气泡 -->
          <div class="msg-bubble-wrap">
            <div
              class="msg-bubble"
              :class="{
                'user-bubble': msg.role === 'user',
                'ai-bubble': msg.role === 'assistant',
                'loading-bubble': msg.loading
              }"
              v-loading="msg.loading"
              :element-loading-text="'AI 正在思考...'"
              :element-loading-spinner="'Loading'"
              :element-loading-background="'rgba(255, 255, 255, 0.8)'"
            >
              <div v-if="!msg.loading" class="msg-content" v-html="formatAnswer(msg.content)"></div>
            </div>

            <!-- 商品咨询才有卡片；普通闲聊、历史消息不会显示这一块。 -->
            <div v-if="msg.recommendedProducts?.length" class="recommended-products">
              <button
                v-for="product in msg.recommendedProducts"
                :key="product.id"
                type="button"
                class="recommended-product-card"
                :aria-label="`查看商品：${product.name}`"
                @click="goToProduct(product.id)"
              >
                <img
                  class="recommended-product-image"
                  :src="product.image_url || PLACEHOLDER_IMG['80x80']"
                  :alt="product.name"
                >
                <span class="recommended-product-info">
                  <strong>{{ product.name }}</strong>
                  <span class="recommended-product-code">商品编号：{{ product.product_code }}</span>
                  <span class="recommended-product-price">¥{{ product.price }}</span>
                  <span class="recommended-product-stock">库存 {{ product.stock }} 件 · 查看详情 ›</span>
                </span>
              </button>
            </div>

            <!-- 仅当后端确认三项收货信息齐全时展示；这不是支付按钮，也不创建订单。 -->
            <section v-if="msg.orderDraft?.can_confirm" class="order-draft-card">
              <strong class="order-draft-title">订单确认单（尚未提交）</strong>
              <div v-for="item in msg.orderDraft.items" :key="item.product_id" class="order-draft-item">
                <span>{{ item.product_name }}（{{ item.product_code }}）× {{ item.quantity }}</span>
                <span>¥{{ item.subtotal }}</span>
              </div>
              <p class="order-draft-total">合计：¥{{ msg.orderDraft.total_amount }}</p>
              <p>收货人：{{ msg.orderDraft.receiver_name }}（{{ msg.orderDraft.receiver_phone }}）</p>
              <p>地址：{{ msg.orderDraft.receiver_address }}</p>
              <p v-if="msg.orderDraft.remark">备注：{{ msg.orderDraft.remark }}</p>
              <p class="order-draft-tip">请核对信息；回复“确认提交”后才会创建订单并进入支付步骤。</p>
            </section>

            <!-- 真实订单创建成功后才显示。点击只跳转，支付仍由订单详情页的原有按钮负责。 -->
            <section v-if="msg.createdOrder" class="created-order-card">
              <strong>订单已创建，等待支付</strong>
              <p>订单号：{{ msg.createdOrder.order_no }}</p>
              <p>应付金额：¥{{ msg.createdOrder.total_amount }}</p>
              <button type="button" class="go-order-button" @click="goToOrder(msg.createdOrder.id)">
                前往订单详情并支付
              </button>
            </section>

            <!-- 消息时间 -->
            <span v-if="msg.timestamp && !msg.loading" class="msg-time">
              {{ formatTime(msg.timestamp) }}
            </span>
          </div>
        </div>
      </div>

      <!-- 底部输入区 -->
      <div class="chat-footer">
        <el-input
          v-model="inputText"
          class="chat-input"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          :placeholder="'请输入您的问题，按 Enter 发送，Shift+Enter 换行...'"
          :disabled="isSending || isRestoringHistory"
          resize="none"
          @keydown="handleKeydown"
        />
        <el-button
          type="primary"
          class="send-btn"
          :disabled="!inputText.trim() || isSending || isRestoringHistory"
          :loading="isSending"
          @click="sendMessage"
        >
          <el-icon><Promotion /></el-icon>
          <span>发送</span>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ChatDotRound,
  Close,
  Delete,
  Promotion
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { aiChatApi, aiChatHistoryApi, type ChatMessage } from '@/api/ai'
import { PLACEHOLDER_IMG } from '@/constants/placeholder'
import { useUserStore } from '@/stores/user'

// ============ 状态 ============
const userStore = useUserStore()
const router = useRouter()

/** 聊天窗是否打开 */
const isOpen = ref(false)
/** 输入框内容 */
const inputText = ref('')
/** 是否正在发送中 */
const isSending = ref(false)

/** 是否正在从 MySQL 恢复当前会话，恢复中不允许抢先发送新消息。 */
const isRestoringHistory = ref(false)
/** 当前浏览器正在使用的会话编号；未登录或首次提问时为 null。 */
const currentSessionId = ref<string | null>(null)
/** 未读消息数（按钮上的小红点） */
const unreadCount = ref(0)
/** 消息列表 */
const messages = ref<ChatMessage[]>([])
/** 消息列表 DOM（用来滚动到底部） */
const chatBodyRef = ref<HTMLElement | null>(null)

/** 常见问题（快捷按钮） */
const quickQuestions = [
  '你们有什么便宜的手机？',
  '1+1等于几？',
  '我的订单怎么还没发货？',
  '可以退换货吗？'
]

/** 用户头像首字母 */
const usernameFirstChar = computed(() => {
  const name = userStore.userInfo?.username || 'U'
  return name.charAt(0).toUpperCase()
})

// ============ 方法 ============

/** 当前用户专属的浏览器存储键，避免同一浏览器切换账号后串会话。 */
function sessionStorageKey(): string | null {
  const userId = userStore.userInfo?.id
  return userId ? `shopping-ai-session:${userId}` : null
}

function saveCurrentSession(sessionId: string) {
  currentSessionId.value = sessionId
  const key = sessionStorageKey()
  if (key) localStorage.setItem(key, sessionId)
}

/** 从 MySQL 恢复当前用户上次正在使用的那一段会话。 */
async function restoreChatHistory() {
  const userId = userStore.userInfo?.id
  const key = sessionStorageKey()
  const savedSessionId = key ? localStorage.getItem(key) : null
  if (!userId || !savedSessionId || messages.value.length > 0) return

  currentSessionId.value = savedSessionId
  isRestoringHistory.value = true
  try {
    const res: any = await aiChatHistoryApi(userId, savedSessionId)
    const savedMessages = res?.data?.messages || []
    messages.value = savedMessages.map((message: any) => {
      const parsedTime = Date.parse(message.time || '')
      return {
        role: message.role === 'ai' ? 'assistant' : 'user',
        content: message.content,
        timestamp: Number.isNaN(parsedTime) ? undefined : parsedTime
      }
    })
  } catch (error) {
    // 保留本地 session_id，网络恢复后下次打开聊天窗还能继续尝试恢复。
    console.error('恢复 AI 聊天记录失败:', error)
  } finally {
    isRestoringHistory.value = false
  }
}

/** 打开聊天窗；若本地保存了会话编号，则从数据库恢复它。 */
async function openChat() {
  isOpen.value = true
  unreadCount.value = 0
  await restoreChatHistory()
  await nextTick()
  scrollToBottom()
}
/** 关闭聊天窗 */
function closeChat() {
  isOpen.value = false
}

/** 开始新会话：只取消当前会话引用，不删除 MySQL 中旧会话记录。 */
function clearHistory() {
  messages.value = []
  currentSessionId.value = null
  const key = sessionStorageKey()
  if (key) localStorage.removeItem(key)
  ElMessage.success('已开始新的对话')
}
/** 发送快捷问题 */
function sendQuickQuestion(q: string) {
  inputText.value = q
  sendMessage()
}

/** 处理键盘事件：Enter 发送，Shift+Enter 换行 */
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

/** 发送消息主流程 */
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isSending.value || isRestoringHistory.value) return

  // 先截取已经完成的旧对话。不能把本轮问题和稍后插入的空加载消息传给后端，
  // 否则当前问题会在 question 与 history 中重复出现，浪费 Prompt Token。
  const previousHistory = messages.value.slice(-10)

  // 1. 把用户消息加入列表
  const userMsg: ChatMessage = {
    role: 'user',
    content: text,
    timestamp: Date.now()
  }
  messages.value.push(userMsg)
  inputText.value = ''
  isSending.value = true
  await nextTick(scrollToBottom)

  // 2. 先插入一条 AI 的「加载中」占位消息
  const aiPlaceholderMsg: ChatMessage = {
    role: 'assistant',
    content: '',
    loading: true,
    timestamp: Date.now()
  }
  messages.value.push(aiPlaceholderMsg)
  await nextTick(scrollToBottom)

  try {
    // 3. 调用后端 AI 接口
    const res = await aiChatApi({
      question: text,
      history: previousHistory.map(m => ({ role: m.role, content: m.content })),
      user_id: userStore.userInfo?.id,
      session_id: currentSessionId.value || undefined
    })

    // 4. 保存后端返回的会话编号。以后每次请求传回它，数据库就会追加到同一段对话。
    const responseData = (res as any)?.data
    if (responseData?.session_id) saveCurrentSession(responseData.session_id)

    // 5. 把占位消息替换成真实 AI 回答
    const placeholderIdx = messages.value.length - 1
    messages.value[placeholderIdx] = {
      role: 'assistant',
      content: responseData?.answer || '抱歉，AI 暂时没有回答',
      intent: responseData?.intent || 'unknown',
      // API 用 snake_case；前端消息对象用 camelCase，方便模板读取。
      recommendedProducts: responseData?.recommended_products || [],
      orderDraft: responseData?.order_draft || undefined,
      createdOrder: responseData?.created_order || undefined,
      timestamp: Date.now(),
      loading: false
    }  } catch (err: any) {
    // 出错时：替换占位消息为错误提示
    const placeholderIdx = messages.value.length - 1
    messages.value[placeholderIdx] = {
      role: 'assistant',
      content: '抱歉，网络繁忙，AI 暂时无法回答，请稍后再试 😭',
      timestamp: Date.now(),
      loading: false
    }
    console.error('AI 聊天接口错误:', err)
  } finally {
    isSending.value = false
    await nextTick(scrollToBottom)
  }
}

/** 点击卡片只负责跳转；详情页会按 ID 重新读取最新价格和库存。 */
function goToProduct(productId: number) {
  isOpen.value = false
  router.push(`/products/${productId}`)
}

/** 使用后端返回的真实订单主键跳转；订单详情页负责展示状态和模拟支付。 */
function goToOrder(orderId: number) {
  isOpen.value = false
  router.push(`/orders/${orderId}`)
}

/** 滚动消息列表到底部 */
function scrollToBottom() {
  if (chatBodyRef.value) {
    chatBodyRef.value.scrollTop = chatBodyRef.value.scrollHeight
  }
}

/** 格式化时间戳 → HH:mm */
function formatTime(ts: number): string {
  const d = new Date(ts)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

/** 格式化 AI 回答（简单的换行 → <br>，商品名高亮） */
function formatAnswer(text: string): string {
  if (!text) return ''
  // 1. 转义 HTML（防止 XSS）
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // 2. 换行转 <br>
  html = html.replace(/\n/g, '<br>')
  // 3. 加粗价格（如 ¥999元、799元）
  html = html.replace(/(¥?\d+(\.\d+)?\s*元)/g, '<strong style="color:#f56c6c">$1</strong>')
  // 4. 加粗 【商品X】
  html = html.replace(/【(商品\s*\d+)】/g, '<span style="color:#409eff;font-weight:600">【$1】</span>')
  return html
}

// ============ 生命周期 ============
onMounted(() => {
  // 页面加载时，给一条未读提示（吸引用户点）
  unreadCount.value = 1
})
</script>

<style scoped>
/* ============================================================
   外层容器 + 悬浮按钮
   ============================================================ */
.ai-chat-wrapper {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.chat-float-btn {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff 0%, #2c7be5 100%);
  color: #fff;
  border: none;
  cursor: pointer;
  box-shadow: 0 4px 20px rgba(64, 158, 255, 0.4);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  transition: all 0.3s;
  padding: 0;
}
.chat-float-btn:hover {
  transform: translateY(-3px) scale(1.05);
  box-shadow: 0 8px 28px rgba(64, 158, 255, 0.55);
}
.chat-float-btn .chat-btn-label {
  font-size: 11px;
  font-weight: 600;
}
.chat-badge {
  display: flex;
  align-items: center;
}

/* ============================================================
   聊天弹窗面板
   ============================================================ */
.chat-panel {
  width: 400px;
  height: 600px;
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: panelIn 0.28s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid #ebeef5;
}

@keyframes panelIn {
  from { opacity: 0; transform: translateY(20px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0)    scale(1);    }
}

/* ---------- 顶部标题栏 ---------- */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  background: linear-gradient(135deg, #409eff 0%, #2c7be5 100%);
  color: #fff;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ai-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(8px);
  border: 2px solid rgba(255, 255, 255, 0.35);
}
.header-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.ai-name {
  font-size: 16px;
  font-weight: 600;
}
.ai-status {
  font-size: 12px;
  opacity: 0.92;
  display: flex;
  align-items: center;
  gap: 5px;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.status-dot.online {
  background: #67c23a;
  box-shadow: 0 0 0 2px rgba(103, 194, 58, 0.3);
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.header-actions :deep(.el-button) {
  color: #fff !important;
  padding: 6px;
}
.header-actions :deep(.el-button:hover) {
  background: rgba(255, 255, 255, 0.2) !important;
}

/* ---------- 消息列表 ---------- */
.chat-body {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  background: #f5f7fa;
  scroll-behavior: smooth;
}
.chat-body::-webkit-scrollbar { width: 6px; }
.chat-body::-webkit-scrollbar-thumb {
  background: #d0d4da;
  border-radius: 3px;
}

/* 欢迎消息 */
.welcome-box {
  text-align: center;
  padding: 24px 12px;
}
.welcome-avatar {
  width: 58px;
  height: 58px;
  margin: 0 auto 14px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff 0%, #2c7be5 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.35);
}
.welcome-title {
  margin: 0 0 10px;
  font-size: 18px;
  color: #303133;
}
.welcome-desc {
  margin: 0 auto 18px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
  max-width: 280px;
}
.quick-questions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.quick-btn {
  border-radius: 16px;
  border-color: #d9ecff;
  color: #409eff;
  background: #ecf5ff;
  font-size: 12px;
}
.quick-btn:hover {
  background: #409eff !important;
  color: #fff !important;
  border-color: #409eff !important;
}

/* 消息单条 */
.msg-item {
  display: flex;
  margin-bottom: 16px;
  gap: 10px;
  align-items: flex-start;
}
.msg-left  { flex-direction: row; }           /* AI 消息：头像在左 */
.msg-right { flex-direction: row-reverse; }   /* 用户消息：头像在右 */

.msg-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 13px;
  flex-shrink: 0;
}
.ai-avatar-small {
  background: linear-gradient(135deg, #409eff 0%, #2c7be5 100%);
  color: #fff;
}
.user-avatar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

/* 气泡 */
.msg-bubble-wrap {
  max-width: 75%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.msg-right .msg-bubble-wrap { align-items: flex-end; }
.msg-left  .msg-bubble-wrap { align-items: flex-start; }

.msg-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-wrap: break-word;
  word-break: break-word;
  min-width: 40px;
  min-height: 20px;
}
.ai-bubble {
  background: #fff;
  color: #303133;
  border-top-left-radius: 4px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  border: 1px solid #ebeef5;
}
.user-bubble {
  background: linear-gradient(135deg, #409eff 0%, #2c7be5 100%);
  color: #fff;
  border-top-right-radius: 4px;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.25);
}
.loading-bubble {
  min-width: 100px;
  min-height: 40px;
}
.msg-content {
  white-space: pre-wrap;
}
.msg-content :deep(strong) {
  font-weight: 600;
}

/* AI 商品推荐卡片：独立于文字气泡，点击后进入已有商品详情页。 */
.recommended-products {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.recommended-product-card {
  width: 100%;
  display: flex;
  gap: 10px;
  padding: 9px;
  text-align: left;
  color: #303133;
  background: #fff;
  border: 1px solid #d9ecff;
  border-radius: 10px;
  cursor: pointer;
  transition: border-color .2s, transform .2s, box-shadow .2s;
}
.recommended-product-card:hover {
  border-color: #409eff;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(64, 158, 255, .16);
}
.recommended-product-image {
  width: 52px;
  height: 52px;
  object-fit: cover;
  border-radius: 7px;
  background: #f5f7fa;
  flex-shrink: 0;
}
.recommended-product-info {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}
.recommended-product-info strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recommended-product-price {
  color: #f56c6c;
  font-weight: 700;
}
.recommended-product-stock {
  color: #909399;
  font-size: 11px;
}

/* 后端给出的订单草稿：用户看见、核对，但尚未真正提交。 */
.order-draft-card {
  width: 100%;
  box-sizing: border-box;
  padding: 12px;
  color: #303133;
  background: #f0f9eb;
  border: 1px solid #c2e7b0;
  border-radius: 10px;
  font-size: 13px;
}
.order-draft-title { display: block; margin-bottom: 8px; color: #529b2e; }
.order-draft-item { display: flex; justify-content: space-between; gap: 12px; margin: 4px 0; }
.order-draft-card p { margin: 5px 0; line-height: 1.5; word-break: break-all; }
.order-draft-total { color: #f56c6c; font-size: 14px; font-weight: 700; }
.order-draft-tip { color: #909399; font-size: 12px; }

/* 绿色确认单和蓝色“已创建”卡片分开，提醒用户订单已生成但还未支付。 */
.created-order-card {
  width: 100%;
  box-sizing: border-box;
  padding: 12px;
  color: #303133;
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
  border-radius: 10px;
  font-size: 13px;
}
.created-order-card strong { color: #409eff; }
.created-order-card p { margin: 6px 0; }
.go-order-button {
  margin-top: 5px;
  padding: 7px 10px;
  color: #fff;
  background: #409eff;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
}

.msg-time {
  font-size: 11px;
  color: #c0c4cc;
  padding: 0 4px;
}

/* ---------- 底部输入区 ---------- */
.chat-footer {
  padding: 12px;
  background: #fff;
  border-top: 1px solid #ebeef5;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-shrink: 0;
}
.chat-input {
  flex: 1;
}
.chat-input :deep(.el-textarea__inner) {
  font-size: 14px;
  padding: 8px 12px;
  border-radius: 10px;
  resize: none;
}
.send-btn {
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 16px;
}

/* 小屏幕适配 */
@media (max-width: 480px) {
  .chat-panel {
    width: calc(100vw - 32px);
    height: calc(100vh - 120px);
    position: fixed;
    right: 16px;
    left: 16px;
    bottom: 80px;
  }
}
</style>
