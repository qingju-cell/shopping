<!-- 
  OrderList.vue —— 「我的订单」页面
  功能：展示当前登录用户的所有订单，支持查看订单详情（弹窗形式）
  结构：
    1. template（HTML 模板） —— 页面长什么样
    2. script setup（逻辑代码） —— 数据和方法
    3. style scoped（CSS 样式） —— 页面漂不漂亮
-->

<template>
  <!-- 最外层容器：订单列表页面 -->
  <div class="order-list">
    <!-- 页面标题 -->
    <h2 class="page-title">我的订单</h2>

    <!-- 
      订单列表容器
      v-loading="loading" 是 Element Plus 的指令：
      当 loading 为 true 时，整个区域显示转圈加载动画
    -->
    <div v-loading="loading" class="orders-container">

      <!-- 
        情况 A：有订单时（orders 数组长度 > 0）
        v-if 控制：只有条件为 true 才渲染这块内容
      -->
      <div v-if="orders.length > 0" class="orders-list">

        <!-- 
          v-for 循环：把 orders 数组里的每一个订单都渲染成一张卡片
          order 是当前循环的订单对象，order.id 是唯一标识（给 Vue 做 diff 用）
        -->
        <div
          v-for="order in orders"
          :key="order.id"
          class="order-card"
        >

          <!-- ====== 订单卡片的头部：订单号 + 时间 + 状态标签 ====== -->
          <div class="order-header">
            <div class="order-info">
              <!-- 
                显示订单号
                优先用 order_no，没有就用 order.id 兜底
                {{ }} 是 Vue 的插值语法：把变量的值显示到页面上
              -->
              <span class="order-no">订单号：{{ order.order_no || order.id }}</span>

              <!-- 显示下单时间，用 formatDate 函数格式化一下 -->
              <span class="order-time">{{ formatDate(order.created_at) }}</span>
            </div>

            <!-- 
              订单状态标签（Element Plus 的 el-tag 组件）
              :type 动态绑定颜色：getStatusType 根据状态号返回对应颜色
              effect="light" 表示浅色背景的标签风格
            -->
            <el-tag :type="getStatusType(order.status)" effect="light">
              {{ getStatusText(order.status) }}
            </el-tag>
          </div>

          <!-- ====== 订单卡片的中部：商品预览（最多显示 3 件） ====== -->
          <div class="order-goods">

            <!-- 
              v-for 循环显示订单项
              (order.items || order.order_items) 双写兼容：
                - order.items 是后端 OrderResponse 计算出来的字段
                - order.order_items 是后端模型原始字段
                - slice(0, 3) 只取前 3 件，超过的不显示
              @click 点击整个商品项跳转到对应商品详情页
            -->
            <div
              v-for="item in getOrderItems(order).slice(0, 3)"
              :key="item.id"
              class="goods-item"
              @click="goToProduct(item.product_id)"
            >
              <!-- 商品图片 -->
              <div class="goods-image">
                <!-- 
                  :src 动态绑定图片地址
                  如果 item.product.image_url 存在就用真实图片
                  否则用 PLACEHOLDER_IMG['60x60'] 占位图（灰色小方块）
                -->
                <img
                  :src="item.product?.image_url || PLACEHOLDER_IMG['60x60']"
                  :alt="item.product_name"
                />
              </div>

              <!-- 商品名称 + 价格 + 数量 -->
              <div class="goods-info">
                <!-- 商品名称，用快照字段 product_name（下单时存的） -->
                <div class="goods-name">{{ item.product_name || '商品名称' }}</div>
                <div class="goods-meta">
                  <!-- 
                    商品单价：用 Number() 转成数字，.toFixed(2) 保留 2 位小数
                    这样显示的价格就是 "99.00" 而不是 "99"
                  -->
                  <span class="goods-price">¥{{ Number(item.product_price).toFixed(2) }}</span>
                  <!-- 购买数量 -->
                  <span class="goods-quantity">x{{ item.quantity }}</span>
                </div>
              </div>
            </div>

            <!-- 
              如果商品超过 3 件，显示"等 N 件商品"的提示
              这样订单卡片不会太长
            -->
            <div v-if="getOrderItems(order).length > 3" class="more-goods">
              等 {{ getOrderItems(order).length }} 件商品
            </div>
          </div>

          <!-- ====== 订单卡片的底部：总金额 + 操作按钮 ====== -->
          <div class="order-footer">
            <div class="order-total">
              <!-- 商品总件数（调用函数计算） -->
              <span>共 {{ getTotalQuantity(order) }} 件商品，合计：</span>
              <!-- 订单总金额（红色大字） -->
              <span class="total-price">¥{{ Number(order.total_amount).toFixed(2) }}</span>
            </div>
            <div class="order-actions">
              <!-- 
                查看详情按钮
                @click 点击时调用 viewDetail(order) 函数，把整个订单对象传进去
              -->
              <el-button size="small" @click="viewDetail(order)">查看详情</el-button>

              <!-- 
                立即支付按钮
                v-if="order.status === 1" 只有当订单状态为 1（待支付）时才显示
                现在只是 UI 占位，后续可以接入支付接口
              -->
              <el-button
                v-if="order.status === 1"
                type="primary"
                size="small"
              >
                立即支付
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 
        情况 B：没有订单时（orders 数组长度为 0）
        v-else 是和上面 v-if 配对的：没有订单就显示空状态
      -->
      <div v-else class="empty-orders">
        <!-- Element Plus 的空状态组件 -->
        <el-empty description="暂无订单">
          <!-- 空状态里的按钮，点击跳转到商品列表页去购物 -->
          <el-button type="primary" @click="goShopping">去购物</el-button>
        </el-empty>
      </div>
    </div>

    <!-- 
      ====== 订单详情弹窗（el-dialog） ======
      v-model="detailDialogVisible" 是双向绑定：
        - 当 detailDialogVisible 为 true 时，弹窗显示
        - 当 detailDialogVisible 为 false 时，弹窗隐藏
      destroy-on-close：关闭弹窗时销毁内部 DOM（避免内存浪费）
    -->
    <el-dialog
      v-model="detailDialogVisible"
      title="订单详情"
      width="600px"
      destroy-on-close
    >
      <!-- 
        弹窗内容主体
        v-if="currentOrder" 只有当 currentOrder 有值时才显示内容
        这一步很重要！防止 currentOrder 为 null 时报错
      -->
      <div v-if="currentOrder" class="order-detail">

        <!-- ====== 基本信息区域 ====== -->

        <!-- 订单号 -->
        <div class="detail-row">
          <span class="detail-label">订单号：</span>
          <span class="detail-value">{{ currentOrder.order_no || currentOrder.id }}</span>
        </div>

        <!-- 下单时间 -->
        <div class="detail-row">
          <span class="detail-label">下单时间：</span>
          <span class="detail-value">{{ formatDate(currentOrder.created_at) }}</span>
        </div>

        <!-- 订单状态（用带颜色的标签显示） -->
        <div class="detail-row">
          <span class="detail-label">订单状态：</span>
          <el-tag :type="getStatusType(currentOrder.status)" effect="light">
            {{ getStatusText(currentOrder.status) }}
          </el-tag>
        </div>

        <!-- 收货人姓名 -->
        <div class="detail-row">
          <span class="detail-label">收货人：</span>
          <span class="detail-value">{{ currentOrder.receiver_name }}</span>
        </div>

        <!-- 联系电话 -->
        <div class="detail-row">
          <span class="detail-label">联系电话：</span>
          <span class="detail-value">{{ currentOrder.receiver_phone }}</span>
        </div>

        <!-- 收货地址 -->
        <div class="detail-row">
          <span class="detail-label">收货地址：</span>
          <span class="detail-value">{{ currentOrder.receiver_address }}</span>
        </div>

        <!-- 
          订单备注
          v-if="currentOrder.remark" 只有当备注不为空时才显示这一行
          没有备注就不显示了，界面更干净
        -->
        <div v-if="currentOrder.remark" class="detail-row">
          <span class="detail-label">备注：</span>
          <span class="detail-value">{{ currentOrder.remark }}</span>
        </div>

        <!-- 分割线（Element Plus 组件） -->
        <el-divider>商品清单</el-divider>

        <!-- ====== 商品清单区域（循环显示每一件商品） ====== -->
        <div class="detail-goods-list">

          <!-- 
            v-for 循环订单项
            双写兼容：items 字段（后端计算属性）或 order_items（后端原始字段）
          -->
          <div
            v-for="item in getOrderItems(currentOrder)"
            :key="item.id"
            class="detail-goods-item"
          >
            <!-- 商品名称 -->
            <div class="detail-goods-name">{{ item.product_name }}</div>
            <!-- 商品单价 × 数量 = 小计金额 -->
            <div class="detail-goods-info">
              <!-- 
                ?? 运算符：前面的变量为 null/undefined 时用后面的值
                item.product_price ?? item.price 兼容两个可能的字段名
              -->
              ¥{{ Number(item.product_price ?? item.price).toFixed(2) }}
              × {{ item.quantity }}
              <!-- 小计金额（红色字突出显示） -->
              <span class="detail-goods-subtotal">
                = ¥{{ Number(item.subtotal ?? (item.product_price ?? item.price) * item.quantity).toFixed(2) }}
              </span>
            </div>
          </div>
        </div>

        <!-- 分割线 -->
        <el-divider />

        <!-- ====== 总金额区域（右对齐） ====== -->
        <div class="detail-total-row">
          <span>共 {{ getTotalQuantity(currentOrder) }} 件商品，订单金额：</span>
          <span class="detail-total-price">¥{{ Number(currentOrder.total_amount).toFixed(2) }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<!-- 
  ====== script setup 部分 ======
  这里写页面的「脑子」：
    - 用到哪些外部工具（import）
    - 页面上有哪些数据（ref 响应式变量）
    - 页面上有哪些操作（函数）
    - 页面加载时要做什么（onMounted）
-->
<script setup lang="ts">

  // ===== 1. 导入需要的东西 =====

  // ref：创建响应式变量（变量变了，页面自动更新）
  // onMounted：页面加载完成时执行的钩子
  import { ref, onMounted } from 'vue'

  // useRouter：路由对象，用来跳转页面
  import { useRouter } from 'vue-router'

  // getMyOrders：获取订单列表的接口函数
  // getOrderDetail：获取单个订单详情的接口函数
  import { getMyOrders, getOrderDetail } from '@/api/order'

  // useUserStore：用户状态管理（Pinia store），里面存着当前登录用户的信息
  import { useUserStore } from '@/stores/user'

  // PLACEHOLDER_IMG：占位图常量（所有需要占位图的地方统一从这里取，避免外链加载失败）
  import { PLACEHOLDER_IMG } from '@/constants/placeholder'

  // ElMessage：Element Plus 的消息提示组件，用来弹出成功/错误提示
  import { ElMessage } from 'element-plus'

  // Order 类型定义（TypeScript 类型检查用，防止变量写错）
  import type { Order, OrderItem } from '@/types'


  // ===== 2. 获取全局对象 =====

  // router：路由控制器，通过它来跳转页面
  const router = useRouter()

  // userStore：用户信息仓库，通过它获取 userId 等信息
  const userStore = useUserStore()


  // ===== 3. 定义响应式变量（页面上会用到的数据） =====

  // loading：加载状态，控制转圈动画的显示/隐藏
  // 初始 false = 不转圈，请求数据时 true = 转圈
  const loading = ref(false)

  // orders：订单列表数组，存储从后端获取到的所有订单
  // 类型是 Order[]，初始为空数组
  const orders = ref<Order[]>([])

  // detailDialogVisible：订单详情弹窗的开关
  // true = 弹窗显示，false = 弹窗隐藏
  const detailDialogVisible = ref(false)

  // currentOrder：当前正在查看的订单数据
  // 点击「查看详情」时把订单对象塞进来
  // 类型是 Order | null，初始为 null（没有选择任何订单）
  const currentOrder = ref<Order | null>(null)


  // ===== 4. 定义函数（页面上的操作） =====

  /**
   * fetchOrders：获取当前用户的订单列表
   * 页面加载时自动调用
   */
  async function fetchOrders() {
    loading.value = true          // 开始加载：显示转圈动画
    try {
      // 调用后端接口，传入当前用户的 userId
      // await 等待接口返回结果
      const res: any = await getMyOrders(userStore.userId)

      // 处理返回数据：
      // 后端返回格式是 { code, msg, data: [订单数组] }
      // 所以优先取 res.data，没有就退化成 res，再没有就是空数组
      orders.value = res?.data || res || []
    } catch (error) {
      // 请求失败：在控制台打印错误 + 给用户弹一个错误提示
      console.error('获取订单列表失败:', error)
      ElMessage.error('获取订单列表失败')
    } finally {
      loading.value = false       // 结束加载：隐藏转圈动画（不管成功还是失败都要关）
    }
  }


  /**
   * getStatusText：把数字状态码转换成文字
   * 例如：传入 1 返回 '待支付'，传入 4 返回 '已完成'
   * @param status 订单状态数字（0-5）
   */
  function getStatusText(status: number): string {
    // 定义一个「字典」：状态码 → 对应文字
    const statusMap: Record<number, string> = {
      0: '待支付',
      1: '待支付',
      2: '已支付',
      3: '已发货',
      4: '已完成',
      5: '已取消'
    }
    // 从字典里取，取不到就返回 '未知状态'
    return statusMap[status] || '未知状态'
  }


  /**
   * getStatusType：把数字状态码转换成 Element Plus 标签的颜色类型
   * 不同状态用不同颜色区分，视觉上一目了然
   * @param status 订单状态数字（0-5）
   */
  function getStatusType(status: number): string {
    // warning=黄色, primary=蓝色, info=灰色, success=绿色
    const typeMap: Record<number, string> = {
      0: 'warning',   // 待支付 → 黄色（提醒）
      1: 'warning',   // 待支付 → 黄色（提醒）
      2: 'primary',   // 已支付 → 蓝色
      3: 'info',      // 已发货 → 灰色
      4: 'success',   // 已完成 → 绿色（成功）
      5: 'info'       // 已取消 → 灰色
    }
    return typeMap[status] || 'info'
  }


  /**
   * getTotalQuantity：计算一个订单的商品总件数
   * @param order 订单对象
   * @returns 商品总件数
   */
  function getOrderItems(order: Order | null): OrderItem[] {
    return order?.items ?? order?.order_items ?? []
  }

  function getTotalQuantity(order: Order): number {
    const items = getOrderItems(order)
    // reduce：把数组里每个 item.quantity 累加起来
    // 例如 [{quantity: 2}, {quantity: 3}] → 2 + 3 = 5
    return items.reduce((sum: number, item: any) => sum + item.quantity, 0)
  }


  /**
   * formatDate：把日期字符串格式化成人类看得懂的格式
   * 例如：'2026-08-02T14:30:00' → '2026年8月2日 14:30'
   * @param dateStr 日期字符串
   */
  function formatDate(dateStr: string): string {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',    // 年份：2026
      month: '2-digit',   // 月份：08
      day: '2-digit',     // 日：02
      hour: '2-digit',    // 小时：14
      minute: '2-digit'   // 分钟：30
    })
  }


  /**
   * goToProduct：点击商品项时跳转到商品详情页
   * @param productId 商品 ID
   */
  function goToProduct(productId: number) {
    // router.push 相当于「页面跳转」
    // 跳转到 /products/{productId}，例如 /products/5
    router.push(`/products/${productId}`)
  }


  /**
   * viewDetail：点击「查看详情」按钮时的处理函数
   * 1. 先调接口获取该订单的最新详情
   * 2. 把订单数据塞进 currentOrder 变量
   * 3. 把 detailDialogVisible 设为 true，弹窗就显示了！
   * @param order 点击的那个订单对象
   */
  async function viewDetail(order: Order) {
    try {
      // 内层 try：尝试调接口获取最新数据
      try {
        // 调用订单详情接口，传入订单 ID 和用户 ID
        const res: any = await getOrderDetail(order.id, userStore.userId)
        // 把后端返回的订单数据存到 currentOrder 里
        currentOrder.value = res?.data || res
      } catch {
        // 如果接口请求失败（比如网络问题），就用列表里已有的订单数据兜底
        // 这样用户还是能看到详情，而不是什么都看不到
        currentOrder.value = order
      }

      // 关键一步：把弹窗开关打开！
      // 因为我们用了 v-model="detailDialogVisible"
      // 所以只要设为 true，弹窗就自动显示
      detailDialogVisible.value = true
    } catch (error) {
      // 最外层的错误处理：打印错误 + 给用户提示
      console.error('打开订单详情失败:', error)
      ElMessage.error('打开订单详情失败')
    }
  }


  /**
   * goShopping：空订单状态下的「去购物」按钮
   * 跳转到商品列表页
   */
  function goShopping() {
    router.push('/products')
  }


  // ===== 5. 生命周期钩子：页面加载完成后自动执行 =====

  // onMounted：当页面渲染完成、挂载到 DOM 上之后执行
  // 这里调用 fetchOrders()，页面一打开就自动加载订单列表
  onMounted(() => {
    fetchOrders()
  })
