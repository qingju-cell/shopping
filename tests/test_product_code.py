"""商品公开编号的无数据库单元测试。"""

from datetime import datetime

from app.schemas.product import ProductResponse


def test_product_response_derives_public_code_from_an_old_cached_dict():
    """旧 Redis 缓存即使没有 product_code，接口也应自动得到 PR 编号。"""
    product = ProductResponse.model_validate({
        "id": 500,
        "name": "测试商品",
        "description": None,
        "price": 99.0,
        "stock": 3,
        "category_id": 1,
        "image_url": None,
        "status": 1,
        "created_at": datetime(2026, 9, 10),
    })

    assert product.product_code == "PR500"
