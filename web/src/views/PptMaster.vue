<script setup>
import { ref, onMounted } from 'vue'
import { pickFolder, getOptions } from '../api.js'
import { useTask } from '../composables/useTask.js'
import LogPanel from '../components/LogPanel.vue'
defineEmits(['back'])
const t = useTask()
const opt = ref({ design_schemes: [], industry_palettes: [], layout_templates: [], canvas: [], text_models: [] })
const f = ref({ prompt: '', page_count: 10, canvas_key: 'ppt169', design_scheme_key: 'general', industry_key: 'none', layout_key: 'none', custom_style: '', output_dir: '', model: 'deepseek-v4-pro' })
onMounted(async () => { opt.value = await getOptions('ppt_master') })
const pickOut = async () => { const r = await pickFolder('选择输出目录'); if (r.path) f.value.output_dir = r.path }
const start = () => t.start('ppt_master', { ...f.value })
</script>
<template>
  <div class="p-8 max-w-5xl mx-auto space-y-5">
    <div><button @click="$emit('back')" class="text-slate-500 hover:text-brand text-sm transition">← 返回首页</button>
      <h1 class="text-2xl font-extrabold text-slate-800 mt-1">📊 PPT 大师</h1>
      <p class="text-slate-500 text-sm mt-0.5">输入主题，AI 自动生成大纲和幻灯片，导出原生 PPTX</p></div>
    <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
      <h2 class="font-bold text-slate-800 mb-4 text-sm">参数设置</h2>
      <div class="space-y-4">
        <div><label class="block text-xs font-medium text-slate-500 mb-1">PPT 主题 / 提示词</label><textarea v-model="f.prompt" rows="3" placeholder="输入 PPT 主题或提示词..." class="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm"></textarea></div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">预计页数</label><input v-model.number="f.page_count" type="number" min="1" class="w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" /></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">画布尺寸</label><select v-model="f.canvas_key" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="o in opt.canvas" :key="o.key" :value="o.key">{{ o.label }}</option></select></div>
        </div>
        <div class="grid grid-cols-3 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">设计方案</label><select v-model="f.design_scheme_key" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-xs"><option v-for="o in opt.design_schemes" :key="o.key" :value="o.key">{{ o.label }}</option></select></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">行业配色</label><select v-model="f.industry_key" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-xs"><option v-for="o in opt.industry_palettes" :key="o.key" :value="o.key">{{ o.label }}</option></select></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">布局模板</label><select v-model="f.layout_key" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-xs"><option v-for="o in opt.layout_templates" :key="o.key" :value="o.key">{{ o.label }}</option></select></div>
        </div>
        <input v-model="f.custom_style" placeholder="自定义风格（可选）" class="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">文本模型</label><select v-model="f.model" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="m in opt.text_models" :key="m">{{ m }}</option></select></div>
          <div class="flex gap-2 items-end"><input v-model="f.output_dir" readonly placeholder="输出目录（可留空）" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="pickOut" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div>
        </div>
        <button @click="start" :disabled="t.running.value" :class="['w-full py-3 rounded-xl font-semibold text-white transition', t.running.value ? 'bg-slate-300' : 'bg-brand hover:bg-brand-dark']">🚀 生成 PPT</button>
      </div>
    </div>
    <LogPanel compact :logs="t.logs.value" :pct="t.pct.value" :progress="t.progress.value" :total="t.total.value" :phase="t.phase.value" :running="t.running.value" @stop="t.stop" />
  </div>
</template>