</script>

<!-- 
  ====== style scoped 部分 ======
  这里定义页面的「长相」：颜色、大小、间距、布局等
  scoped 表示样式只在当前组件生效，不会污染其他页面
-->
<style scoped>

  /* 页面最外层容器：上下留 24px 间距 */
  .order-list {
    padding: 24px 0;
  }

  /* 页面标题 */
  .page-title {
    margin: 0 0 20px;        /* 下边距 20px */
    font-size: 24px;         /* 字体大小：24 像素 */
    font-weight: 600;        /* 字体加粗 */
    color: #303133;          /* 深灰色文字 */
  }

  /* 订单列表容器 */
  .orders-container {
    min-height: 400px;      /* 最小高度 400px，防止列表太短时页面塌陷 */
  }

  /* 订单列表（多张卡片纵向排列，卡片之间有 16px 间距） */
  .orders-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* 单个订单卡片：白底 + 圆角 + 柔和阴影 */
  .order-card {
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
    overflow: hidden;
    transition: box-shadow 0.3s;   /* 阴影变化有 0.3 秒过渡动画 */
  }

  /* 鼠标悬停时的卡片：阴影加深，有「浮起来」的感觉 */
  .order-card:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  }

  /* ====== 订单头部 ====== */
  .order-header {
    display: flex;
    align-items: center;
    justify-content: space-between;  /* 左右两端对齐 */
    padding: 16px 24px;
    background: #fafafa;             /* 浅灰背景 */
    border-bottom: 1px solid #f2f6fc;
  }

  /* 订单号 + 时间的容器 */
  .order-info {
    display: flex;
    align-items: center;
    gap: 20px;
  }

  /* 订单号文字 */
  .order-no {
    font-size: 14px;
    color: #303133;
    font-weight: 500;
  }

  /* 下单时间文字 */
  .order-time {
    font-size: 13px;
    color: #909399;
  }

  /* ====== 订单商品预览区 ====== */
  .order-goods {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px 24px;
    overflow-x: auto;   /* 商品太多时可以横向滚动 */
  }

  /* 单个商品项（横向排列：图片 + 名称 + 价格） */
  .goods-item {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 240px;
    cursor: pointer;           /* 鼠标变成手型，表示可点击 */
    padding: 8px;
    border-radius: 6px;
    transition: background-color 0.3s;
  }

  /* 鼠标悬停商品项：背景变浅灰 */
  .goods-item:hover {
    background: #f5f7fa;
  }

  /* 商品图片容器 */
  .goods-image {
    width: 60px;
    height: 60px;
    border-radius: 4px;
    overflow: hidden;
    background: #f0f0f0;
    flex-shrink: 0;             /* 不允许被压缩 */
  }

  /* 商品图片填充整个容器 */
  .goods-image img {
    width: 100%;
    height: 100%;
    object-fit: cover;       /* 图片按比例裁剪填满，不变形 */
  }

  /* 商品文字信息容器 */
  .goods-info {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }

  /* 商品名称 */
  .goods-name {
    font-size: 14px;
    color: #303133;
    overflow: hidden;            /* 超出隐藏 */
    text-overflow: ellipsis;     /* 文字过长显示省略号 ... */
    white-space: nowrap;        /* 不换行 */
  }

  /* 商品价格 + 数量的行 */
  .goods-meta {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 13px;
  }

  /* 商品价格（红色） */
  .goods-price {
    color: #f56c6c;
    font-weight: 500;
  }

  /* 商品数量（灰色） */
  .goods-quantity {
    color: #909399;
  }

  /* 「等 N 件商品」提示文字 */
  .more-goods {
    font-size: 13px;
    color: #909399;
    padding: 0 12px;
  }

  /* ====== 订单底部 ====== */
  .order-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 24px;
    border-top: 1px solid #f2f6fc;
  }

  /* 总金额文字 */
  .order-total {
    display: flex;
    align-items: baseline;
    gap: 4px;
    font-size: 14px;
    color: #606266;
  }

  /* 价格数字（红色大字） */
  .total-price {
    font-size: 20px;
    font-weight: 700;
    color: #f56c6c;
  }

  /* 操作按钮容器 */
  .order-actions {
    display: flex;
    gap: 12px;
  }

  /* ====== 空订单状态 ====== */
  .empty-orders {
    padding: 80px 0;
    text-align: center;
  }

  /* ====== 订单详情弹窗样式 ====== */

  /* 详情主体容器 */
  .order-detail {
    padding: 8px 0;
  }

  /* 每一行详情信息（标签 + 值横向排列） */
  .detail-row {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 8px 0;
    font-size: 14px;
    line-height: 1.6;
  }

  /* 左边的标签（右对齐、灰色） */
  .detail-label {
    flex-shrink: 0;
    width: 80px;
    color: #909399;
    text-align: right;
  }

  /* 右边的值（自动撑开、可以换行） */
  .detail-value {
    flex: 1;
    color: #303133;
    word-break: break-all;      /* 长文本自动换行，不撑破布局 */
  }

  /* 商品清单列表 */
  .detail-goods-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  /* 单个商品项（灰色圆角背景，两端对齐） */
  .detail-goods-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 12px;
    background: #fafafa;
    border-radius: 6px;
    font-size: 14px;
  }

  /* 商品名称（自动撑开，过长显示省略号） */
  .detail-goods-name {
    color: #303133;
    font-weight: 500;
    flex: 1;
    margin-right: 16px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* 商品单价 × 数量 */
  .detail-goods-info {
    color: #606266;
    flex-shrink: 0;
  }

  /* 小计金额（红色加粗） */
  .detail-goods-subtotal {
    margin-left: 12px;
    color: #f56c6c;
    font-weight: 600;
  }

  /* 总金额行（右对齐） */
  .detail-total-row {
    display: flex;
    justify-content: flex-end;
    align-items: baseline;
    gap: 8px;
    padding-top: 8px;
    font-size: 14px;
    color: #606266;
  }

  /* 总金额数字（最大最红最粗，突出显示） */
  .detail-total-price {
    font-size: 22px;
    font-weight: 700;
    color: #f56c6c;
  }
</style>