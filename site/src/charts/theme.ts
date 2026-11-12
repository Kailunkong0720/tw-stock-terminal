/** 從 CSS token 讀出圖表要用的顏色（圖表函式庫畫在 canvas 上，不能直接用 CSS 變數）。 */
export type ChartTheme = {
  panel: string
  raised: string
  line: string
  lineStrong: string
  text1: string
  text2: string
  text3: string
  up: string
  down: string
  flat: string
  accent: string
  warn: string
  s1: string
  s2: string
  s3: string
}

export function readTheme(): ChartTheme {
  const cs = getComputedStyle(document.documentElement)
  const v = (name: string) => cs.getPropertyValue(name).trim()
  return {
    panel: v('--bg-panel'),
    raised: v('--bg-raised'),
    line: v('--line'),
    lineStrong: v('--line-strong'),
    text1: v('--text-1'),
    text2: v('--text-2'),
    text3: v('--text-3'),
    up: v('--up'),
    down: v('--down'),
    flat: v('--flat'),
    accent: v('--accent'),
    warn: v('--warn'),
    s1: v('--series-1'),
    s2: v('--series-2'),
    s3: v('--series-3'),
  }
}

/** #rrggbb + 透明度 → rgba() */
export function alpha(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.replace(/(.)/g, '$1$1') : h, 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}
