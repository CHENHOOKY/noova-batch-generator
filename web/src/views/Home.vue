<script setup>
import { ref, onMounted } from 'vue'
import { getPlugins, tint } from '../api.js'
const emit = defineEmits(['open'])
const plugins = ref([])
onMounted(async () => { plugins.value = await getPlugins() })
</script>

<template>
  <div class="p-8 max-w-6xl mx-auto">
    <div class="rounded-3xl p-10 text-white shadow-xl" style="background:linear-gradient(120deg,#312e81 0%,#6d28d9 45%,#0ea5e9 100%)">
      <h1 class="text-3xl font-extrabold tracking-wide">你好，我是 Noova 助手</h1>
      <p class="mt-2 text-white/75">AI 图像生成平台 · 批量处理 · 高效创作</p>
      <div class="mt-5 flex flex-wrap gap-2.5 text-xs">
        <span class="px-3 py-1.5 rounded-full bg-white/15">🧩 {{ plugins.length }} 个功能插件</span>
        <span class="px-3 py-1.5 rounded-full bg-white/15">⚡ 批量并发处理</span>
        <span class="px-3 py-1.5 rounded-full bg-white/15">🔒 本地安全运行</span>
      </div>
    </div>
    <div class="flex items-center justify-between mt-10 mb-5">
      <h2 class="text-xl font-bold text-slate-800">功能服务</h2><span class="text-sm text-slate-400">共 {{ plugins.length }} 个</span>
    </div>
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
      <button v-for="p in plugins" :key="p.id" :disabled="!p.enabled" @click="p.enabled && emit('open', p.id)"
        :class="['group text-left rounded-2xl p-6 border transition-all', p.enabled ? 'bg-white border-slate-200 hover:-translate-y-1 hover:shadow-xl hover:border-transparent cursor-pointer' : 'bg-white/60 border-slate-100 opacity-70 cursor-not-allowed']">
        <div class="w-12 h-12 rounded-2xl flex items-center justify-center text-2xl mb-4" :style="{ background: tint(p.color, 0.86), border: '1px solid ' + tint(p.color, 0.7) }">{{ p.icon }}</div>
        <div class="font-bold text-slate-800">{{ p.name }}</div>
        <p class="text-xs text-slate-500 mt-1.5 leading-relaxed h-8 overflow-hidden">{{ p.desc }}</p>
        <div class="mt-3 text-xs font-semibold transition" :class="p.enabled ? 'text-brand group-hover:translate-x-1' : 'text-slate-400'">{{ p.enabled ? '进入  →' : '即将上线' }}</div>
      </button>
    </div>
  </div>
</template>
