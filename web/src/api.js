// 前端 API 封装 —— 与 FastAPI 后端通信
const json = async (url, opts) => {
  const r = await fetch(url, opts)
  if (!r.ok) { let d = '请求失败'; try { d = (await r.json()).detail || d } catch (e) {} throw new Error(d) }
  return r.json()
}
export const getPlugins = () => json('/api/plugins')
export const getSettings = () => json('/api/settings')
export const saveSettings = (p) => json('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) })
export const pickFolder = (title) => json('/api/dialog/folder', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) })
export const pickFile = (title, filetypes = []) => json('/api/dialog/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, filetypes }) })
export const pickFiles = (title, filetypes = []) => json('/api/dialog/open-multi', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, filetypes }) })
export const startTask = (endpoint, payload) => json('/api/tasks/' + endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
export const stopTask = (tid) => json(`/api/tasks/${tid}/stop`, { method: 'POST' })
export const getOptions = (name) => json('/api/options/' + name)
export const getManualPages = () => json('/api/manual/pages')
export const getManualPage = (pid) => json('/api/manual/' + pid)
export function openTaskWS(tid) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${location.host}/ws/tasks/${tid}`)
}
export function tint(hex, a = 0.85) {
  const h = String(hex).replace('#', '')
  if (h.length !== 6) return hex
  const n = (s) => parseInt(s, 16)
  const mix = (c) => Math.round(c + (255 - c) * a)
  return `rgb(${mix(n(h.slice(0, 2)))},${mix(n(h.slice(2, 4)))},${mix(n(h.slice(4, 6)))})`
}
