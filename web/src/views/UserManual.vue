<script setup>
import { ref, onMounted, watch } from 'vue'
import { getManualPages, getManualPage } from '../api.js'
defineEmits(['back'])
const pages = ref([])
const cur = ref('')
const html = ref('')
onMounted(async () => { pages.value = await getManualPages(); if (pages.value.length) select(pages.value[0].id) })
async function select(id) { cur.value = id; const r = await getManualPage(id); html.value = r.html }
</script>

<template>
  <div class="p-8 max-w-6xl mx-auto">
    <button @click="$emit('back')" class="text-slate-500 hover:text-brand text-sm mb-4 transition">← 返回首页</button>
    <h1 class="text-3xl font-extrabold text-slate-800">📚 使用手册</h1>
    <p class="text-slate-500 mt-1">Noova 全部功能的图文使用指南</p>
    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mt-8">
      <div class="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
        <div class="text-xs font-bold text-slate-400 tracking-widest px-2 pb-3">目  录</div>
        <button v-for="p in pages" :key="p.id" @click="select(p.id)"
          :class="['w-full text-left px-3 py-2 rounded-lg text-sm transition', cur === p.id ? 'bg-brand-soft text-brand font-semibold' : 'text-slate-600 hover:bg-slate-100']">{{ p.icon }}&nbsp;{{ p.title }}</button>
      </div>
      <div class="lg:col-span-3 bg-white rounded-2xl border border-slate-200 p-8 shadow-sm overflow-auto">
        <div class="manual prose max-w-none text-slate-700" v-html="html"></div>
      </div>
    </div>
  </div>
</template>
