import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Loader2,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  Sparkles,
  LineChart,
  ScanSearch,
  Flame,
  Zap,
  Radar,
  ShieldCheck,
  BellRing,
  TrendingUp,
  FileText,
  Landmark,
  Bot,
  KeyRound,
  LogIn,
  UserPlus,
  Plug,
  Server,
  Wallet,
  ExternalLink,
} from 'lucide-react'
import { api, type LlmServerGroup, type LlmServerGroupId, type LlmServerGroupsResponse, type SettingsState } from '@/lib/api'
import { useSettings } from '@/lib/useSharedQueries'
import { QK } from '@/lib/queryKeys'
import { Logo } from '@/components/Logo'

const TOKEN_KEY = 'opentdx_llm_server_access_token'
const DEFAULT_MODEL = 'gpt-5.5'

// ===== 引导页:3 步向导 =====
// 0. 欢迎  1. 官方 LLM 服务  2. 完成 → 写标记 → 进面板

const STEPS = ['欢迎', 'LLM 服务', '完成'] as const

const BRAND = '#8B5CF6'

const HIGHLIGHTS = [
  { icon: LineChart,   title: '看板与自选', desc: '市场全景看板、涨跌分布、情绪雷达,自定义自选列表', tint: 'text-accent' },
  { icon: ScanSearch,  title: '策略选股',   desc: '内置多套选股策略,一键扫描全市场命中标的', tint: 'text-bull' },
  { icon: TrendingUp,  title: '个股详情',   desc: '详情页内一键 AI 分析,关键价位、技术形态一目了然', tint: 'text-warning' },
  { icon: Flame,       title: '连板梯队',   desc: '涨停梯队、封板强度、炸板监控,情绪温度计', tint: 'text-warning' },
  { icon: Landmark,    title: '概念行业',   desc: '概念板块、行业维度的资金流向与热度排名', tint: 'text-accent' },
  { icon: FileText,    title: '财务分析',   desc: '官方 LLM 服务可直接支撑财报与个股 AI 解读', tint: 'text-bear' },
  { icon: ShieldCheck, title: '回测验证',   desc: '策略历史回测、因子分析,用数据验证逻辑', tint: 'text-accent' },
  { icon: Radar,       title: '实时监控',   desc: '自定义条件 / 策略监控,盘中触发即推送告警', tint: 'text-bear' },
  { icon: BellRing,    title: '本地优先',   desc: 'OpenTDX 数据源默认可用,行情与记录本地存储', tint: 'text-bull' },
]

function normalizeGroups(data: LlmServerGroupsResponse | undefined): LlmServerGroup[] {
  if (!data) return []
  if (Array.isArray(data)) return data
  if (Array.isArray(data.items)) return data.items
  if (Array.isArray(data.groups)) return data.groups
  if (Array.isArray(data.data)) return data.data
  return []
}

function groupValue(group: LlmServerGroup): string {
  const raw = group.id ?? group.group_id ?? group.value ?? group.code ?? group.name
  return raw == null ? '' : String(raw)
}

function groupLabel(group: LlmServerGroup): string {
  return group.name ?? group.label ?? group.display_name ?? group.code ?? `分组 ${groupValue(group)}`
}

function groupPayloadValue(value: string): LlmServerGroupId | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  return /^-?\d+$/.test(trimmed) ? Number(trimmed) : trimmed
}

function keyTail(key: string | null | undefined) {
  const value = (key ?? '').trim()
  const match = value.match(/[A-Za-z0-9_-]+$/)
  return match?.[0] ?? ''
}

function isUsableApiKey(key: string | undefined) {
  const value = (key ?? '').trim()
  return value.length > 16 && !value.includes('...') && !/[•*]/.test(value)
}

function money(value: number | null | undefined) {
  const n = Number(value ?? 0)
  return `$${n.toFixed(4)}`
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : '操作失败,请稍后重试'
}

