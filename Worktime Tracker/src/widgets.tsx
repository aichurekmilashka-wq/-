import {useEffect, useState} from 'react'
import {createRoot} from 'react-dom/client'
import DraggableWidgetGrid, {type WidgetItem} from '@/components/ui/draggable-widget-grid'
import './index.css'

interface Summary {
  report: {total_seconds: number; page_seconds: number}
  running: number
  people: number
  order: string[]
  editable: boolean
}
declare global { interface Window { worktimeSummary?: Summary } }
const ITEMS: WidgetItem[] = [
  {id: 'total', size: 'wide', label: 'Общее время задач'},
  {id: 'browser', size: 'sm', label: 'На страницах'},
  {id: 'running', size: 'sm', label: 'Сейчас в работе'},
]
function duration(seconds: number) {
  const n = Math.max(0, Math.floor(seconds))
  return [Math.floor(n / 3600), Math.floor(n / 60) % 60, n % 60].map(v => String(v).padStart(2, '0')).join(':')
}
function Board() {
  const [summary, setSummary] = useState<Summary | undefined>(window.worktimeSummary)
  useEffect(() => {
    const update = (event: Event) => setSummary((event as CustomEvent<Summary>).detail)
    window.addEventListener('worktime:summary', update)
    return () => window.removeEventListener('worktime:summary', update)
  }, [])
  useEffect(() => {
    if (!summary) return
    const fallback = document.getElementById('summary-grid'), host = document.getElementById('react-widgets')
    if (fallback && host) { fallback.hidden = true; host.hidden = false }
  }, [summary])
  if (!summary) return null
  const items = summary.order.map(id => ITEMS.find(item => item.id === id)).filter((item): item is WidgetItem => Boolean(item))
  return <DraggableWidgetGrid items={items} editable={summary.editable} maxColumns={4} cellSize={235} gap={12} radius={24}
    onChange={order => localStorage.setItem('worktime-layout', JSON.stringify(order.map(item => item.id)))}
    renderItem={item => {
      const value = item.id === 'total' ? duration(summary.report.total_seconds) : item.id === 'browser' ? duration(summary.report.page_seconds) : `${summary.running} / ${summary.people}`
      const meta = item.id === 'total' ? 'Включает простой и время без наблюдения' : item.id === 'browser' ? 'Активная вкладка браузера' : 'Сотрудников с запущенной задачей'
      return <section className="widget-shell"><h2 className="widget-label">{item.label}</h2><p className="widget-value">{value}</p><p className="widget-meta">{meta}</p></section>
    }}/>
}
const host = document.getElementById('react-widgets')
if (host) {
  const stylesheet = document.createElement('link')
  stylesheet.rel = 'stylesheet'; stylesheet.href = '/widgets.css'; document.head.append(stylesheet)
  createRoot(host).render(<Board/>)
}
