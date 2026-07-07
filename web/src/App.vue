<script setup>
import { ref, onMounted, computed } from 'vue'
import { getPlugins } from './api.js'
import Home from './views/Home.vue'
import Settings from './views/Settings.vue'
import BatchDraw from './views/BatchDraw.vue'
import FolderBatchDraw from './views/FolderBatchDraw.vue'
import Upscale from './views/Upscale.vue'
import Ecommerce from './views/Ecommerce.vue'
import Storyboard from './views/Storyboard.vue'
import PictureBook from './views/PictureBook.vue'
import PptMaster from './views/PptMaster.vue'
import UserManual from './views/UserManual.vue'

const MAP = { home: Home, settings: Settings, batch_draw: BatchDraw, folder_batch_draw: FolderBatchDraw,
  upscale: Upscale, ecommerce: Ecommerce, storyboard: Storyboard, picture_book: PictureBook,
  ppt_master: PptMaster, user_manual: UserManual }
const plugins = ref([])
const view = ref('home')
onMounted(async () => { plugins.value = await getPlugins() })
const go = (v) => (view.value = v)
const cur = computed(() => MAP[view.value] || Home)
const navCls = (name) => ['w-full text-left px-4 py-2.5 rounded-xl text-sm transition',
  view.value === name ? 'bg-white/20 font-semibold' : 'text-white/80 hover:bg-white/10'].join(' ')
</script>

<template>
  <div class="flex h-full">
    <aside class="w-60 shrink-0 flex flex-col text-white overflow-auto"
           style="background:linear-gradient(180deg,#4338ca 0%,#6d28d9 55%,#0ea5e9 100%)">
      <div class="px-6 pt-7 pb-6">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-xl bg-white/20 flex items-center justify-center text-lg font-black">N</div>
          <div><div class="font-extrabold text-lg leading-tight">Noova AI</div><div class="text-[11px] text-white/70">AI 创意套件</div></div>
        </div>
      </div>
      <nav class="px-3 space-y-1">
        <button @click="go('home')" :class="navCls('home')">🏠&nbsp;&nbsp;应用首页</button>
        <button v-for="p in plugins" :key="p.id" @click="go(p.id)" :class="navCls(p.id)">{{ p.icon }}&nbsp;&nbsp;{{ p.name }}</button>
        <button @click="go('settings')" :class="navCls('settings')">⚙&nbsp;&nbsp;设置</button>
      </nav>
      <div class="mt-auto px-6 py-5 text-[11px] text-white/60">Noova · v3.0 Web</div>
    </aside>
    <main class="flex-1 overflow-auto bg-slate-50">
      <transition name="fade" mode="out-in">
        <component :is="cur" @open="go" @back="go('home')" :key="view" />
      </transition>
    </main>
  </div>
</template>
