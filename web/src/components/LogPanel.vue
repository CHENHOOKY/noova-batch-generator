<script setup>
defineProps({
  logs: { type: Array, default: () => [] }, pct: { type: Number, default: 0 },
  progress: { type: Number, default: 0 }, total: { type: Number, default: 0 },
  phase: { type: String, default: '' }, running: { type: Boolean, default: false },
  compact: { type: Boolean, default: false }
})
defineEmits(['stop'])
</script>
<template>
  <div :class="['bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col', compact ? 'p-5' : 'p-7']">
    <div class="flex items-center justify-between mb-3">
      <h2 class="font-bold text-slate-800">运行监控</h2>
      <span class="text-xs text-slate-400">{{ phase || (total ? `${progress}/${total}` : '—') }}</span>
    </div>
    <div class="flex items-center gap-3 mb-3">
      <div class="flex-1 h-2 rounded-full bg-slate-100 overflow-hidden">
        <div class="h-full rounded-full transition-all duration-300" :style="{ width: pct + '%', background: 'linear-gradient(90deg,#6366F1,#0ea5e9)' }"></div>
      </div>
      <span class="text-xs font-semibold text-slate-500 w-10 text-right">{{ pct }}%</span>
      <button v-if="running" @click="$emit('stop')" class="px-3 py-1.5 rounded-lg bg-red-500 hover:bg-red-600 text-white text-xs font-semibold transition">⏹ 终止</button>
    </div>
    <div :class="['flex-1 overflow-auto rounded-xl bg-slate-900 text-slate-100 text-xs font-mono p-4 space-y-1', compact ? 'h-44' : 'h-72']">
      <div v-if="!logs.length" class="text-slate-500">运行后日志将在此实时显示…</div>
      <div v-for="(l, i) in logs" :key="i" :class="(String(l).includes('FAIL')||String(l).includes('错误')||String(l).includes('❌')) ? 'text-red-400' : (String(l).includes('OK')||String(l).includes('✅')) ? 'text-emerald-400' : 'text-slate-300'">{{ l }}</div>
    </div>
  </div>
</template>
