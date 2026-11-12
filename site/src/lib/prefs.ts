import { useSyncExternalStore } from 'react'

/** 漲跌配色：台灣慣例紅漲綠跌（預設），或綠漲紅跌。 */
export type UpDown = 'red-up' | 'green-up'

const KEY = 'twst.updown'
const listeners = new Set<() => void>()

function read(): UpDown {
  try {
    return localStorage.getItem(KEY) === 'green-up' ? 'green-up' : 'red-up'
  } catch {
    return 'red-up'
  }
}

let current: UpDown = read()

function apply(v: UpDown) {
  document.documentElement.dataset.updown = v
}

export function initPrefs() {
  apply(current)
}

export function setUpDown(v: UpDown) {
  current = v
  try {
    localStorage.setItem(KEY, v)
  } catch {
    // 私密瀏覽等情況無法儲存，仍套用到本次瀏覽
  }
  apply(v)
  for (const l of listeners) l()
}

export function useUpDown(): UpDown {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => current,
  )
}
