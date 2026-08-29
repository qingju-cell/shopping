# ============================================================
# _init_.py —— 模型包初始化文件
# 功能：统一导出所有 ORM 模型，方便其他模块一次性导入
# 使用方式：from app.models import User, Product, Order, OrderItem
# ============================================================

# 导入所有模型类，这样在其他地方可以直接使用
# 例如：from app.models import User
from app.models.user import User
from app.models.category import Category
from app.models.product import Product
from app.models.cart import CartItem
from app.models.order import Order, OrderItem
from app.models.ai_chat_message import AIChatMessage