<script setup>
import { ref, onMounted, watch } from 'vue'
import { pickFolder, pickFile, getOptions } from '../api.js'
import { useTask } from '../composables/useTask.js'
import LogPanel from '../components/LogPanel.vue'
defineEmits(['back'])
const t = useTask()
const out = ref(''); const defaultInput = ref(''); const outMode = ref('prompt')
const models = ref([]); const cfg = ref({}); const model = ref(''); const ratio = ref(''); const size = ref('')
const poll = ref(20); const conc = ref(1)
const groups = ref([])
const bulk = ref('')
onMounted(async () => { const o = await getOptions('folder_batch_draw'); models.value = o.models; cfg.value = o.config; model.value = o.models[0]; onModel() })
function onModel() { const c = cfg.value[model.value] || {}; ratio.value = (c.ratios || [])[0] || ''; size.value = (c.sizes || [])[0] || '' }
watch(model, onModel)
const newGroup = (prompt = '') => ({ prompt, folder: '', fixed1: '', fixed2: '', output_dir: '' })
const addBulk = () => { bulk.value.split('\n').map(x => x.trim()).filter(Boolean).forEach(l => groups.value.push(newGroup(l))); bulk.value = '' }
const rmGroup = (i) => groups.value.splice(i, 1)
const clearAll = () => { groups.value = [] }
const applyDefaultToAll = () => { if (!defaultInput.value) return; groups.value.forEach(g => { if (!g.folder) g.folder = defaultInput.value }) }
const pickOut = async () => { const r = await pickFolder('选择全局输出目录'); if (r.path) out.value = r.path }
const pickDefault = async () => { const r = await pickFolder('选择默认参考图文件夹'); if (r.path) defaultInput.value = r.path }
const pickFld = async (g) => { const r = await pickFolder('选择参考图文件夹'); if (r.path) g.folder = r.path }
const pickFx = async (g, n) => { const r = await pickFile(`选择${n}`, ['图片 (*.png *.jpg *.jpeg *.webp *.bmp)']); if (r.path) g[n] = r.path }
const pickOutG = async (g) => { const r = await pickFolder('选择该组单独输出目录'); if (r.path) g.output_dir = r.path }
const base = (p) => { try { return p.split(/[\\/]/).pop() } catch (e) { return p } }
const fldLabel = (g) => g.folder ? base(g.folder) : (defaultInput.value ? '默认' : '未选')
const fldOk = (g) => !!(g.folder || defaultInput.value)
const start = () => t.start('folder_batch_draw', { output_dir: out.value, default_input_dir: defaultInput.value, groups: groups.value, model: model.value, aspect_ratio: ratio.value, image_size: size.value, poll_interval: poll.value, concurrency: conc.value, output_mode: outMode.value })
</script>

