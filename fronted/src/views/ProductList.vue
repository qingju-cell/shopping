<template>
  <div class="product-list">
    <!-- 搜索和筛选区域 -->
    <div class="filter-section">
      <div class="search-bar">
        <el-input
            v-model="keyword"
            placeholder="搜索商品..."
            size="large"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleSearch"
        >
          <template #prefix>
            <el-icon>
              <Search/>
            </el-icon>
          </template>
        </el-input>
        <el-button type="primary" size="large" @click="handleSearch">搜索</el-button>
      </div>

      <div class="category-tabs">
        <el-tag
            :type="!currentCategoryId ? 'primary' : 'info'"
            class="category-tag"
            effect="plain"
            @click="selectCategory(null)"
        >
          全部
        </el-tag>
        <el-tag
            v-for="category in categories"
            :key="category.id"
            :type="currentCategoryId === category.id ? 'primary' : 'info'"
            class="category-tag"
            effect="plain"
            @click="selectCategory(category.id)"
        >
          {{ category.name }}
        </el-tag>
      </div>
    </div>


    <!-- 商品列表 -->
    <div v-loading="loading" class="products-grid">
      <div
          v-for="product in products"
          :key="product.id"
          class="product-card"
          @click="goToDetail(product.id)"
      >
        <div class="product-image">
          <img
              :src="product.image_url || PLACEHOLDER_IMG['300x300']"
              :alt="product.name"
          />
        </div>
        <div class="product-info">
          <h3 class="product-name">{{ product.name }}</h3>
          <p class="product-desc">{{ product.description || '暂无描述' }}</p>
          <div class="product-footer">
            <span class="product-price">¥{{ Number(product.price).toFixed(2) }}</span>
            <el-button
                type="primary"
                size="small"
                circle
                @click.stop="addToCart(product.id)"
            >
              <el-icon>
                <ShoppingCart/>
              </el-icon>
            </el-button>
          </div>
        </div>
      </div>
    </div>
    <!-- 空状态 -->
    <div v-if="!loading && products.length === 0" class="empty-state">
      <el-empty description="暂无商品"/>
    </div>

    <!-- 分页 -->
    <div v-if="total > 0" class="pagination">
      <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 30, 50]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="fetchProducts"
          @current-change="fetchProducts"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import {ref, onMounted} from 'vue'
import {useRouter} from 'vue-router'
import {Search, ShoppingCart} from '@element-plus/icons-vue'
import {getProducts} from '@/api/product'
import {getCategoryListApi} from '@/api/category'
import {useCartStore} from '@/stores/cart'
import { PLACEHOLDER_IMG } from '@/constants/placeholder'
import type {Product, Category} from '@/types'

const router = useRouter()
const cartStore = useCartStore()

const loading = ref(false)
const products = ref<Product[]>([])
const categories = ref<Category[]>([])
const keyword = ref('')
const currentCategoryId = ref<number | null>(null)
const page = ref(1)
const pageSize = ref(12)
const total = ref(0)

async function fetchCategories() {
  try {
    const res: any = await getCategoryListApi()
    categories.value = res.data || res || []
  } catch (error) {
    console.error('获取分类失败:', error)
  }
}

async function fetchProducts() {
  loading.value = true
  try {
    const params: any = {
      page: page.value,
      page_size: pageSize.value
    }

    if (currentCategoryId.value) {
      params.category_id = currentCategoryId.value
    }
    if (keyword.value.trim()) {
      params.keyword = keyword.value.trim()
    }

    const res: any = await getProducts(params)

    if (res.list) {
      products.value = res.list
      total.value = res.total || 0
    } else if (res.items) {
      products.value = res.items
      total.value = res.total || 0
    } else if (res.data?.list) {
      products.value = res.data.list
      total.value = res.data.total || 0
    } else if (res.data?.items) {
      products.value = res.data.items
      total.value = res.data.total || 0
    } else if (Array.isArray(res)) {
      products.value = res
      total.value = res.length
    } else {
      products.value = []
      total.value = 0
    }
  } catch (error) {
    console.error('获取商品列表失败:', error)
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  fetchProducts()
}

function selectCategory(categoryId: number | null) {
  currentCategoryId.value = categoryId
  page.value = 1
  fetchProducts()
}

function goToDetail(productId: number) {
  router.push(`/products/${productId}`)
}

async function addToCart(productId: number) {
  await cartStore.addItem(productId, 1)
}

onMounted(() => {
  fetchCategories()
  fetchProducts()
})
</script>

<style scoped>
.product-list {
  padding: 24px 0;
}

.filter-section {
  background: #fff;
  padding: 20px 24px;
  border-radius: 8px;
  margin-bottom: 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.search-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.search-bar .el-input {
  flex: 1;
  max-width: 400px;
}

.category-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.category-tag {
  cursor: pointer;
  font-size: 14px;
  padding: 6px 16px;
  transition: all 0.3s;
}

.category-tag:hover {
  transform: translateY(-1px);
}

.products-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 20px;
  min-height: 400px;
}

.product-card {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
}

.product-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
}

.product-image {
  width: 100%;
  height: 200px;
  overflow: hidden;
  background: #f5f5f5;
}

.product-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.product-card:hover .product-image img {
  transform: scale(1.05);
}

.product-info {
  padding: 16px;
}

.product-name {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-desc {
  margin: 0 0 12px;
  font-size: 13px;
  color: #909399;
  height: 36px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.product-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.product-price {
  font-size: 20px;
  font-weight: 600;
  color: #f56c6c;
}

.empty-state {
  padding: 80px 0;
  text-align: center;
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: 32px;
}
</style>