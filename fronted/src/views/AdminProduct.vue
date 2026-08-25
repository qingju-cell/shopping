<template>
  <div class="admin-product">
    <div class="page-header">
      <h2 class="page-title">
        <el-icon><Goods /></el-icon>
        商品管理
      </h2>
      <div class="header-actions">
        <router-link to="/admin/categories" class="cat-link">
          <el-button>
            <el-icon><List /></el-icon>
            去分类管理
          </el-button>
        </router-link>
        <el-button type="primary" @click="openDialog('create')">
          <el-icon><Plus /></el-icon>
          新增商品
        </el-button>
      </div>
    </div>

    <el-table v-loading="loading" :data="productList" border stripe style="width: 100%" empty-text="暂无商品">
      <el-table-column label="ID" prop="id" width="80" align="center" />
      <el-table-column label="图片" width="110" align="center">
        <template #default="{ row }">
          <el-image
            :src="row.image_url || placeholderImg"
            :preview-src-list="row.image_url ? [row.image_url] : []"
            fit="cover"
            style="width: 70px; height: 70px; border-radius: 6px; border: 1px solid #ebeef5"
            :preview-teleported="true"
          >
            <template #error>
              <div class="image-err">无图</div>
            </template>
          </el-image>
        </template>
      </el-table-column>
      <el-table-column label="商品名称" prop="name" min-width="160" show-overflow-tooltip />
      <el-table-column label="分类" width="120" align="center">
        <template #default="{ row }">
          <el-tag type="info" effect="plain">{{ getCategoryName(row.category_id) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="价格" width="110" align="right">
        <template #default="{ row }">
          <span class="price-cell">¥{{ Number(row.price).toFixed(2) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="库存" prop="stock" width="90" align="center" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="Number(row.status) === 1 ? 'success' : 'info'" effect="dark" size="small">
            {{ Number(row.status) === 1 ? '上架' : '下架' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openDialog('edit', row)">编辑</el-button>
          <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
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

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增商品' : '编辑商品'"
      width="560px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="90px"
        label-position="right"
      >
        <el-form-item label="商品名称" prop="name">
          <el-input v-model="formData.name" placeholder="请输入商品名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="分类" prop="category_id">
          <el-select v-model="formData.category_id" placeholder="请选择分类" clearable style="width: 100%">
            <el-option
              v-for="c in categories"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="3"
            placeholder="商品描述（可选）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="价格 (¥)" prop="price">
          <el-input-number v-model="formData.price" :min="0" :precision="2" :step="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="库存" prop="stock">
          <el-input-number v-model="formData.stock" :min="0" :step="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="formData.status">
            <el-radio :value="1">上架</el-radio>
            <el-radio :value="0">下架</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="图片 URL" prop="image_url">
          <el-input v-model="formData.image_url" placeholder="https://... （可选）" clearable />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">确认提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Goods, List, Plus } from '@element-plus/icons-vue'
import {
  getProducts,
  createProduct,
  updateProduct,
  deleteProduct
} from '@/api/product'
import { getCategoryListApi } from '@/api/category'
import { PLACEHOLDER_IMG } from '@/constants/placeholder'
import type { Product, Category, ProductCreate, ProductUpdate } from '@/types'

type DialogMode = 'create' | 'edit'

const placeholderImg = PLACEHOLDER_IMG['80x80']

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const dialogMode = ref<DialogMode>('create')
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const productList = ref<Product[]>([])
const categories = ref<Category[]>([])
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

const defaultForm = () => ({
  name: '',
  description: '' as string | null,
  price: 0 as number | string,
  stock: 0,
  category_id: null as number | null,
  image_url: '' as string | null,
  status: 1
})

const formData = reactive<ReturnType<typeof defaultForm>>(defaultForm())

const formRules: FormRules = {
  name: [
    { required: true, message: '请输入商品名称', trigger: 'blur' },
    { max: 100, message: '商品名称不能超过 100 字', trigger: 'blur' }
  ],
  price: [
    { required: true, message: '请输入价格', trigger: 'blur' },
    { validator: (_r, v, cb) => (Number(v) >= 0 ? cb() : cb(new Error('价格不能为负数'))), trigger: 'change' }
  ],
  stock: [
    { validator: (_r, v, cb) => (Number(v) >= 0 ? cb() : cb(new Error('库存不能为负数'))), trigger: 'change' }
  ]
}

const categoryMap = computed(() => {
  const m: Record<number, string> = {}
  categories.value.forEach(c => (m[c.id] = c.name))
  return m
})
function getCategoryName(id: number | null | undefined) {
  if (!id) return '未分类'
  return categoryMap.value[id] || '未分类'
}

async function fetchCategories() {
  try {
    const res: any = await getCategoryListApi()
    categories.value = (res.data || res) as Category[]
  } catch (e) {
    console.error('获取分类失败', e)
    categories.value = []
  }
}

async function fetchProducts() {
  loading.value = true
  try {
    const res: any = await getProducts({ page: page.value, page_size: pageSize.value })
    const payload = res.data ?? res
    productList.value = (payload.list ?? payload.items ?? []) as Product[]
    total.value = Number(payload.total ?? 0)
  } catch (e: any) {
    ElMessage.error(e?.message || '获取商品列表失败')
    productList.value = []
  } finally {
    loading.value = false
  }
}

function resetForm() {
  const d = defaultForm()
  Object.keys(d).forEach(k => {
    ;(formData as any)[k] = (d as any)[k]
  })
  editingId.value = null
  formRef.value?.resetFields()
}

function openDialog(mode: DialogMode, row?: Product) {
  dialogMode.value = mode
  resetForm()
  if (mode === 'edit' && row) {
    editingId.value = row.id
    formData.name = row.name
    formData.description = row.description ?? ''
    formData.price = Number(row.price)
    formData.stock = Number(row.stock ?? 0)
    formData.category_id = row.category_id ?? null
    formData.image_url = row.image_url ?? ''
    formData.status = Number((row as any).status ?? 1)
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async valid => {
    if (!valid) return
    submitting.value = true
    try {
      const payload: ProductCreate | ProductUpdate = {
        name: formData.name,
        description: formData.description || null,
        price: Number(formData.price),
        stock: Number(formData.stock || 0),
        category_id: formData.category_id ?? null,
        image_url: formData.image_url || null,
        ...(dialogMode.value === 'edit' ? {} : { status: (formData as any).status ?? 1 })
      }
      if (dialogMode.value === 'create') {
        await createProduct(payload as ProductCreate)
        ElMessage.success('新增商品成功')
      } else if (editingId.value) {
        await updateProduct(editingId.value, payload as ProductUpdate)
        ElMessage.success('编辑商品成功')
      }
      dialogVisible.value = false
      fetchProducts()
    } catch (e: any) {
      ElMessage.error(e?.message || '提交失败')
    } finally {
      submitting.value = false
    }
  })
}

async function handleDelete(row: Product) {
  try {
    await ElMessageBox.confirm(`确定要删除商品「${row.name}」吗？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '确认删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  loading.value = true
  try {
    await deleteProduct(row.id)
    ElMessage.success('删除成功')
    fetchProducts()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await fetchCategories()
  fetchProducts()
})
</script>

<style scoped>
.admin-product {
  padding: 20px;
  background: #fff;
  border-radius: 10px;
  min-height: calc(100vh - 200px);
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 20px;
  margin: 0;
  color: #303133;
}
.header-actions {
  display: flex;
  gap: 10px;
}
.cat-link { text-decoration: none; }
.price-cell {
  color: #f56c6c;
  font-weight: 600;
  font-size: 14px;
}
.image-err {
  width: 70px;
  height: 70px;
  background: #f5f7fa;
  color: #909399;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 12px;
}
.pagination-wrap {
  margin-top: 18px;
  display: flex;
  justify-content: flex-end;
}
</style>