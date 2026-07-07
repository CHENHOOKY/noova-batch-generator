import { ref } from 'vue'
import { startTask, stopTask, openTaskWS } from '../api.js'

// 通用任务/WebSocket 组合式函数：所有插件共享
export function useTask() {
  const logs = ref([])
  const progress = ref(0)
  const total = ref(0)
  const pct = ref(0)
  const phase = ref('')
  const running = ref(false)
  const events = ref([])   // 结构化事件（prompts/outline/episode/page…）
  let ws = null
  let tid = null

  function start(endpoint, payload) {
    logs.value = []; progress.value = 0; total.value = 0; pct.value = 0; phase.value = ''
    events.value = []; running.value = true
    startTask(endpoint, payload)
      .then((d) => {
        tid = d.task_id
        ws = openTaskWS(tid)
        ws.onmessage = onMsg
        ws.onclose = () => { running.value = false }
      })
      .catch((e) => { logs.value.push('启动失败: ' + (e.message || e)); running.value = false })
  }
  function onMsg(e) {
    const ev = JSON.parse(e.data)
    if (ev.type === 'log') logs.value.push(ev.msg)
    else if (ev.type === 'progress') {
      if ('current' in ev) { progress.value = ev.current; total.value = ev.total; pct.value = total.value ? Math.round((ev.current / total.value) * 100) : 0 }
      else if ('pct' in ev) { pct.value = ev.pct }
      if (ev.phase) phase.value = ev.phase
      if (ev.label) phase.value = ev.label
    }
    else if (ev.type === 'done') { logs.value.push(ev.success ? '✅ 任务完成' : '❌ 任务结束'); running.value = false; if (ws) { ws.close(); ws = null } }
    else if (ev.type === 'error') { logs.value.push('错误: ' + ev.msg) }
    else events.value.push(ev)
  }
  function stop() { if (tid) { stopTask(tid); logs.value.push('已请求终止…') } }
  return { logs, progress, total, pct, phase, running, events, start, stop }
}
