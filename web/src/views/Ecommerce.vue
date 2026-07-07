<script setup>
import { ref, onMounted } from 'vue'
import { pickFolder, pickFiles, getOptions } from '../api.js'
import { useTask } from '../composables/useTask.js'
import LogPanel from '../components/LogPanel.vue'
defineEmits(['back'])
const t = useTask()
const opt = ref({ categories: [], platforms: [], task_types: [], image_models: [] })
const f = ref({ product_name: '', category: '', material: '', color_desc: '', brand_marks: '', platform: '', task_type: '', style_direction: '', is_redesign: false, image_count: 3, aspect_ratio: '1:1', image_size: '1K', image_model: 'nano-banana-pro', ds_model: 'deepseek-v4-pro', output_dir: '' })
const productImgs = ref([]); const refImgs = ref([])
onMounted(async () => { opt.value = await getOptions('ecommerce'); f.value.category = opt.value.categories[0]; f.value.platform = opt.value.platforms[0]; f.value.task_type = opt.value.task_types[0] })
const pickProduct = async () => { const r = await pickFiles('选择产品图（最多3张）', ['图片 (*.png *.jpg *.jpeg *.webp)']); productImgs.value = r.paths || [] }
const pickRef = async () => { const r = await pickFiles('选择参考图（最多5张）', ['图片 (*.png *.jpg *.jpeg *.webp)']); refImgs.value = r.paths || [] }
const pickOut = async () => { const r = await pickFolder('选择输出目录'); if (r.path) f.value.output_dir = r.path }
const start = () => t.start('ecommerce', { ...f.value, product_image_paths: productImgs.value, ref_image_paths: refImgs.value })
</script>
<template>
  <div class="p-8 max-w-5xl mx-auto space-y-5">
    <div><button @click="$emit('back')" class="text-slate-500 hover:text-brand text-sm transition">← 返回首页</button>
      <h1 class="text-2xl font-extrabold text-slate-800 mt-1">🛒 电商图</h1>
      <p class="text-slate-500 text-sm mt-0.5">输入产品信息，AI 推理视觉 DNA 并生成 N 套差异化方案图</p></div>
    <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
      <h2 class="font-bold text-slate-800 mb-4 text-sm">参数设置</h2>
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <button @click="pickProduct" class="px-3 py-2.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm font-medium transition">📷 产品图 <span class="text-slate-400">({{ productImgs.length }} 张)</span></button>
          <button @click="pickRef" class="px-3 py-2.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm font-medium transition">🎨 参考图 <span class="text-slate-400">({{ refImgs.length }} 张)</span></button>
        </div>
        <input v-model="f.product_name" placeholder="产品名称（如：氨基酸洁面慕斯）" class="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
        <div class="grid grid-cols-2 gap-3">
          <select v-model="f.category" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="c in opt.categories" :key="c">{{ c }}</option></select>
          <select v-model="f.platform" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="c in opt.platforms" :key="c">{{ c }}</option></select>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <input v-model="f.material" placeholder="材质描述" class="px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
          <input v-model="f.color_desc" placeholder="颜色描述" class="px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
        </div>
        <input v-model="f.brand_marks" placeholder="品牌标识 / Logo" class="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
        <div class="grid grid-cols-2 gap-3">
          <select v-model="f.task_type" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="c in opt.task_types" :key="c">{{ c }}</option></select>
          <input v-model="f.style_direction" placeholder="风格方向（可选）" class="px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
        </div>
        <div class="grid grid-cols-4 gap-2">
          <select v-model="f.image_model" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-xs"><option v-for="m in opt.image_models" :key="m">{{ m }}</option></select>
          <input v-model="f.aspect_ratio" placeholder="比例" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-xs" />
          <select v-model="f.image_size" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-xs"><option>1K</option><option>2K</option><option>4K</option></select>
          <input v-model.number="f.image_count" type="number" min="1" max="10" placeholder="张数" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-xs" />
        </div>
        <label class="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" v-model="f.is_redesign" /> 改版意图（在原图基础上优化升级）</label>
        <div class="flex gap-2"><input v-model="f.output_dir" readonly placeholder="输出目录（可留空，默认 ~/NoovaProjects/ecommerce）" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="pickOut" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div>
        <button @click="start" :disabled="t.running.value" :class="['w-full py-3 rounded-xl font-semibold text-white transition', t.running.value ? 'bg-slate-300' : 'bg-brand hover:bg-brand-dark']">🚀 开始生成</button>
      </div>
    </div>
    <LogPanel compact :logs="t.logs.value" :pct="t.pct.value" :progress="t.progress.value" :total="t.total.value" :phase="t.phase.value" :running="t.running.value" @stop="t.stop" />
  </div>
</template>
