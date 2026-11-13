import { useQuery } from '@tanstack/react-query'

import schema from './contract/schema.json'
import type {
  Backtest,
  Bars,
  Calendar,
  Events,
  Flows,
  Forecast,
  GlobeOvernight,
  GlobeSupply,
  GraphEgo,
  GraphPropagate,
  Heatmap,
  IndustryFlows,
  MarketFlows,
  Meta,
  Moves,
  Overview,
  Ranking,
  Securities,
  Timeline,
} from './contract/types'

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

/** 以 meta 的產生時間當版本，換資料後瀏覽器快取不會拿到舊檔。 */
function useVersion(): string | undefined {
  return useMeta().data?.generated_at
}

function useDataFile<T>(path: string | null, key: unknown[]) {
  const v = useVersion()
  return useQuery({
    queryKey: [...key, v],
    queryFn: () => loadData<T>(`${path}?v=${encodeURIComponent(v ?? '')}`),
    enabled: Boolean(path && v),
    staleTime: Infinity,
    retry: (n, err) => !(err instanceof DataError && err.kind === 'not-found') && n < 1,
  })
}

export const useCalendar = () => useDataFile<Calendar>('calendar.json', ['calendar'])
export const useSecurities = () => useDataFile<Securities>('securities.json', ['securities'])
export const useOverview = () => useDataFile<Overview>('market/overview.json', ['overview'])
export const useHeatmap = () => useDataFile<Heatmap>('market/heatmap.json', ['heatmap'])
export const useIndustryFlows = () => useDataFile<IndustryFlows>('flows/industry.json', ['industry-flows'])
export const useMarketFlows = () => useDataFile<MarketFlows>('flows/market.json', ['market-flows'])
export const useBars = (symbol: string) => useDataFile<Bars>(`bars/${symbol}.json`, ['bars', symbol])
export const useFlows = (symbol: string) => useDataFile<Flows>(`flows/${symbol}.json`, ['flows', symbol])
export const useRanking = () => useDataFile<Ranking>('forecast/ranking.json', ['ranking'])
/** 非追蹤池的股票沒有預測檔（404），呼叫端以 tracked 決定是否啟用。 */
export const useForecast = (symbol: string, enabled = true) =>
  useDataFile<Forecast>(enabled ? `forecast/${symbol}.json` : null, ['forecast', symbol])
export const useBacktest = (symbol: string, enabled = true) =>
  useDataFile<Backtest>(enabled ? `forecast/backtest/${symbol}.json` : null, ['backtest', symbol])
/** 沒有異常波動日的股票沒有這個檔（404 不重試）。 */
export const useMoves = (symbol: string) => useDataFile<Moves>(`moves/${symbol}.json`, ['moves', symbol])
export const useEvents = (symbol: string, enabled = true) =>
  useDataFile<Events>(enabled ? `events/${symbol}.json` : null, ['events', symbol])
export const useTimeline = () => useDataFile<Timeline>('events/timeline.json', ['timeline'])
export const useEgo = (symbol: string) => useDataFile<GraphEgo>(`graph/ego/${symbol}.json`, ['ego', symbol])
export const useGlobeOvernight = () => useDataFile<GlobeOvernight>('globe/overnight.json', ['globe-overnight'])
export const useGlobeSupply = () => useDataFile<GlobeSupply>('globe/supply.json', ['globe-supply'])
export const usePropagate = (nodeId: string | null) =>
  useDataFile<GraphPropagate>(nodeId ? `graph/propagate/${nodeId.replace(':', '_')}.json` : null, ['propagate', nodeId])
