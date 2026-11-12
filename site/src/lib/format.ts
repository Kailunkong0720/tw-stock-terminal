/**
 * 台股格式化規則（PLAN.md 7.3）。所有數字顯示都經過這裡。
 * Phase 1 之後補上：價格升降單位、張數、億／萬。
 */

/** 2026-11-11 → 2026-11-11（週三） */
export function formatDate(iso: string | null | undefined, withWeekday = false): string {
  if (!iso) return '—'
  const d = new Date(`${iso.slice(0, 10)}T00:00:00+08:00`)
  if (Number.isNaN(d.getTime())) return iso
  const base = iso.slice(0, 10)
  if (!withWeekday) return base
  const wd = new Intl.DateTimeFormat('zh-TW', { weekday: 'short', timeZone: 'Asia/Taipei' }).format(d)
  return `${base}（${wd}）`
}

/** ISO 時間 → 2026-11-12 16:31（台北時間） */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(d)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`
}
