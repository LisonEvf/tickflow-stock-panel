import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useQuoteStream } from '@/lib/useQuoteStream'
import { ToastContainer } from '@/components/Toast'
import { AlertToastContainer } from '@/components/AlertToast'
import { AiAnalysisHost } from '@/components/financials/AiAnalysisHost'
import { AiReportBubble } from '@/components/financials/AiReportBubble'
import { StockAnalysisHost } from '@/components/stock-analysis/StockAnalysisHost'
import { StockAnalysisBubble } from '@/components/stock-analysis/StockAnalysisBubble'
import {
  useCapabilities,
  useSettings,
  usePreferences,
  useQuoteStatus,
  useVersion,
} from '@/lib/useSharedQueries'
import { QK } from '@/lib/queryKeys'
import { tierRank } from '@/lib/capability-labels'
import {
  Star,
  ScanSearch,
  History,
  FileText,
  Settings,
  Database,
  Loader2,
  LayoutDashboard,
  Tags,
  Flame,
  BarChart3,
  Sparkles,
  Layers3,
  Landmark,
  Cable,
  RadioTower,
  CheckCircle2,
  BookOpenCheck,
  Bot,
} from 'lucide-react'
import { Logo } from './Logo'
import { api, type IndexQuote } from '@/lib/api'
import { cn } from '@/lib/cn'
import { setCurrentTotal as setAlertTotal, useUnreadAlerts } from '@/lib/monitorBadge'

// 品牌色 — 只用于 logo / brand 区域,不影响功能语义色
const BRAND = '#8B5CF6'
const CORE_INDEXES = [
  { symbol: '000001.SH', name: '上证指数' },
  { symbol: '399001.SZ', name: '深证成指' },
  { symbol: '399006.SZ', name: '创业板指' },
  { symbol: '000680.SH', name: '科创综指' },
] as const

type CoreIndex = (typeof CORE_INDEXES)[number]

const nav = [
  { to: '/',                label: '看板',     icon: LayoutDashboard },
  { to: '/watchlist',  label: '自选',   icon: Star },
  { to: '/screener',   label: '策略',   icon: ScanSearch },
  { to: '/backtest',   label: '回测',   icon: History },
  { to: '/limit-ladder', label: '连板梯队', icon: Flame },
  { to: '/concept-analysis', label: '概念分析', icon: Layers3 },
  { to: '/industry-analysis', label: '行业分析', icon: Landmark },
  { to: '/financials', label: '财务分析', icon: FileText },
  { to: '/llm-service', label: 'LLM服务', icon: Bot },
  { to: '/monitor', label: '监控中心', icon: RadioTower },
  { to: '/review',      label: '复盘',   icon: BookOpenCheck },
  { to: '/indices', label: '指数', icon: BarChart3 },
  { to: '/trading', label: '交易', icon: Cable },
  { to: '/data',       label: '数据',   icon: Database },
] as const

function fmtIndexValue(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toFixed(2)
}

function fmtIndexPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`
}

function indexPctClass(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return 'text-muted'
  const n = Number(v)
  if (n === 0) return 'text-foreground'
  return n > 0 ? 'text-bull' : 'text-bear'
}

/** 监控中心未读徽标 — 仅在非监控页且有未读时显示。 */
function MonitorBadge({ active }: { active: boolean }) {
  const unread = useUnreadAlerts()
  // 尊重用户设置: 可在菜单设置里关闭数字提示
  const badgeEnabled = (() => {
    try { return localStorage.getItem('monitor_badge_enabled') !== '0' } catch { return true }
  })()
  if (active || unread <= 0 || !badgeEnabled) return null
  return (
    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[9px] font-bold text-white animate-pulse">
      {unread > 99 ? '99+' : unread}
    </span>
  )
}

function SidebarIndexQuotes({ rows, items }: { rows: IndexQuote[] | undefined; items: CoreIndex[] }) {
  if (items.length === 0) return null
  const quoteBySymbol = new Map((rows ?? []).map(q => [q.symbol, q]))
  return (
    <div className="mt-2 grid grid-cols-2 gap-1.5">
      {items.map(item => {
        const q = quoteBySymbol.get(item.symbol)
        const value = q?.last_price ?? q?.close
        const pct = q?.change_pct
        return (
          <NavLink
            key={item.symbol}
            to={`/indices?symbol=${encodeURIComponent(item.symbol)}`}
            className="block rounded bg-elevated/60 px-2 py-1.5 transition-colors hover:bg-elevated"
            title={`${item.name} ${item.symbol}`}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="text-[10px] text-secondary">{item.name}</span>
              <span className={`text-[10px] font-mono ${indexPctClass(pct)}`}>{fmtIndexPct(pct)}</span>
            </div>
            <div className="mt-0.5 truncate font-mono text-[10px] text-foreground/80">
              {fmtIndexValue(value)}
            </div>
          </NavLink>
        )
      })}
    </div>
  )
}

function AIConfigBadge({ configured, model }: { configured?: boolean; model?: string }) {
  return (
    <NavLink
      to="/settings?tab=ai"
      className="mt-2 group block -mx-2.5"
      title="AI 配置"
    >
      <div className="relative overflow-hidden rounded-lg border border-purple-400/20 bg-gradient-to-br from-purple-500/[0.12] via-surface to-surface px-3 py-2 transition-all hover:border-purple-400/35 hover:from-purple-500/[0.16]">
        <div className="absolute -right-5 -top-6 h-14 w-14 rounded-full bg-purple-500/10 blur-2xl" />
        <div className="relative flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-purple-400/10 text-purple-300 ring-1 ring-purple-400/20">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-foreground">AI 配置</span>
              <span className={`h-1.5 w-1.5 rounded-full ${configured ? 'bg-bear' : 'bg-warning'}`} />
            </div>
            <div className="mt-0.5 truncate text-[10px] leading-tight text-muted">
              {configured ? (model || '已接入模型') : '接入策略生成模型'}
            </div>
          </div>
          <Settings className="h-3 w-3 text-muted group-hover:text-purple-300 transition-colors" />
        </div>
      </div>
    </NavLink>
  )
}

export function Layout() {
  // ===== 共享 hooks (替代内联 useQuery) =====
  const { data: caps } = useCapabilities()
  const { data: settingsState } = useSettings()
  const { data: versionData } = useVersion()
  const { data: prefs } = usePreferences()
  // poll=true: 全局唯一开启条件轮询 (非交易时段 60s 兜底, 交易时段靠 SSE)
  const { data: quoteStatus } = useQuoteStatus({ poll: true })
  const { data: analysisMenus } = useQuery({
    queryKey: QK.analysisMenus,
    queryFn: api.analysisMenus,
  })

  // 数据同步状态轮询: 有活跃 job 时「数据」菜单项显示转圈
  const { data: pipelineJobs } = useQuery({
    queryKey: QK.pipelineJobs,
    queryFn: () => api.pipelineJobs(1),
    refetchInterval: (query) => (query.state.data?.active_id ? 2000 : 15000),
    refetchIntervalInBackground: true,
  })
  const isDataSyncing = !!pipelineJobs?.active_id

  // 数据同步完成的"瞬时反馈": isDataSyncing 从 true→false 时显示绿色对勾,
  // 闪烁约 3 秒后自动消失。
  const [dataSyncJustDone, setDataSyncJustDone] = useState(false)
  const prevSyncingRef = useRef(false)
  useEffect(() => {
    // 仅在"刚结束"(true→false)且非首次挂载时触发
    if (prevSyncingRef.current && !isDataSyncing) {
      setDataSyncJustDone(true)
      const t = setTimeout(() => setDataSyncJustDone(false), 3000)
      prevSyncingRef.current = isDataSyncing
      return () => clearTimeout(t)
    }
    prevSyncingRef.current = isDataSyncing
  }, [isDataSyncing])

  const version = versionData?.version
  const sidebarIndexSymbols = prefs?.sidebar_index_symbols ?? CORE_INDEXES.map(p => p.symbol)
  const sidebarIndexes = CORE_INDEXES.filter(item => sidebarIndexSymbols.includes(item.symbol))
  const { data: sidebarIndexQuotes } = useQuery({
    queryKey: [...QK.indexQuotes, 'sidebar', sidebarIndexSymbols.join(',')] as const,
    queryFn: () => api.indexQuotes(sidebarIndexes.map(p => p.symbol)),
    enabled: sidebarIndexes.length > 0,
    placeholderData: (prev) => prev,
  })

  // SSE: 行情更新时自动刷新相关 queries + 告警通知
  useQuoteStream(true, prefs?.sse_refresh_pages)

  const isRunning = quoteStatus?.running ?? false
  const isTrading = quoteStatus?.is_trading_hours ?? false
  const tier = tierRank(caps?.label ?? '')
  const isNoneTier = tier < 0
  const isWatchlistMode = tier === 0
  const realtimeModeLabel = isWatchlistMode ? '自选股' : '全市场'

  // 轮询触发记录总数 → 更新监控中心徽标 (每 15 秒)
  const alertsTotalQuery = useQuery({
    queryKey: ['alerts-total'],
    queryFn: () => api.alertsList({ days: 7, limit: 1 }),
    refetchInterval: 15000,
    refetchIntervalInBackground: true,
    select: (data) => data.total,
  })
  // 只在拿到真实总数时同步徽标 (避免 data=undefined 时传 0 重置 lastSeen)
  const alertsTotal = alertsTotalQuery.data
  useEffect(() => {
    if (alertsTotal != null) setAlertTotal(alertsTotal)
  }, [alertsTotal])

  // 合并内置页面 + 可见的扩展分析菜单
  const analysisNav = (analysisMenus?.items ?? [])
    .filter(m => m.visible)
    .map(m => ({ to: `/analysis/${m.id}`, label: m.label, icon: m.icon === 'tags' ? Tags : BarChart3 }))

  const allNav = [...nav, ...analysisNav]
  const savedOrder = prefs?.nav_order ?? []

  const navItems = savedOrder.length > 0
    ? (() => {
        const byTo = new Map(allNav.map(n => [n.to, n]))
        const ordered = savedOrder
          .map(id => byTo.get(id) ?? byTo.get(`/analysis/${id}`))
          .filter(Boolean)
        const seen = new Set(ordered.map(n => n!.to))
        return [...ordered as typeof allNav, ...allNav.filter(n => !seen.has(n.to))]
      })()
    : allNav

  const hiddenIds = new Set(prefs?.nav_hidden ?? [])
  const visibleNavItems = navItems.filter(n => !hiddenIds.has(n.to) && !hiddenIds.has(n.to.replace(/^\/analysis\//, '')))

  return (
    <div className="h-screen grid grid-cols-[14rem_1fr] bg-base text-foreground overflow-hidden">
      <aside className="border-r border-border bg-surface flex flex-col h-full min-h-0 overflow-hidden">
        <div className="px-5 py-5 border-b border-border shrink-0">
          {/* Brand block — 原创 logo + 等宽 wordmark */}
          <div className="flex items-center gap-2.5">
            <Logo
              size={28}
              className="shrink-0 drop-shadow-[0_0_8px_rgba(139,92,246,0.5)]"
              style={{ color: BRAND }}
            />
            <div
              className="font-mono font-bold text-[13px] tracking-[0.06em] text-foreground leading-tight"
              style={{ textShadow: `0 0 10px ${BRAND}44` }}
            >
              <div>OpenTDX</div>
              <div>Stock Panel</div>
            </div>
          </div>

          <div className="mt-2.5 text-[10px] uppercase tracking-[0.22em] text-secondary">
            Quant · Terminal
          </div>

          <div
            className="mt-3 h-px"
            style={{ background: `linear-gradient(90deg, ${BRAND}88, transparent 80%)` }}
          />

          <AIConfigBadge
            configured={settingsState?.ai_configured ?? settingsState?.has_ai_key}
            model={settingsState?.ai_model}
          />
        </div>

        <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-3 space-y-0.5">
          {visibleNavItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2 rounded-btn text-sm transition-colors duration-150 ease-smooth',
                  isActive
                    ? 'bg-elevated text-foreground font-medium'
                    : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="flex-1">{label}</span>
                  {/* Beta 标识 */}
                  {to === '/review' && (
                    <span className="inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-400 shrink-0">
                      Beta
                    </span>
                  )}
                  {/* 数据同步状态: 同步中转圈, 刚完成显示绿色对勾闪烁 3 秒 */}
                  {to === '/data' && isDataSyncing && (
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
                  )}
                  {to === '/data' && !isDataSyncing && dataSyncJustDone && (
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-bull animate-pulse" />
                  )}
                  {/* 监控中心徽标: 仅非监控页且有未读时显示 */}
                  {to === '/monitor' && <MonitorBadge active={isActive} />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 全局行情开关 */}
        <div className="border-t border-border px-3 py-2.5 shrink-0">
          {isNoneTier ? (
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-secondary truncate">实时行情</span>
                <span className="text-[10px] text-muted font-medium bg-elevated px-1.5 py-0.5 rounded">
                  不可用
                </span>
              </div>
              <div className="mt-1.5 text-[10px] leading-snug text-muted">
                当前数据能力不足，实时监控暂不可用
              </div>
            </div>
          ) : (
            /* 实时轮询常开 — 状态 + 跳转设置 */
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <span className={`inline-block h-1.5 w-1.5 rounded-full shrink-0 ${
                  isRunning && isTrading
                    ? 'bg-accent animate-pulse'
                    : isRunning
                      ? 'bg-warning/60'
                      : 'bg-muted'
                }`} />
                <span className="text-xs text-secondary truncate">
                  实时行情 · {realtimeModeLabel}
                </span>
                <NavLink
                  to="/settings?tab=monitoring"
                  className="text-secondary hover:text-foreground transition-colors shrink-0"
                  title="实时监控设置"
                >
                  <Settings className="h-3 w-3" />
                </NavLink>
              </div>
              <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">自动</span>
            </div>
          )}

          {/* 状态提示 */}
          {!isNoneTier && (
            <div className="mt-1.5 text-[10px] leading-snug">
              {isRunning && isTrading ? (
                <span className="text-accent">行情运行中</span>
              ) : isRunning ? (
                <span className="text-warning/70">休市轮询中</span>
              ) : (
                <span className="text-warning/70">行情服务启动中</span>
              )}
            </div>
          )}
          {!isWatchlistMode && !isNoneTier && (
            <SidebarIndexQuotes rows={sidebarIndexQuotes?.rows} items={sidebarIndexes} />
          )}
        </div>

        <div className="border-t border-border px-2 py-3 space-y-0.5 shrink-0">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              cn(
                'flex items-center justify-between gap-3 px-3 py-2 rounded-btn text-sm transition-colors duration-150 ease-smooth',
                isActive
                  ? 'bg-elevated text-foreground font-medium'
                  : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
              )
            }
          >
            <span className="flex items-center gap-3">
              <Settings className="h-4 w-4 shrink-0" />
              <span>设置</span>
            </span>
            <span className="font-mono text-[10px] text-muted/50 select-none">
              {version ?? ''}
            </span>
          </NavLink>
        </div>
      </aside>

      <motion.main
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="h-full overflow-auto scrollbar-gutter-stable"
      >
        <Outlet />
      </motion.main>
      <ToastContainer />
      <AlertToastContainer />
      <AiAnalysisHost />
      <AiReportBubble />
      <StockAnalysisHost />
      <StockAnalysisBubble />
    </div>
  )
}
