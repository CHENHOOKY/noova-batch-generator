<script setup>
import { ref, onMounted, watch } from 'vue'
import { pickFolder, pickFile, getOptions } from '../api.js'
import { useTask } from '../composables/useTask.js'
import LogPanel from '../components/LogPanel.vue'
defineEmits(['back'])
const t = useTask()
const excel = ref(''); const out = ref('')
const models = ref([]); const cfg = ref({}); const model = ref(''); const ratio = ref(''); const size = ref('')
const poll = ref(20); const conc = ref(1)
onMounted(async () => { const o = await getOptions('batch_draw'); models.value = o.models; cfg.value = o.config; model.value = o.models[0]; onModel() })
function onModel() { const c = cfg.value[model.value] || {}; ratio.value = (c.ratios || [])[0] || ''; size.value = (c.sizes || [])[0] || '' }
watch(model, onModel)
const chExcel = async () => { const r = await pickFile('选择 Excel 文件', ['Excel (*.xlsx *.xls)']); if (r.path) excel.value = r.path }
const chOut = async () => { const r = await pickFolder('选择输出目录'); if (r.path) out.value = r.path }
const start = () => t.start('batch_draw', { excel_path: excel.value, output_dir: out.value, model: model.value, aspect_ratio: ratio.value, image_size: size.value, poll_interval: poll.value, concurrency: conc.value })
</script>
<template>
  <div class="p-8 max-w-5xl mx-auto space-y-5">
    <div><button @click="$emit('back')" class="text-slate-500 hover:text-brand text-sm transition">← 返回首页</button>
      <h1 class="text-2xl font-extrabold text-slate-800 mt-1">🎨 批量出图</h1>
      <p class="text-slate-500 text-sm mt-0.5">导入 Excel，自动解析提示词与参考图，批量 AI 出图</p></div>
    <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
      <h2 class="font-bold text-slate-800 mb-4 text-sm">参数设置</h2>
      <div class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">Excel 文件</label><div class="flex gap-2"><input v-model="excel" readonly placeholder="未选择" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="chExcel" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">输出目录</label><div class="flex gap-2"><input v-model="out" readonly placeholder="未选择" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="chOut" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div></div>
        </div>
        <div class="grid grid-cols-3 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">模型</label><select v-model="model" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="m in models" :key="m">{{ m }}</option></select></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">比例</label><select v-model="ratio" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="r in (cfg[model]?.ratios||[])" :key="r">{{ r }}</option></select></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">画质</label><select v-model="size" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="s in (cfg[model]?.sizes||[])" :key="s">{{ s }}</option></select></div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">轮询间隔（秒）</label><input v-model.number="poll" type="number" class="w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" /></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">并发数量</label><input v-model.number="conc" type="number" min="1" max="10" class="w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" /></div>
        </div>
        <button @click="start" :disabled="t.running.value" :class="['w-full py-3 rounded-xl font-semibold text-white transition', t.running.value ? 'bg-slate-300' : 'bg-brand hover:bg-brand-dark']">🚀 开始执行任务</button>
      </div>
    </div>
    <LogPanel compact :logs="t.logs.value" :pct="t.pct.value" :progress="t.progress.value" :total="t.total.value" :phase="t.phase.value" :running="t.running.value" @stop="t.stop" />
  </div>
</template>
