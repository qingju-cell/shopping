"""AI 客服的消息持久化、结构化记忆和上下文组装。

本文件不调用大模型、不执行 RAG；只负责回答三件事：
1. 用户与 AI 的可见聊天记录如何保存；
2. 每段会话的精炼事实（偏好、预算、待确认订单）如何保存；
3. 这些数据如何变成模型可阅读、长度受控的上下文。
"""

# 标准库：文件版教学记忆、数据库 JSON 字段、正则提取预算、唯一会话编号。
import json
import os
import re
import uuid
from datetime import datetime


def get_memory_file_path() -> str:
    """返回命令行教学模式使用的 chat_history.json 路径。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.json")


def load_memory() -> list[dict]:
    """读取命令行教学模式的 JSON 对话历史；文件不存在时返回空列表。"""
    memory_file = get_memory_file_path()
    if not os.path.exists(memory_file):
        print(f"📝 没找到历史记忆文件，开始新对话（{os.path.basename(memory_file)}）")
        return []
    try:
        with open(memory_file, "r", encoding="utf-8") as file:
            history = json.load(file)
        print(f"💾 已加载历史记忆：{len(history) // 2} 轮对话")
        return history
    except Exception as error:
        print(f"⚠️ 记忆文件读取失败，忽略历史：{error}")
        return []


def save_memory(history: list[dict]) -> None:
    """保存命令行教学模式的对话历史；网站版聊天不使用这个文件。"""
    memory_file = get_memory_file_path()
    try:
        with open(memory_file, "w", encoding="utf-8") as file:
            json.dump(history, file, ensure_ascii=False, indent=2)
        print(f"💾 记忆已保存：{len(history) // 2} 轮 → {os.path.basename(memory_file)}")
    except Exception as error:
        print(f"⚠️ 记忆保存失败：{error}")


def _get_db_session():
    """延迟创建 SQLAlchemy Session，避免 import 本模块时立刻连接数据库。"""
    from app.database import SessionLocal
    return SessionLocal()


def save_message_to_db(user_id: int, session_id: str, role: str, content: str, intent: str = "") -> None:
    """将用户可见的单条问答写入 ai_chat_messages，不保存内部工具调用。"""
    db = _get_db_session()
    try:
        from app.models.ai_chat_message import AIChatMessage
        db.add(AIChatMessage(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            intent=intent,
        ))
        db.commit()
    except Exception as error:
        db.rollback()
        print(f"⚠️ 消息入库失败：{error}")
    finally:
        db.close()


def load_history_from_db(user_id: int, session_id: str | None = None, limit: int = 20) -> list[dict]:
    """读取某段会话的用户可见聊天记录，供前端恢复聊天窗口。"""
    db = _get_db_session()
    try:
        from app.models.ai_chat_message import AIChatMessage
        query = db.query(AIChatMessage).filter(AIChatMessage.user_id == user_id)
        if session_id:
            query = query.filter(AIChatMessage.session_id == session_id)
        messages = query.order_by(AIChatMessage.created_at.asc()).limit(limit).all()
        return [
            {
                "role": message.role,
                "content": message.content,
                "time": message.created_at.isoformat() if message.created_at else "",
            }
            for message in messages
        ]
    except Exception as error:
        print(f"⚠️ 历史消息加载失败：{error}")
        return []
    finally:
        db.close()


def generate_session_id() -> str:
    """生成用于关联同一段 AI 对话的短 UUID。"""
    return uuid.uuid4().hex[:12]


# 完整消息存在 ai_chat_messages；这里只保存稳定、可压缩的事实。
_MEMORY_STOP = {"商品", "产品", "推荐", "购买", "想买", "有没有", "便宜", "更便宜", "价格", "多少钱", "有货", "库存"}
_PREFERENCES = {"轻薄", "游戏", "学生", "办公", "编程", "拍照", "续航", "大屏", "小屏", "高端", "性价比", "低价", "静音", "便携", "送礼"}


def _memory_words(text: str) -> list[str]:
    """把关键词文本拆成短词，去重并过滤无区分度的词。"""
    words = re.split(r"[\s,，、/|]+", text or "")
    result = []
    for word in words:
        word = word.strip()[:20]
        if word and word not in _MEMORY_STOP and word not in result:
            result.append(word)
    return result


def _budget(text: str) -> tuple[int | None, int | None]:
    """从自然语言识别预算，返回（最低价, 最高价）；无法识别时返回 None。"""
    text = text.replace(",", "")
    match = re.search(r"(\d{2,6})\s*(?:元)?\s*(?:到|至|[-~～])\s*(\d{2,6})\s*(?:元)?", text)
    if match:
        return tuple(sorted((int(match.group(1)), int(match.group(2)))))
    match = re.search(r"(?:预算|不超过|低于|小于|最多|控制在)\s*(\d{2,6})\s*(?:元)?|(?:\d{2,6})\s*(?:元)?\s*(?:以内|以下)", text)
    if match:
        return None, int(match.group(1) or re.search(r"\d{2,6}", match.group(0)).group())
    match = re.search(r"(?:不少于|至少|起步)\s*(\d{2,6})\s*(?:元)?", text)
    return (int(match.group(1)), None) if match else (None, None)


def update_structured_memory(memory: dict | None, question: str, intent: str, search_keywords: str, topic_mode: str = "continue") -> dict:
    """更新商品偏好、预算和关键词，保留可能已存在的 pending_order 草稿。"""
    updated = dict(memory or {})
    updated["last_intent"] = intent
    updated["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if intent != "product":
        return updated
    if topic_mode == "new":
        for key in ("topic_keywords", "preferences", "budget_min", "budget_max"):
            updated.pop(key, None)
    old_topics = [item for item in updated.get("topic_keywords", []) if isinstance(item, str)]
    words = _memory_words(search_keywords)
    updated["topic_keywords"] = (old_topics + [item for item in words if item not in old_topics])[-8:]
    old_preferences = [item for item in updated.get("preferences", []) if isinstance(item, str)]
    found = [item for item in words + _memory_words(question) if item in _PREFERENCES]
    updated["preferences"] = (old_preferences + [item for item in found if item not in old_preferences])[-8:]
    low, high = _budget(question)
    if low is not None:
        updated["budget_min"] = low
    if high is not None:
        updated["budget_max"] = high
    return updated


def format_structured_memory_for_prompt(memory: dict | None) -> str:
    """把偏好和待确认订单压缩为模型可读文本，不泄露已保存的电话或地址。"""
    if not memory:
        return ""

    lines = []
    if memory.get("topic_keywords"):
        lines.extend(["【长期购物记忆（仅在与当前问题相关时参考）】", f"关注商品：{'、'.join(memory['topic_keywords'])}"])
        low, high = memory.get("budget_min"), memory.get("budget_max")
        if low is not None and high is not None:
            lines.append(f"预算：{low}-{high} 元")
        elif high is not None:
            lines.append(f"预算上限：{high} 元")
        elif low is not None:
            lines.append(f"预算下限：{low} 元")
        if memory.get("preferences"):
            lines.append(f"偏好：{'、'.join(memory['preferences'])}")

    draft = memory.get("pending_order")
    if isinstance(draft, dict) and draft.get("status") in {"collecting_receiver", "ready_for_confirmation"}:
        item = next(iter(draft.get("items") or []), {})
        missing_names = {
            "receiver_name": "收货人姓名",
            "receiver_phone": "收货电话",
            "receiver_address": "收货地址",
        }
        missing = draft.get("missing_receiver_fields") or [
            key for key in missing_names if not str(draft.get(key, "")).strip()
        ]
        lines.extend([
            "【待确认订单（不可直接创建或扣库存）】",
            f"商品：{item.get('product_name', '未知商品')}（ID: {item.get('product_id', '未知')}），数量：{item.get('quantity', '未知')}",
            f"草稿状态：{draft['status']}",
            "待补充：" + ("、".join(missing_names.get(key, key) for key in missing) if missing else "无；等待用户确认"),
        ])
    return "\n".join(lines)


def load_structured_memory(user_id: int, session_id: str) -> dict:
    """从 ai_chat_sessions.memory_json 读取当前会话的结构化状态。"""
    db = _get_db_session()
    try:
        from app.models.ai_chat_session import AIChatSession
        row = db.query(AIChatSession).filter(
            AIChatSession.user_id == user_id,
            AIChatSession.session_id == session_id,
        ).first()
        value = json.loads(row.memory_json or "{}") if row else {}
        return value if isinstance(value, dict) else {}
    except Exception as error:
        print(f"⚠️ 会话记忆读取失败：{error}")
        return {}
    finally:
        db.close()


def save_structured_memory(user_id: int, session_id: str, memory: dict) -> None:
    """将偏好和订单草稿序列化为 JSON，写入或更新当前会话。"""
    db = _get_db_session()
    try:
        from app.models.ai_chat_session import AIChatSession
        row = db.query(AIChatSession).filter(
            AIChatSession.user_id == user_id,
            AIChatSession.session_id == session_id,
        ).first()
        if not row:
            row = AIChatSession(user_id=user_id, session_id=session_id)
            db.add(row)
        row.memory_json = json.dumps(memory, ensure_ascii=False)
        db.commit()
    except Exception as error:
        db.rollback()
        print(f"⚠️ 会话记忆保存失败：{error}")
    finally:
        db.close()


def merge_memory_into_context(history_text: str, memory: dict) -> str:
    """合并精炼结构化记忆与最近原始对话，形成一次模型调用的上下文。"""
    structured = format_structured_memory_for_prompt(memory)
    if not structured:
        return history_text
    return f"{structured}\n\n【最近对话】\n{history_text or '（无最近对话）'}"


def remove_structured_memory_from_context(context_text: str) -> str:
    """用户开启新商品话题时，移除旧偏好，只保留最近原始对话。"""
    marker = "\n\n【最近对话】\n"
    prefix, separator, recent_history = context_text.partition(marker)
    if separator and prefix.startswith("【长期购物记忆（仅在与当前问题相关时参考）】"):
        return recent_history
    return context_text


def format_memory_for_prompt(history: list[dict], max_turns: int = 6) -> str:
    """把最近几条用户可见消息转为“用户：…\n小购：…”文本，控制 Prompt 长度。"""
    if not history:
        return "（无历史对话）"
    recent = history[-max_turns:]
    lines = []
    for message in recent:
        role_name = "用户" if message["role"] == "user" else "小购"
        lines.append(f"{role_name}：{message['content']}")
    return "\n".join(lines)


def _extract_last_user_msg(history_text: str) -> str:
    """从格式化历史中提取除最后一条外的用户消息，供旧教学逻辑兼容使用。"""
    lines = history_text.strip().split("\n")
    user_messages = [line[3:].strip() for line in lines if line.startswith("用户：")]
    return " ".join(user_messages[:-1]) if len(user_messages) >= 2 else ""
