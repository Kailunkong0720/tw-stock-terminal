/**
 * 台股格式化規則（PLAN.md 7.3）。所有數字顯示都經過這裡。
 */

const nf = (d: number) =>
  new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: true })
const NF = [nf(0), nf(1), nf(2), nf(3)]

/** 2026-11-11 → 2026-11-11（週三） */
export function formatDate(iso: string | null | undefined, withWeekday = false): string {
  if (!iso) return '—'
  const base = iso.slice(0, 10)
  if (!withWeekday) return base
  const d = new Date(`${base}T00:00:00+08:00`)
  if (Number.isNaN(d.getTime())) return base
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

/**
 * 價格的小數位數，依台股升降單位：
 * 未滿 10 元 0.01、10–50 元 0.05、50–100 元 0.1、100–500 元 0.5、500–1000 元 1、1000 元以上 5。
 * ETF 一律兩位。還原價不是實際成交價，也用兩位（1000 元以上用一位）。
 */
export function priceDecimals(p: number, opts: { etf?: boolean; adjusted?: boolean } = {}): number {
  const a = Math.abs(p)
  if (opts.etf || opts.adjusted) return a >= 1000 ? 1 : 2
  if (a < 50) return 2
  if (a < 500) return 1
  return 0
}

export function formatPrice(p: number | null | undefined, opts: { etf?: boolean; adjusted?: boolean } = {}): string {
  if (p == null || !Number.isFinite(p)) return '—'
  return NF[priceDecimals(p, opts)]!.format(p)
}

/** 0.0123 → +1.23% */
export function formatPct(r: number | null | undefined, digits = 2, fromRatio = true): string {
  if (r == null || !Number.isFinite(r)) return '—'
  const v = fromRatio ? r * 100 : r
  const s = NF[Math.min(digits, 3)]!.format(Math.abs(v))
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${s}%`
}

export function formatSigned(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const s = NF[Math.min(digits, 3)]!.format(Math.abs(v))
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${s}`
}

export function formatInt(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return NF[0]!.format(v)
}

/** 張數：125,312 張 → 12.53 萬 */
export function formatLots(v: number | null | undefined, signed = false): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const a = Math.abs(v)
  const sign = signed ? (v > 0 ? '+' : v < 0 ? '−' : '') : v < 0 ? '−' : ''
  if (a >= 1e8) return `${sign}${NF[2]!.format(a / 1e8)} 億`
  if (a >= 1e5) return `${sign}${NF[2]!.format(a / 1e4)} 萬`
  return `${sign}${NF[0]!.format(a)}`
}

/** 億元：1234.5 → 1,234.5 億；也可傳入百萬元（unit='M'）。 */
export function formatYi(v: number | null | undefined, unit: 'yi' | 'M' = 'yi', signed = true): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const yi = unit === 'M' ? v / 100 : v
  const a = Math.abs(yi)
  const sign = signed ? (yi > 0 ? '+' : yi < 0 ? '−' : '') : yi < 0 ? '−' : ''
  if (a >= 1) return `${sign}${NF[a >= 100 ? 0 : a >= 10 ? 1 : 2]!.format(a)} 億`
  return `${sign}${NF[0]!.format(a * 1e4)} 萬`
}

/** 千元 → 億元 */
export function kToYi(v: number): number {
  return v / 1e5
}

/** 漲跌顏色的 class（紅漲綠跌由 CSS token 決定） */
export function toneClass(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v) || v === 0) return 'text-flat'
  return v > 0 ? 'text-up' : 'text-down'
}