export function Onboarding() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [step, setStep] = useState(0)

  const complete = useMutation({
    mutationFn: api.completeOnboarding,
    onSuccess: (data) => {
      qc.setQueryData(QK.settings, (old: any) =>
        old ? { ...old, onboarding_completed: data.onboarding_completed } : old,
      )
      qc.invalidateQueries({ queryKey: QK.settings })
      navigate('/', { replace: true })
    },
    onError: () => {
      navigate('/', { replace: true })
    },
  })

  const finish = () => complete.mutate()

  return (
    <div className="relative min-h-screen bg-base overflow-hidden flex flex-col">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute -top-40 -left-40 h-[28rem] w-[28rem] rounded-full blur-[120px] opacity-20"
          style={{ background: `radial-gradient(circle, ${BRAND}, transparent 70%)` }}
        />
        <div
          className="absolute -bottom-40 -right-32 h-[26rem] w-[26rem] rounded-full blur-[120px] opacity-15"
          style={{ background: 'radial-gradient(circle, hsl(var(--accent)), transparent 70%)' }}
        />
        <div
          className="absolute inset-0 opacity-[0.025]"
          style={{
            backgroundImage:
              'linear-gradient(hsl(var(--fg-primary)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--fg-primary)) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
        />
      </div>

      <header className="relative z-10 flex items-center justify-between px-6 py-4 border-b border-border">
        <div className="flex items-center gap-2.5 text-foreground">
          <Logo
            size={24}
            className="shrink-0"
            style={{ color: BRAND, filter: `drop-shadow(0 0 8px ${BRAND}55)` }}
          />
          <span className="text-sm font-semibold tracking-tight">OpenTDX Stock Panel</span>
        </div>
        <div className="flex items-center gap-1.5">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-1.5">
              {i > 0 && <div className="h-px w-3 bg-border" />}
              <motion.div
                animate={{
                  width: i === step ? 64 : 24,
                  backgroundColor: i === step
                    ? 'hsl(var(--accent))'
                    : i < step
                      ? 'hsl(var(--accent) / 0.6)'
                      : 'hsl(var(--border))',
                }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                className="h-1.5 rounded-full"
              />
            </div>
          ))}
        </div>
        <div className="w-[88px] text-right">
          <span className="text-xs text-muted tabular">
            {step + 1} / {STEPS.length}
          </span>
        </div>
      </header>

      <main className="relative z-10 flex-1 flex items-center justify-center px-6 py-10">
        <div className="w-full max-w-2xl">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            >
              {step === 0 && <WelcomeStep onNext={() => setStep(1)} onSkip={finish} />}
              {step === 1 && (
                <LlmServiceStep
                  onNext={() => setStep(2)}
                  onSkip={finish}
                  onBack={() => setStep(0)}
                />
              )}
              {step === 2 && <FinishStep onNext={finish} onBack={() => setStep(1)} pending={complete.isPending} />}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  )
}

