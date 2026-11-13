import {
  createHashHistory,
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
  Link,
} from '@tanstack/react-router'

import { AppShell } from './app/AppShell'

function NotFound() {
  return (
    <div className="p-6 text-sm text-text-2">
      找不到這個頁面。
      <Link to="/" className="ml-2 text-accent hover:underline">
        回到市場總覽
      </Link>
    </div>
  )
}

// 每個頁面各自打包、用到才下載（圖譜的力導向函式庫、熱力圖的版面計算等不必在首頁就載入）
const Market = lazyRouteComponent(() => import('./features/market/MarketPage'), 'MarketPage')
const Stock = lazyRouteComponent(() => import('./features/stock/StockPage'), 'StockPage')
const Flows = lazyRouteComponent(() => import('./features/flows/FlowsPage'), 'FlowsPage')
const Forecast = lazyRouteComponent(() => import('./features/forecast/ForecastPage'), 'ForecastPage')
const ExplainIndex = lazyRouteComponent(() => import('./features/explain/ExplainPages'), 'ExplainIndexPage')
const ExplainDetail = lazyRouteComponent(() => import('./features/explain/ExplainPages'), 'ExplainDetailPage')
const Graph = lazyRouteComponent(() => import('./features/graph/GraphPage'), 'GraphPage')
const Financials = lazyRouteComponent(() => import('./features/financials/FinancialsPage'), 'FinancialsPage')
const Globe = lazyRouteComponent(() => import('./features/globe/GlobePage'), 'GlobePage')
const About = lazyRouteComponent(() => import('./features/about/AboutPage'), 'AboutPage')

const rootRoute = createRootRoute({ component: AppShell, notFoundComponent: NotFound })

const routes = [
  createRoute({ getParentRoute: () => rootRoute, path: '/', component: Market }),
  createRoute({ getParentRoute: () => rootRoute, path: '/stock/$symbol', component: Stock }),
  createRoute({ getParentRoute: () => rootRoute, path: '/flows', component: Flows }),
  createRoute({ getParentRoute: () => rootRoute, path: '/forecast', component: Forecast }),
  createRoute({ getParentRoute: () => rootRoute, path: '/explain', component: ExplainIndex }),
  createRoute({ getParentRoute: () => rootRoute, path: '/explain/$symbol/$date', component: ExplainDetail }),
  createRoute({ getParentRoute: () => rootRoute, path: '/graph', component: Graph }),
  createRoute({ getParentRoute: () => rootRoute, path: '/graph/$symbol', component: Graph }),
  createRoute({ getParentRoute: () => rootRoute, path: '/financials', component: Financials }),
  createRoute({ getParentRoute: () => rootRoute, path: '/globe', component: Globe }),
  createRoute({ getParentRoute: () => rootRoute, path: '/about', component: About }),
]

export const router = createRouter({
  routeTree: rootRoute.addChildren(routes),
  history: createHashHistory(),
  defaultPreload: 'intent',
  defaultPendingComponent: () => <div className="p-4 text-xs text-text-3">載入中…</div>,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