<template>
  <div class="p-8 max-w-6xl mx-auto space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <button @click="$emit('back')" class="text-slate-500 hover:text-brand text-sm transition">← 返回首页</button>
        <h1 class="text-2xl font-extrabold text-slate-800 mt-1">📁 文件夹批量出图</h1>
      </div>
    </div>

    <!-- 全局设置（紧凑两列）-->
    <div class="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
      <h2 class="font-bold text-slate-800 mb-3 text-sm">全局设置</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div class="flex gap-2"><input v-model="out" readonly placeholder="全局输出目录" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="pickOut" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div>
        <div class="flex gap-2"><input v-model="defaultInput" readonly placeholder="默认参考图文件夹（公共来源）" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="pickDefault" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-2 mt-3">
        <select v-model="model" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="m in models" :key="m">{{ m }}</option></select>
        <select v-model="ratio" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="r in (cfg[model]?.ratios||[])" :key="r">{{ r }}</option></select>
        <select v-model="size" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="s in (cfg[model]?.sizes||[])" :key="s">{{ s }}</option></select>
        <select v-model="outMode" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option value="prompt">按提示词命名</option><option value="numbered">按时间+序号</option><option value="flat">不建子文件夹</option></select>
        <div class="grid grid-cols-2 gap-2">
          <input v-model.number="poll" type="number" placeholder="轮询秒" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
          <input v-model.number="conc" type="number" min="1" max="10" placeholder="并发" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
        </div>
      </div>
    </div>

    <!-- 批量提示词 + 任务组：左右分栏，提示词区占大头 -->
    <div class="grid grid-cols-1 lg:grid-cols-5 gap-5">
      <!-- 左：批量输入（2/5）-->
      <div class="lg:col-span-2 space-y-5">
        <div class="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
          <h2 class="font-bold text-slate-800 mb-1 text-sm">批量添加提示词</h2>
          <p class="text-xs text-slate-400 mb-3">每行一个提示词，一次性创建多组</p>
          <textarea v-model="bulk" rows="10" placeholder="一只在草地上奔跑的橘猫&#10;水彩风格的山间小屋&#10;未来城市夜景..." class="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm resize-none"></textarea>
          <button @click="addBulk" :disabled="!bulk.trim()" :class="['w-full mt-3 py-2.5 rounded-xl text-sm font-semibold transition', bulk.trim() ? 'bg-brand-soft text-brand hover:bg-brand hover:text-white' : 'bg-slate-100 text-slate-300 cursor-not-allowed']">➕ 添加为任务组</button>
          <button @click="groups.push(newGroup())" class="w-full mt-2 py-2 rounded-xl border border-dashed border-slate-300 text-slate-400 hover:border-brand hover:text-brand text-sm transition">+ 单独添加一组</button>
        </div>
      </div>

      <!-- 右：任务组列表（3/5，给提示词更多空间）-->
      <div class="lg:col-span-3">
        <div class="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm h-full flex flex-col">
          <div class="flex items-center justify-between mb-3">
            <h2 class="font-bold text-slate-800 text-sm">任务组 <span class="text-slate-400 font-normal">（{{ groups.length }} 组）</span></h2>
            <div class="flex gap-2">
              <button @click="applyDefaultToAll" :disabled="!defaultInput || !groups.length" class="text-xs px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 transition disabled:opacity-40">全部用默认文件夹</button>
              <button @click="clearAll" :disabled="!groups.length" class="text-xs px-2.5 py-1 rounded-lg text-red-500 hover:bg-red-50 transition disabled:opacity-40">清空</button>
            </div>
          </div>
          <div v-if="!groups.length" class="flex-1 flex items-center justify-center text-slate-300 text-sm py-10">还没有任务组，在左侧批量添加提示词</div>
          <div v-else class="flex-1 space-y-2 overflow-auto pr-1" style="max-height: 380px">
            <div v-for="(g, i) in groups" :key="i" class="rounded-xl border border-slate-200 bg-slate-50/60 p-2.5">
              <div class="flex items-center gap-2">
                <span class="w-6 h-6 shrink-0 rounded-full bg-brand text-white text-xs font-bold flex items-center justify-center">{{ i + 1 }}</span>
                <input v-model="g.prompt" class="flex-1 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-sm" />
                <button @click="rmGroup(i)" class="text-slate-300 hover:text-red-500 transition shrink-0 px-1" title="删除">✕</button>
              </div>
              <div class="flex flex-wrap items-center gap-1.5 mt-2 ml-8">
                <button @click="pickFld(g)" :class="['text-xs px-2.5 py-1 rounded-full border transition', fldOk(g) ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-amber-50 border-amber-200 text-amber-700']" :title="g.folder || (defaultInput || '未选')">📁 {{ fldLabel(g) }}</button>
                <button @click="pickFx(g,'fixed1')" :class="['text-xs px-2.5 py-1 rounded-full border transition', g.fixed1 ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-slate-50 border-slate-200 text-slate-400']">📌1 {{ g.fixed1 ? base(g.fixed1) : '可选' }}</button>
                <button @click="pickFx(g,'fixed2')" :class="['text-xs px-2.5 py-1 rounded-full border transition', g.fixed2 ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-slate-50 border-slate-200 text-slate-400']">📌2 {{ g.fixed2 ? base(g.fixed2) : '可选' }}</button>
                <button @click="pickOutG(g)" :class="['text-xs px-2.5 py-1 rounded-full border transition', g.output_dir ? 'bg-violet-50 border-violet-200 text-violet-700' : 'bg-slate-50 border-slate-200 text-slate-400']">📂 {{ g.output_dir ? base(g.output_dir) : '默认输出' }}</button>
              </div>
            </div>
          </div>
          <button @click="start" :disabled="t.running.value || !groups.length" :class="['w-full py-3 mt-3 rounded-xl font-semibold text-white transition', (t.running.value || !groups.length) ? 'bg-slate-300' : 'bg-brand hover:bg-brand-dark']">🚀 开始执行任务</button>
        </div>
      </div>
    </div>

    <!-- 运行监控：底部紧凑条 -->
    <LogPanel compact :logs="t.logs.value" :pct="t.pct.value" :progress="t.progress.value" :total="t.total.value" :phase="t.phase.value" :running="t.running.value" @stop="t.stop" />
  </div>
</template>
