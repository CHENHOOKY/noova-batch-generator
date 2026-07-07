<script setup>
import { ref } from 'vue'
import { pickFolder } from '../api.js'
import { useTask } from '../composables/useTask.js'
import LogPanel from '../components/LogPanel.vue'
defineEmits(['back'])
const t = useTask()
const inputDir = ref(''); const outputDir = ref(''); const fmt = ref('png')
const chooseIn = async () => { const r = await pickFolder('选择图片文件夹'); if (r.path) inputDir.value = r.path }
const chooseOut = async () => { const r = await pickFolder('选择输出目录'); if (r.path) outputDir.value = r.path }
const start = () => t.start('upscale', { input_dir: inputDir.value, output_dir: outputDir.value, output_format: fmt.value })
</script>
<template>
  <div class="p-8 max-w-5xl mx-auto space-y-5">
    <div><button @click="$emit('back')" class="text-slate-500 hover:text-brand text-sm transition">← 返回首页</button>
      <h1 class="text-2xl font-extrabold text-slate-800 mt-1">🔍 图像放大</h1>
      <p class="text-slate-500 text-sm mt-0.5">Real-ESRGAN 深度超分，纯 CPU 4 倍放大，支持 PNG / JPG / WebP</p></div>
    <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
      <h2 class="font-bold text-slate-800 mb-4 text-sm">参数设置</h2>
      <div class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">图片文件夹</label><div class="flex gap-2"><input v-model="inputDir" readonly placeholder="未选择" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="chooseIn" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">输出目录</label><div class="flex gap-2"><input v-model="outputDir" readonly placeholder="未选择" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="chooseOut" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div></div>
        </div>
        <div class="md:w-1/3"><label class="block text-xs font-medium text-slate-500 mb-1">输出格式</label><select v-model="fmt" class="w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option value="png">PNG（无损）</option><option value="jpg">JPG（质量 95）</option><option value="webp">WebP（质量 95）</option></select></div>
        <button @click="start" :disabled="t.running.value" :class="['w-full py-3 rounded-xl font-semibold text-white transition', t.running.value ? 'bg-slate-300' : 'bg-brand hover:bg-brand-dark']">{{ t.running.value ? '运行中…' : '🚀 开始放大' }}</button>
      </div>
    </div>
    <LogPanel compact :logs="t.logs.value" :pct="t.pct.value" :progress="t.progress.value" :total="t.total.value" :phase="t.phase.value" :running="t.running.value" @stop="t.stop" />
  </div>
</template>
