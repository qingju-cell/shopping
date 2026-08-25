<template>
  <div class="admin-category">
    <div class="page-header">
      <h2 class="page-title">
        <el-icon><List /></el-icon>
        分类管理
      </h2>
      <div class="header-actions">
        <router-link to="/admin/products" class="prod-link">
          <el-button>
            <el-icon><Goods /></el-icon>
            去商品管理
          </el-button>
        </router-link>
        <el-button type="primary" @click="openDialog('create')">
          <el-icon><Plus /></el-icon>
          新增分类
        </el-button>
      </div>
    </div>

    <el-table v-loading="loading" :data="categories" border stripe style="width: 100%" empty-text="暂无分类">
      <el-table-column label="ID" prop="id" width="80" align="center" />
      <el-table-column label="分类名称" prop="name" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <span style="font-weight: 500">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="父分类ID" prop="parent_id" width="110" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.parent_id && row.parent_id > 0" type="info" effect="plain" size="small">
            {{ row.parent_id }}
          </el-tag>
          <span v-else style="color: #909399">— 顶级 —</span>
        </template>
      </el-table-column>
      <el-table-column label="排序权重" prop="sort" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="Number(row.sort) === 0 ? 'info' : 'warning'" effect="plain">
            {{ row.sort }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="180" align="center">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" align="center" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="openDialog('edit', row)">编辑</el-button>
          <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新增分类' : '编辑分类'"
      width="480px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="100px"
        label-position="right"
      >
        <el-form-item label="分类名称" prop="name">
          <el-input v-model="formData.name" placeholder="请输入分类名称，如：手机数码" maxlength="50" show-word-limit />
        </el-form-item>
        <el-form-item label="父分类" prop="parent_id">
          <el-select
            v-model="formData.parent_id"
            placeholder="不选则为顶级分类"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="c in parentOptions"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
          <div class="form-tip">可选，留空为顶级分类；数值越大排序越靠后。</div>
        </el-form-item>
        <el-form-item label="排序权重" prop="sort">
          <el-input-number v-model="formData.sort" :min="0" :max="9999" :step="1" style="width: 100%" />
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
  getCategoryListApi,
  addCategoryApi,
  updateCategoryApi,
  deleteCategoryApi
} from '@/api/category'
import type { Category, CategoryCreate, CategoryUpdate } from '@/types'

type DialogMode = 'create' | 'edit'

const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const dialogMode = ref<DialogMode>('create')
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const categories = ref<Category[]>([])

const defaultForm = () => ({
  name: '',
  parent_id: 0 as number | undefined,
  sort: 0
})

const formData = reactive<ReturnType<typeof defaultForm>>(defaultForm())

const formRules: FormRules = {
  name: [
    { required: true, message: '请输入分类名称', trigger: 'blur' },
    { max: 50, message: '分类名称不能超过 50 字', trigger: 'blur' }
  ]
}

const parentOptions = computed(() => {
  // 编辑时排除自己，避免形成环
  const exclude = editingId.value
  return categories.value.filter(c => !exclude || c.id !== exclude)
})

function formatTime(t: string | null | undefined) {
  if (!t) return '—'
  try {
    const d = new Date(t)
    const pad = (n: number) => n.toString().padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return '—'
  }
}

async function fetchCategories() {
  loading.value = true
  try {
    const res: any = await getCategoryListApi()
    categories.value = (res.data || res || []) as Category[]
  } catch (e: any) {
    ElMessage.error(e?.message || '获取分类列表失败')
    categories.value = []
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

function openDialog(mode: DialogMode, row?: Category) {
  dialogMode.value = mode
  resetForm()
  if (mode === 'edit' && row) {
    editingId.value = row.id
    formData.name = row.name
    formData.parent_id = row.parent_id ?? 0
    formData.sort = row.sort ?? 0
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async valid => {
    if (!valid) return
    submitting.value = true
    try {
      const payload: CategoryCreate | CategoryUpdate = {
        name: formData.name,
        parent_id: formData.parent_id ?? 0,
        sort: formData.sort ?? 0
      }
      if (dialogMode.value === 'create') {
        await addCategoryApi(payload as CategoryCreate)
        ElMessage.success('新增分类成功')
      } else if (editingId.value) {
        await updateCategoryApi(editingId.value, payload as CategoryUpdate)
        ElMessage.success('编辑分类成功')
      }
      dialogVisible.value = false
      fetchCategories()
    } catch (e: any) {
      ElMessage.error(e?.message || '提交失败')
    } finally {
      submitting.value = false
    }
  })
}

async function handleDelete(row: Category) {
  try {
    await ElMessageBox.confirm(
      `确定要删除分类「${row.name}」吗？\n注意：该分类下的商品不会被删除，但分类会变为"未分类"。`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '确认删除',
        cancelButtonText: '取消'
      }
    )
  } catch {
    return
  }
  loading.value = true
  try {
    await deleteCategoryApi(row.id)
    ElMessage.success('删除成功')
    fetchCategories()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchCategories()
})
</script>

<style scoped>
.admin-category {
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
.prod-link { text-decoration: none; }
.form-tip {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}
</style>