<script setup>
import { ref, onMounted } from 'vue'
import { pickFolder, getOptions } from '../api.js'
import { useTask } from '../composables/useTask.js'
import LogPanel from '../components/LogPanel.vue'
defineEmits(['back'])
const t = useTask()
const opt = ref({ styles: [], durations: [], image_models: [] })
const f = ref({ story_text: '', style_label: '', episode_count: 4, duration: 15, ds_model: 'deepseek-v4-pro', image_model: 'nano-banana-pro', image_size: '1K', image_ratio: '16:9', run_images: true, project_dir: '' })
onMounted(async () => { opt.value = await getOptions('storyboard'); f.value.style_label = opt.value.styles[0] || '' })
const pickOut = async () => { const r = await pickFolder('选择项目目录'); if (r.path) f.value.project_dir = r.path }
const start = () => t.start('storyboard', { ...f.value })
</script>
<template>
  <div class="p-8 max-w-5xl mx-auto space-y-5">
    <div><button @click="$emit('back')" class="text-slate-500 hover:text-brand text-sm transition">← 返回首页</button>
      <h1 class="text-2xl font-extrabold text-slate-800 mt-1">🎬 分镜脚本生成器</h1>
      <p class="text-slate-500 text-sm mt-0.5">故事 → 四幕剧本 → 素材规划 → AI 出图 → 逐秒分镜</p></div>
    <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
      <h2 class="font-bold text-slate-800 mb-4 text-sm">参数设置</h2>
      <div class="space-y-4">
        <div><label class="block text-xs font-medium text-slate-500 mb-1">故事 / 主题</label><textarea v-model="f.story_text" rows="4" placeholder="输入故事内容或主题描述..." class="w-full px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-sm"></textarea></div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">视觉风格</label><select v-model="f.style_label" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="s in opt.styles" :key="s">{{ s }}</option></select></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">每集时长（秒）</label><select v-model.number="f.duration" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="d in opt.durations" :key="d" :value="Number(d)">{{ d }}</option></select></div>
        </div>
        <div class="grid grid-cols-3 gap-3">
          <div><label class="block text-xs font-medium text-slate-500 mb-1">集数</label><input v-model.number="f.episode_count" type="number" min="1" max="12" class="w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" /></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">出图模型</label><select v-model="f.image_model" class="w-full px-2 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm"><option v-for="m in opt.image_models" :key="m">{{ m }}</option></select></div>
          <div><label class="block text-xs font-medium text-slate-500 mb-1">比例</label><input v-model="f.image_ratio" class="w-full px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm" /></div>
        </div>
        <label class="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" v-model="f.run_images" /> 生成素材图片（第三阶段）</label>
        <div class="flex gap-2"><input v-model="f.project_dir" readonly placeholder="项目目录（可留空）" class="flex-1 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 text-sm truncate" /><button @click="pickOut" class="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-medium transition shrink-0">选择</button></div>
        <button @click="start" :disabled="t.running.value" :class="['w-full py-3 rounded-xl font-semibold text-white transition', t.running.value ? 'bg-slate-300' : 'bg-brand hover:bg-brand-dark']">🚀 生成分镜脚本</button>
      </div>
    </div>
    <LogPanel compact :logs="t.logs.value" :pct="t.pct.value" :progress="t.progress.value" :total="t.total.value" :phase="t.phase.value" :running="t.running.value" @stop="t.stop" />
  </div>
</template>
