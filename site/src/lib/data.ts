import { useQuery } from '@tanstack/react-query'

import schema from './contract/schema.json'
import type { Meta } from './contract/types'

/** 網站預期的資料契約版本（由 pipeline 產生的 schema 決定，單一來源）。 */
export const CONTRACT_VERSION = (schema as { 'x-contract-version': number })['x-contract-version']

/** 資料根路徑。相對於頁面，所以在 GitHub Pages 的子路徑下也能運作。 */
export const DATA_ROOT = './data/'

export class DataError extends Error {
  constructor(
    readonly path: string,
    readonly kind: 'not-found' | 'http' | 'network' | 'parse',
    message: string,
  ) {
    super(message)
    this.name = 'DataError'
  }
}

export function dataUrl(path: string): URL {
  return new URL(path, new URL(DATA_ROOT, document.baseURI))
}

export async function loadData<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(dataUrl(path), init)
  } catch {
    throw new DataError(path, 'network', `無法連線取得 ${path}`)
  }
  if (res.status === 404) throw new DataError(path, 'not-found', `找不到資料檔 ${path}`)
  if (!res.ok) throw new DataError(path, 'http', `取得 ${path} 失敗（HTTP ${res.status}）`)
  try {
    return (await res.json()) as T
  } catch {
    throw new DataError(path, 'parse', `資料檔 ${path} 格式錯誤`)
  }
}

/** meta.json 每次都向伺服器確認，部署新資料後重新整理就會看到。 */
export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: () => loadData<Meta>('meta.json', { cache: 'no-cache' }),
    staleTime: Infinity,
    retry: 1,
  })
}