function WelcomeStep({ onNext, onSkip }: { onNext: () => void; onSkip: () => void }) {
  return (
    <div className="text-center">
      <motion.div
        initial={{ scale: 0.85, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="mx-auto w-fit rounded-2xl p-4 border border-border"
        style={{ background: `linear-gradient(135deg, ${BRAND}22, transparent)` }}
      >
        <Sparkles className="h-8 w-8" style={{ color: BRAND }} />
      </motion.div>

      <h1 className="mt-6 text-3xl font-bold text-foreground tracking-tight">
        欢迎使用 OpenTDX Stock Panel
      </h1>
      <p className="mt-3 text-sm text-secondary leading-relaxed max-w-md mx-auto">
        OpenTDX 行情数据源已经默认可用。初始化只需要接入官方 LLM 服务,
        也可以跳过后进入面板再配置。
      </p>

      <div className="mt-8 grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-left">
        {HIGHLIGHTS.map((h, i) => (
          <motion.div
            key={h.title}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.04 * i + 0.1 }}
            whileHover={{ y: -2 }}
            className="group flex items-start gap-2.5 rounded-card border border-border bg-surface/80 backdrop-blur-sm p-2.5 transition-colors hover:border-accent/30"
          >
            <div className="rounded-lg bg-elevated/50 p-1.5 shrink-0">
              <h.icon className={`h-4 w-4 ${h.tint} transition-transform group-hover:scale-110`} />
            </div>
            <div className="min-w-0">
              <div className="text-xs font-medium text-foreground">{h.title}</div>
              <div className="mt-0.5 text-[11px] text-muted leading-snug line-clamp-2">{h.desc}</div>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="mt-8 flex items-center justify-center gap-3">
        <button
          onClick={onNext}
          className="inline-flex items-center gap-2 px-6 h-11 rounded-xl bg-accent text-white text-sm font-semibold shadow-lg shadow-accent/20 hover:bg-accent/90 hover:shadow-accent/30 transition-all"
        >
          接入官方 LLM
          <ArrowRight className="h-4 w-4" />
        </button>
        <button
          onClick={onSkip}
          className="px-4 h-11 rounded-xl text-sm text-secondary hover:text-foreground hover:bg-elevated transition-colors"
        >
          跳过
        </button>
      </div>
    </div>
  )
}

function LlmServiceStep({
  onNext,
  onSkip,
  onBack,
}: {
  onNext: () => void
  onSkip: () => void
  onBack: () => void
}) {
  const qc = useQueryClient()
  const settings = useSettings()
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? '')
  const [serverUrl, setServerUrl] = useState('http://127.0.0.1:18080')
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [verifyCode, setVerifyCode] = useState('')
  const [promoCode, setPromoCode] = useState('')
  const [keyName, setKeyName] = useState('OpenTDX Stock Panel')
  const [selectedGroupId, setSelectedGroupId] = useState('')
  const [selectedKeyId, setSelectedKeyId] = useState<number | null>(null)
  const [model, setModel] = useState(DEFAULT_MODEL)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const config = useQuery({
    queryKey: ['llm-server-config'],
    queryFn: api.llmServerConfig,
  })
  const health = useQuery({
    queryKey: ['llm-server-health'],
    queryFn: api.llmServerHealth,
    refetchOnWindowFocus: false,
  })
  const profile = useQuery({
    queryKey: ['llm-server-profile', token],
    queryFn: () => api.llmServerProfile(token),
    enabled: !!token,
    retry: false,
  })
  const keys = useQuery({
    queryKey: ['llm-server-keys', token],
    queryFn: () => api.llmServerKeys(token),
    enabled: !!token,
    retry: false,
  })
  const groups = useQuery({
    queryKey: ['llm-server-groups', token],
    queryFn: () => api.llmServerGroupsAvailable(token),
    enabled: !!token,
    retry: false,
  })

  useEffect(() => {
    if (config.data?.base_url) setServerUrl(config.data.base_url)
  }, [config.data?.base_url])

  const gatewayUrl = config.data?.gateway_base_url ?? `${serverUrl.replace(/\/$/, '')}/v1`
  const isOfficialConfigured = Boolean(
    settings.data?.ai_configured &&
    settings.data?.ai_base_url &&
    settings.data.ai_base_url.replace(/\/$/, '') === gatewayUrl.replace(/\/$/, ''),
  )
  const groupItems = useMemo(() => normalizeGroups(groups.data), [groups.data])

  useEffect(() => {
    if (groupItems.length === 0) {
      if (selectedGroupId) setSelectedGroupId('')
      return
    }
    const values = groupItems.map(groupValue).filter(Boolean)
    if (selectedGroupId && values.includes(selectedGroupId)) return
    const defaultGroupId = !Array.isArray(groups.data)
      ? groups.data?.default_group_id ?? groups.data?.default_group
      : null
    const defaultValue = defaultGroupId == null ? '' : String(defaultGroupId)
    setSelectedGroupId(defaultValue && values.includes(defaultValue) ? defaultValue : values[0] ?? '')
  }, [groupItems, groups.data, selectedGroupId])

  const selectedKey = useMemo(() => {
    const items = keys.data?.items ?? []
    return items.find(k => k.id === selectedKeyId) ?? items.find(k => k.status === 'active') ?? items[0]
  }, [keys.data?.items, selectedKeyId])

  useEffect(() => {
    if (selectedKeyId) return
    const items = keys.data?.items ?? []
    if (items.length === 0) return
    const currentTail = keyTail(settings.data?.ai_api_key_masked)
    const appliedKey = currentTail ? items.find(k => keyTail(k.key).endsWith(currentTail)) : undefined
    const nextKey = appliedKey ?? items.find(k => k.status === 'active') ?? items[0]
    if (nextKey?.id) setSelectedKeyId(nextKey.id)
  }, [keys.data?.items, selectedKeyId, settings.data?.ai_api_key_masked])

  const login = useMutation({
    mutationFn: () => api.llmServerLogin(email.trim(), password),
    onMutate: () => {
      setError('')
      setMessage('')
    },
    onSuccess: (data) => {
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setToken(data.access_token)
      setPassword('')
      setMessage('登录成功,可以继续创建或接入 API Key。')
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const register = useMutation({
    mutationFn: () => api.llmServerRegister({
      email: email.trim(),
      password,
      verify_code: verifyCode.trim() || undefined,
      promo_code: promoCode.trim() || undefined,
    }),
    onMutate: () => {
      setError('')
      setMessage('')
    },
    onSuccess: (data) => {
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setToken(data.access_token)
      setPassword('')
      setMessage('账户已创建,可以继续创建或接入 API Key。')
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const connect = useMutation({
    mutationFn: async () => {
      if (!token) throw new Error('请先登录或注册官方 LLM 服务')
      const modelName = model.trim() || DEFAULT_MODEL
      let apiKey = isUsableApiKey(selectedKey?.key) ? selectedKey?.key ?? '' : ''
      if (!apiKey) {
        const payload: { name: string; group_id?: LlmServerGroupId | null } = {
          name: keyName.trim() || 'OpenTDX Stock Panel',
        }
        const groupId = groupPayloadValue(selectedGroupId)
        if (groupId != null) payload.group_id = groupId
        const created = await api.llmServerCreateKey(token, payload)
        apiKey = created.key
        setSelectedKeyId(created.id)
      }
      if (!isUsableApiKey(apiKey)) {
        throw new Error('未拿到完整 API Key,请新建 Key 后再接入')
      }
      return api.llmServerUseKey(apiKey, modelName, config.data?.base_url ?? serverUrl)
    },
    onMutate: () => {
      setError('')
      setMessage('')
    },
    onSuccess: (data) => {
      qc.setQueryData<SettingsState>(QK.settings, prev => prev ? {
        ...prev,
        ai_provider: data.ai_provider,
        ai_base_url: data.ai_base_url,
        ai_api_key_masked: data.ai_api_key_masked,
        has_ai_key: true,
        ai_configured: data.ai_configured,
        ai_model: data.ai_model,
        ai_codex_command: 'codex',
      } : prev)
      qc.invalidateQueries({ queryKey: QK.settings })
      qc.invalidateQueries({ queryKey: ['llm-server-keys', token] })
      setMessage('官方 LLM 服务已接入 OpenTDX AI。')
      onNext()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const busy = login.isPending || register.isPending || connect.isPending
  const canAuth = !!email.trim() && !!password && !busy
  const canConnect = !!token && !!model.trim() && !busy && (!groups.isLoading || groupItems.length === 0 || !!selectedGroupId)

  return (
    <div>
      <div className="flex items-center gap-2.5">
        <div className="rounded-lg bg-accent/10 p-2">
          <Bot className="h-4 w-4 text-accent" />
        </div>
        <h2 className="text-xl font-bold text-foreground">接入官方 LLM 服务</h2>
      </div>
      <p className="mt-2.5 text-sm text-secondary leading-relaxed">
        行情数据已经默认走 OpenTDX。官方 LLM 服务用于个股分析、财务解读和复盘生成,
        这里可以完成注册登录并一键应用到 AI 设置。
      </p>

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <StatusTile
          icon={Server}
          title="服务状态"
          value={health.isFetching ? '检测中' : health.data?.ok ? '可连接' : '未连接'}
          tone={health.data?.ok ? 'good' : 'warn'}
        />
        <StatusTile
          icon={Wallet}
          title="账户余额"
          value={token ? money(profile.data?.balance) : '--'}
          tone={token ? 'good' : 'muted'}
        />
        <StatusTile
          icon={Plug}
          title="AI 接入"
          value={isOfficialConfigured ? '已接入' : settings.data?.ai_configured ? '已配置其他' : '未接入'}
          tone={isOfficialConfigured ? 'good' : 'muted'}
        />
      </div>

      {!token ? (
        <div className="mt-5 rounded-card border border-border bg-surface/80 p-4">
          <div className="mb-4 inline-flex rounded-lg bg-elevated p-1 text-xs">
            <button
              onClick={() => setAuthMode('login')}
              className={`rounded-md px-3 py-1.5 ${authMode === 'login' ? 'bg-base text-foreground' : 'text-muted'}`}
            >
              登录
            </button>
            <button
              onClick={() => setAuthMode('register')}
              className={`rounded-md px-3 py-1.5 ${authMode === 'register' ? 'bg-base text-foreground' : 'text-muted'}`}
            >
              注册
            </button>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="邮箱">
              <input value={email} onChange={e => setEmail(e.target.value)} className={inputCls} />
            </Field>
            <Field label="密码">
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} className={inputCls} />
            </Field>
          </div>

          {authMode === 'register' && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="验证码">
                <input value={verifyCode} onChange={e => setVerifyCode(e.target.value)} className={inputCls} />
              </Field>
              <Field label="邀请码/优惠码">
                <input value={promoCode} onChange={e => setPromoCode(e.target.value)} className={inputCls} />
              </Field>
            </div>
          )}

          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
            <button
              onClick={() => authMode === 'login' ? login.mutate() : register.mutate()}
              disabled={!canAuth}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-accent px-5 text-sm font-semibold text-white disabled:opacity-40"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : authMode === 'login' ? <LogIn className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />}
              {authMode === 'login' ? '登录官方服务' : '创建账户'}
            </button>
            <QuickLink href={`${serverUrl.replace(/\/$/, '')}/${authMode === 'login' ? 'login' : 'register'}`} label="打开网页版" />
          </div>
        </div>
      ) : isOfficialConfigured ? (
        <div className="mt-5 rounded-card border border-bear/25 bg-bear/[0.06] p-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-bear" />
            <div>
              <div className="text-sm font-medium text-foreground">官方 LLM 服务已接入</div>
              <p className="mt-1 text-xs text-secondary leading-relaxed">
                当前模型为 {settings.data?.ai_model || DEFAULT_MODEL},进入面板后可直接使用 AI 个股分析和复盘功能。
              </p>
            </div>
          </div>
        </div>
      ) : (
        <div className="mt-5 rounded-card border border-border bg-surface/80 p-4">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-medium text-foreground">{profile.data?.email ?? '已登录官方 LLM 服务'}</div>
              <div className="mt-1 text-xs text-muted">
                余额 {money(profile.data?.balance)} · API Key {(keys.data?.items ?? []).length} 个
              </div>
            </div>
            <a
              href="/llm-service"
              className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-btn border border-border bg-base px-3 text-xs text-secondary hover:text-accent sm:mt-0"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              服务中心
            </a>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_160px]">
            <Field label="Key 名称">
              <input value={keyName} onChange={e => setKeyName(e.target.value)} className={inputCls} />
            </Field>
            <Field label="模型">
              <input value={model} onChange={e => setModel(e.target.value)} className={inputCls} />
            </Field>
          </div>

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="分组">
              <select
                value={selectedGroupId}
                onChange={e => setSelectedGroupId(e.target.value)}
                disabled={groups.isLoading || groupItems.length === 0}
                className={inputCls}
              >
                {groups.isLoading && <option value="">加载分组...</option>}
                {!groups.isLoading && groupItems.length === 0 && <option value="">服务端默认分组</option>}
                {groupItems.map(group => {
                  const value = groupValue(group)
                  return <option key={value || groupLabel(group)} value={value}>{groupLabel(group)}</option>
                })}
              </select>
            </Field>
            <Field label="当前 Key">
              <select
                value={selectedKey?.id ?? ''}
                onChange={e => setSelectedKeyId(e.target.value ? Number(e.target.value) : null)}
                disabled={keys.isLoading || (keys.data?.items ?? []).length === 0}
                className={inputCls}
              >
                {keys.isLoading && <option value="">加载 Key...</option>}
                {!keys.isLoading && (keys.data?.items ?? []).length === 0 && <option value="">自动新建</option>}
                {(keys.data?.items ?? []).map(key => (
                  <option key={key.id} value={key.id}>{key.name}</option>
                ))}
              </select>
            </Field>
          </div>

          {groups.isError && (
            <div className="mt-3 rounded-lg border border-warning/20 bg-warning/10 px-3 py-2 text-xs text-warning">
              暂时无法读取可用分组,仍可使用服务端默认分组自动新建 Key。
            </div>
          )}

          <div className="mt-4 rounded-lg border border-border bg-base px-3 py-2 text-xs">
            <Line label="网关地址" value={gatewayUrl} mono />
            <Line label="接入策略" value={isUsableApiKey(selectedKey?.key) ? '使用选中 Key' : '自动新建 Key 后接入'} />
          </div>
        </div>
      )}

      {message && (
        <div className="mt-4 rounded-btn border border-bear/30 bg-bear/5 px-3 py-2 text-xs text-bear">
          {message}
        </div>
      )}
      {error && (
        <div className="mt-4 rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
          {error}
        </div>
      )}

      <div className="mt-6 flex items-center justify-between">
        <button
          onClick={onBack}
          disabled={busy}
          className="inline-flex items-center gap-1.5 px-3 h-9 rounded-btn text-sm text-secondary hover:text-foreground transition-colors disabled:opacity-40"
        >
          <ArrowLeft className="h-4 w-4" />
          上一步
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={onSkip}
            disabled={busy}
            className="px-4 h-9 rounded-btn text-sm text-secondary hover:text-foreground transition-colors disabled:opacity-40"
          >
            跳过
          </button>
          {isOfficialConfigured ? (
            <button
              onClick={onNext}
              className="inline-flex items-center gap-2 px-5 h-9 rounded-xl bg-accent text-white text-sm font-semibold hover:bg-accent/90 transition-colors"
            >
              继续
              <ArrowRight className="h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={() => connect.mutate()}
              disabled={!canConnect}
              className="inline-flex items-center gap-2 px-5 h-9 rounded-xl bg-accent text-white text-sm font-semibold hover:bg-accent/90 disabled:opacity-40 transition-all"
            >
              {connect.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
              一键接入
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function FinishStep({ onNext, onBack, pending }: { onNext: () => void; onBack: () => void; pending: boolean }) {
  const tips = [
    { icon: TrendingUp, text: '打开任意个股详情:点击 AI 分析生成操作建议' },
    { icon: FileText, text: '进入财务分析:官方 LLM 服务可解读利润、资负、现金流' },
    { icon: Wallet, text: 'LLM 服务页:查看余额、充值、管理 API Key 与分组' },
  ]

  return (
    <div className="text-center">
      <motion.div
        initial={{ scale: 0.85, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="mx-auto w-fit"
      >
        <div
          className="relative rounded-2xl p-5 border border-border"
          style={{ background: `linear-gradient(135deg, ${BRAND}22, transparent)` }}
        >
          <CheckCircle2 className="h-12 w-12 text-bear" />
          <motion.div
            animate={{ scale: [1, 1.4], opacity: [0.4, 0] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: 'easeOut' }}
            className="absolute inset-5 rounded-full bg-bear/30"
          />
        </div>
      </motion.div>

      <h1 className="mt-6 text-2xl font-bold text-foreground">初始化完成</h1>
      <p className="mt-2.5 text-sm text-secondary leading-relaxed max-w-md mx-auto">
        OpenTDX 数据源默认可用。进入面板后即可查看行情、运行策略,
        已接入 LLM 时可直接使用所有 AI 分析功能。
      </p>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.2 }}
        className="mt-5 flex items-start gap-2.5 rounded-card border border-accent/30 bg-accent/[0.06] px-4 py-3 text-left"
      >
        <div className="rounded-lg bg-accent/15 p-1.5 shrink-0 mt-px">
          <Zap className="h-4 w-4 text-accent" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-medium text-foreground">下一步:开始分析</div>
          <p className="mt-1 text-xs text-secondary leading-relaxed">
            如果暂时跳过了 LLM 接入,后续可从左侧「LLM服务」或「设置 → AI」继续配置。
          </p>
        </div>
      </motion.div>

      <div className="mt-4 space-y-2 text-left">
        {tips.map((t, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: 0.1 * i + 0.3 }}
            className="flex items-center gap-3 rounded-card border border-border bg-surface/80 backdrop-blur-sm px-3.5 py-2.5"
          >
            <div className="rounded-lg bg-accent/10 p-1.5 shrink-0">
              <t.icon className="h-3.5 w-3.5 text-accent" />
            </div>
            <span className="text-xs text-secondary">{t.text}</span>
          </motion.div>
        ))}
      </div>

      <div className="mt-8 flex items-center justify-between">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 px-3 h-10 rounded-btn text-sm text-secondary hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          上一步
        </button>
        <button
          onClick={onNext}
          disabled={pending}
          className="inline-flex items-center gap-2 px-6 h-10 rounded-xl bg-accent text-white text-sm font-semibold shadow-lg shadow-accent/20 hover:bg-accent/90 hover:shadow-accent/30 disabled:opacity-60 transition-all"
        >
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {pending ? '正在进入…' : '进入面板'}
        </button>
      </div>
    </div>
  )
}

const inputCls = 'h-9 w-full rounded-lg bg-base px-3 text-xs text-foreground ring-1 ring-border/40 focus:outline-none focus:ring-2 focus:ring-accent/30 disabled:opacity-50'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-[10px] uppercase tracking-wider text-muted/70">{label}</span>
      {children}
    </label>
  )
}

function Line({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-muted">{label}</span>
      <span className={`min-w-0 truncate text-right text-foreground ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

function QuickLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl border border-border bg-base px-4 text-sm text-secondary hover:border-accent/40 hover:text-accent"
    >
      <ExternalLink className="h-3.5 w-3.5" />
      {label}
    </a>
  )
}

function StatusTile({ icon: Icon, title, value, tone }: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  value: string
  tone: 'good' | 'warn' | 'muted'
}) {
  const cls = tone === 'good'
    ? 'border-bear/25 bg-bear/[0.06] text-bear'
    : tone === 'warn'
      ? 'border-warning/25 bg-warning/[0.06] text-warning'
      : 'border-border bg-surface/80 text-secondary'
  return (
    <div className={`rounded-card border p-3 ${cls}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-[10px] uppercase tracking-wider opacity-75">{title}</span>
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="mt-2 truncate text-sm font-semibold text-foreground">{value}</div>
    </div>
  )
}
