"""Docker 环境中的只读 API 冒烟测试。"""

import os

import requests

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT_SECONDS = 10


def get_json(path: str, **params):
    response = requests.get(
        f"{BASE_URL}{path}", params=params, timeout=TIMEOUT_SECONDS
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == 200, payload
    return payload["data"]


def test_openapi_docs_are_available():
    response = requests.get(f"{BASE_URL}/docs", timeout=TIMEOUT_SECONDS)
    assert response.status_code == 200
    assert "Swagger UI" in response.text


def test_category_list_has_valid_parent_ids():
    categories = get_json("/api/category/")
    assert isinstance(categories, list)
    assert all(isinstance(category["parent_id"], int) for category in categories)


def test_product_page_and_detail_are_available():
    page = get_json("/api/products", page=1, page_size=3)
    assert isinstance(page["total"], int)
    assert isinstance(page["list"], list)
    assert page["total"] >= len(page["list"])

    # GitHub Actions 使用全新的空数据库；本机有商品时额外验证详情接口。
    if not page["list"]:
        return

    product_id = page["list"][0]["id"]
    product = get_json(f"/api/products/{product_id}")
    assert product["id"] == product_id
    assert product["name"]
