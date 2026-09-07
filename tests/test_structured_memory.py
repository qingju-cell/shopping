from app.AI.ai_core import classify_intent_and_expand, format_structured_memory_for_prompt, merge_memory_into_context, remove_structured_memory_from_context, update_structured_memory

def test_product_memory_keeps_topic_budget_and_preferences():
    memory = update_structured_memory({}, "想买轻薄笔记本，预算 3000 到 5000 元", "product", "笔记本 轻薄 学生 编程")
    assert memory["topic_keywords"] == ["笔记本", "轻薄", "学生", "编程"]
    assert memory["budget_min"] == 3000
    assert memory["budget_max"] == 5000
    assert "轻薄" in memory["preferences"]

def test_follow_up_keeps_existing_budget():
    memory = update_structured_memory({"topic_keywords":["笔记本"], "budget_max":5000}, "有更便宜的吗？", "product", "笔记本 低价")
    assert memory["budget_max"] == 5000
    assert memory["topic_keywords"] == ["笔记本", "低价"]

def test_classifier_returns_new_topic_mode_without_real_llm_call():
    class FakeLLM:
        def invoke(self, _prompt):
            return type("Response", (), {"content": "product|new|手机 拍照"})()

    assert classify_intent_and_expand("我想买拍照手机", FakeLLM(), "刚才在聊笔记本") == (
        "product", "new", "手机 拍照",
    )
def test_new_topic_resets_old_product_conditions():
    memory = update_structured_memory(
        {"topic_keywords": ["笔记本", "轻薄"], "budget_max": 5000, "preferences": ["轻薄", "学生"]},
        "我想买一台拍照好的手机", "product", "手机 拍照", topic_mode="new",
    )
    assert memory["topic_keywords"] == ["手机", "拍照"]
    assert "budget_max" not in memory
    assert "学生" not in memory["preferences"]
def test_new_topic_does_not_send_old_memory_to_product_answer():
    context = merge_memory_into_context("用户：帮我看看", {"topic_keywords": ["笔记本"], "budget_max": 5000})
    assert remove_structured_memory_from_context(context) == "用户：帮我看看"
def test_prompt_is_compact():
    text = format_structured_memory_for_prompt({"topic_keywords":["笔记本"], "budget_max":5000, "preferences":["轻薄"]})
    assert "关注商品：笔记本" in text
    assert "预算上限：5000 元" in text
    assert "偏好：轻薄" in text