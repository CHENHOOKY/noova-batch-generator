<script setup>
import { ref, onMounted } from 'vue'
import { pickFolder, getOptions } from '../api.js'
import { useTask } from '../composables/useTask.js'
import LogPanel from '../components/LogPanel.vue'
defineEmits(['back'])
const t = useTask()
const opt = ref({ styles: [], scenes: [], characters: [], themes: [], emotions: [], narratives: [], image_models: [] })
const f = ref({ style_key: 'watercolor', scene_key: 'meadow', age: 5, pages: 4, character_key: 'yueyue', emotion: '', theme: '', custom_topic: '', story_title: '', generate_images: true, image_model: 'nano-banana-pro', aspect_ratio: '1:1', image_size: '1K', output_formats: ['markdown'], output_dir: '', text_model: 'deepseek-v4-pro' })
onMounted(async () => { opt.value = await getOptions('picture_book') })
const pickOut = async () => { const r = await pickFolder('选择输出目录'); if (r.path) f.value.output_dir = r.path }
const toggleFmt = (m) => { const i = f.value.output_formats.indexOf(m); if (i >= 0) f.value.output_formats.splice(i, 1); else f.value.output_formats.push(m) }
const start = () => t.start('picture_book', { ...f.value })
</script>
<template>
  <div class="p-8 max-w-5xl mx-auto space-y-5">
    <div><button @click="$emit('back')" class="text-slate-500 hover:text-brand text-sm transition">← 返回首页</button>
      <h1 class="text-2xl font-extrabold text-slate-800 mt-1">📖 绘本魔法师</h1>
      <p class="text-slate-500 text-sm mt-0.5">AI 生成中英双语儿童绘本，含拼音、学习点与配图</p></div>
    <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
      <h2 class="font-bold text-slate-800 mb-4 text-sm">参数设置</h2>
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">视觉风格</label><select v-model="f.style_key" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="o in opt.styles" :key="o.key" :value="o.key">{{ o.label }}</option></select></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">场景</label><select v-model="f.scene_key" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="o in opt.scenes" :key="o.key" :value="o.key">{{ o.label }}</option></select></div>
        </div>
        <div class="grid grid-cols-3 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">角色</label><select v-model="f.character_key" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="o in opt.characters" :key="o.key" :value="o.key">{{ o.label }}</option></select></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">年龄</label><input v-model.number="f.age" type="number" min="3" max="12" class="w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" /></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">页数</label><input v-model.number="f.pages" type="number" min="1" max="15" class="w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" /></div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">主题</label><select v-model="f.theme" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option value="">（自动）</option><option v-for="o in opt.themes" :key="o.key" :value="o.key">{{ o.label }}</option></select></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">叙事</label><select v-model="f.narrative" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="o in opt.narratives" :key="o.key" :value="o.key">{{ o.label }}</option></select></div>
        </div>
        <input v-model="f.custom_topic" placeholder="自定义主题（可选，留空由 AI 发想）" class="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
        <input v-model="f.story_title" placeholder="故事标题（可选）" class="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
        <div class="grid grid-cols-3 gap-3">
          <select v-model="f.image_model" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="m in opt.image_models" :key="m">{{ m }}</option></select>
          <input v-model="f.aspect_ratio" placeholder="比例" class="px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" />
          <select v-model="f.image_size" class="px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option>1K</option><option>2K</option><option>4K</option></select>
        </div>
        <div class="flex flex-wrap items-center gap-4 text-sm text-slate-600">
          <label class="flex items-center gap-1"><input type="checkbox" v-model="f.generate_images" /> 生成配图</label>
          <span>导出：</span><label class="flex items-center gap-1"><input type="checkbox" checked disabled /> Markdown</label>
          <label class="flex items-center gap-1"><input type="checkbox" :checked="f.output_formats.includes('pptx')" @change="toggleFmt('pptx')" /> PPTX</label>
        </div>
        <div class="flex gap-2"><input v-model="f.output_dir" readonly placeholder="输出目录（可留空）" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="pickOut" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div>
        <button @click="start" :disabled="t.running.value" :class="['w-full py-3 rounded-xl font-semibold text-white transition', t.running.value ? 'bg-slate-300' : 'bg-brand hover:bg-brand-dark']">🚀 开始创作</button>
      </div>
    </div>
    <LogPanel compact :logs="t.logs.value" :pct="t.pct.value" :progress="t.progress.value" :total="t.total.value" :phase="t.phase.value" :running="t.running.value" @stop="t.stop" />
  </div>
</template>
