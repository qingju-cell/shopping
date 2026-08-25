<template>
  <Layout v-if="useLayout">
    <router-view />
  </Layout>
  <router-view v-else />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Layout from '@/layouts/Layout.vue'

const route = useRoute()

const useLayout = computed(() => {
  return route.meta.layout !== false
})
</script>

<style>
/* 全局样式在 global.css 中 */
</style>
