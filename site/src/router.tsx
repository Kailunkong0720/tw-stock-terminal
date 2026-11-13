import {
  createHashHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Link,
} from '@tanstack/react-router'

import { AppShell } from './app/AppShell'
import { AboutPage } from './features/about/AboutPage'
import { ExplainDetailPage, ExplainIndexPage } from './features/explain/ExplainPages'
import { ForecastPage } from './features/forecast/ForecastPage'
import { MarketPage } from './features/market/MarketPage'
import { SectionPage } from './features/placeholder/SectionPage'
import { StockPage } from './features/stock/StockPage'

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

const rootRoute = createRootRoute({ component: AppShell, notFoundComponent: NotFound })

const routes = [
  createRoute({ getParentRoute: () => rootRoute, path: '/', component: MarketPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/stock/$symbol', component: StockPage }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/flows',
    component: () => (
      <SectionPage
        title="資金流向"
        detail="外資與三大法人每日買賣超：個股、產業輪動、全市場，皆可沿時間軸播放。"
      />
    ),
  }),
  createRoute({ getParentRoute: () => rootRoute, path: '/forecast', component: ForecastPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/explain', component: ExplainIndexPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/explain/$symbol/$date', component: ExplainDetailPage }),
  createRoute({
    getParentRoute: () => rootRoute,
    path: '/graph',
    component: () => (
      <SectionPage title="知識圖譜" detail="公司、產業、全球實體與事件之間的關係，以及每次大波動的解釋路徑。" />
    ),
  }),
  createRoute({ getParentRoute: () => rootRoute, path: '/about', component: AboutPage }),
]

export const router = createRouter({
  routeTree: rootRoute.addChildren(routes),
  history: createHashHistory(),
  defaultPreload: 'intent',
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
