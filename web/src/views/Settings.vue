<script setup>
import { ref, onMounted } from 'vue'
import { getSettings, saveSettings } from '../api.js'
const emit = defineEmits(['back'])
const visualKey = ref(''); const textKey = ref('')
const hasVisual = ref(false); const hasText = ref(false); const saved = ref(false)
onMounted(async () => { const s = await getSettings(); visualKey.value = s.visual_key; textKey.value = s.text_key; hasVisual.value = s.has_visual; hasText.value = s.has_text })
const save = async () => { await saveSettings({ visual_key: visualKey.value, text_key: textKey.value }); hasVisual.value = !!visualKey.value; hasText.value = !!textKey.value; saved.value = true; setTimeout(() => (saved.value = false), 2000) }
</script>

<template>
  <div class="p-8 max-w-3xl mx-auto">
    <button @click="emit('back')" class="text-slate-500 hover:text-brand text-sm mb-4 transition">← 返回首页</button>
    <h1 class="text-3xl font-extrabold text-slate-800">⚙ 设置</h1>
    <p class="text-slate-500 mt-1">配置 API Key，仅保存在本机 ~/.noova/settings.json</p>
    <div class="bg-white rounded-2xl border border-slate-200 p-7 shadow-sm mt-8">
      <h2 class="font-bold text-slate-800">视觉模型 API（出图）</h2>
      <p class="text-xs text-slate-400 mt-1">https://noova.cn · Key 以 sk- 开头</p>
      <input v-model="visualKey" type="password" placeholder="输入 Noova API Key（sk-...）" class="mt-3 w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
      <div class="mt-2 text-xs" :class="hasVisual ? 'text-emerald-600' : 'text-amber-600'">{{ hasVisual ? '✅ 已配置' : '⚠ 未配置' }}</div>
    </div>
    <div class="bg-white rounded-2xl border border-slate-200 p-7 shadow-sm mt-5">
      <h2 class="font-bold text-slate-800">文本模型 API（文案 / PPT / 绘本）</h2>
      <p class="text-xs text-slate-400 mt-1">OpenAI 兼容服务 · Key 以 sk- 开头</p>
      <input v-model="textKey" type="password" placeholder="输入文本 API Key（sk-...）" class="mt-3 w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
      <div class="mt-2 text-xs" :class="hasText ? 'text-emerald-600' : 'text-amber-600'">{{ hasText ? '✅ 已配置' : '⚠ 未配置' }}</div>
    </div>
    <div class="mt-6 flex items-center gap-4">
      <button @click="save" class="px-6 py-2.5 rounded-xl bg-brand hover:bg-brand-dark text-white font-semibold transition">保存设置</button>
      <span v-if="saved" class="text-emerald-600 text-sm">✅ 已保存</span>
    </div>
  </div>
</template>
