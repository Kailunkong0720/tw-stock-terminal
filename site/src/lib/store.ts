import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type RangeKey = '1M' | '3M' | '6M' | '1Y' | '3Y' | 'ALL'
export const RANGES: { key: RangeKey; label: string; days: number | null }[] = [
  { key: '1M', label: '1月', days: 21 },
  { key: '3M', label: '3月', days: 63 },
  { key: '6M', label: '6月', days: 126 },
  { key: '1Y', label: '1年', days: 252 },
  { key: '3Y', label: '3年', days: 756 },
  { key: 'ALL', label: '全部', days: null },
]

/** localStorage 在私密瀏覽或被封鎖時會丟例外；包一層讓網站照常運作。 */
const safeStorage = createJSONStorage(() => ({
  getItem: (k: string) => {
    try {
      return localStorage.getItem(k)
    } catch {
      return null
    }
  },
  setItem: (k: string, v: string) => {
    try {
      localStorage.setItem(k, v)
    } catch {
      // 忽略
    }
  },
  removeItem: (k: string) => {
    try {
      localStorage.removeItem(k)
    } catch {
      // 忽略
    }
  },
}))

type Prefs = {
  watchlist: string[]
  recent: string[]
  adjusted: boolean
  range: RangeKey
  subPane: 'volume' | 'foreign' | 'foreignCum'
  showCone: boolean
  setShowCone: (v: boolean) => void
  toggleWatch: (s: string) => void
  pushRecent: (s: string) => void
  setAdjusted: (v: boolean) => void
  setRange: (r: RangeKey) => void
  setSubPane: (p: Prefs['subPane']) => void
}

export const usePrefs = create<Prefs>()(
  persist(
    (set) => ({
      watchlist: ['2330', '0050', '2317', '2454'],
      recent: [],
      adjusted: true,
      range: '1Y',
      subPane: 'volume',
      showCone: true,
      setShowCone: (showCone) => set({ showCone }),
      toggleWatch: (s) =>
        set((st) => ({ watchlist: st.watchlist.includes(s) ? st.watchlist.filter((x) => x !== s) : [...st.watchlist, s] })),
      pushRecent: (s) => set((st) => ({ recent: [s, ...st.recent.filter((x) => x !== s)].slice(0, 8) })),
      setAdjusted: (adjusted) => set({ adjusted }),
      setRange: (range) => set({ range }),
      setSubPane: (subPane) => set({ subPane }),
    }),
    { name: 'twst.prefs', storage: safeStorage, version: 1 },
  ),
)

/** 不需要保存的畫面狀態：K 線可視區間、要聚焦的日期、搜尋視窗。 */
type View = {
  visible: { from: string; to: string } | null
  focusDate: string | null
  hoverDate: string | null
  searchOpen: boolean
  selectedMove: string | null
  selectMove: (d: string | null) => void
  setVisible: (v: View['visible']) => void
  focus: (d: string | null) => void
  setHover: (d: string | null) => void
  setSearchOpen: (o: boolean) => void
}

export const useView = create<View>()((set) => ({
  visible: null,
  focusDate: null,
  hoverDate: null,
  searchOpen: false,
  selectedMove: null,
  selectMove: (selectedMove) => set({ selectedMove }),
  setVisible: (visible) => set({ visible }),
  focus: (focusDate) => set({ focusDate }),
  setHover: (hoverDate) => set({ hoverDate }),
  setSearchOpen: (searchOpen) => set({ searchOpen }),
}))
