import { useEffect, useMemo, useState } from 'react'
import type React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  CreditCard,
  ExternalLink,
  KeyRound,
  Loader2,
  LogIn,
  LogOut,
  Plug,
  Plus,
  RefreshCw,
  Save,
  Server,
  Trash2,
  Wallet,
  Zap,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { toast } from '@/components/Toast'
import { api, type LlmServerCreateOrderResult, type LlmServerGroup, type LlmServerGroupId, type LlmServerGroupsResponse, type SettingsState } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

const TOKEN_KEY = 'opentdx_llm_server_access_token'
const DEFAULT_MODEL = 'gpt-5.5'

function money(value: number | null | undefined) {
  const n = Number(value ?? 0)
  return `$${n.toFixed(4)}`
}

function compactMoney(value: number | null | undefined) {
  const n = Number(value ?? 0)
  return n >= 100 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`
}

function maskKey(key: string | undefined) {
  if (!key) return '--'
  if (key.length <= 16) return key
  return `${key.slice(0, 8)}...${key.slice(-6)}`
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

function orderStatusLabel(status: string | undefined) {
  const map: Record<string, string> = {
    PENDING: '待支付',
    PAID: '已支付',
    COMPLETED: '已完成',
    EXPIRED: '已过期',
    CANCELLED: '已取消',
    FAILED: '失败',
  }
  return map[status ?? ''] ?? (status || '--')
}

function orderStatusClass(status: string | undefined) {
  if (status === 'COMPLETED' || status === 'PAID') return 'text-bear bg-bear/10 border-bear/20'
  if (status === 'PENDING') return 'text-warning bg-warning/10 border-warning/20'
  if (status === 'FAILED' || status === 'EXPIRED' || status === 'CANCELLED') return 'text-danger bg-danger/10 border-danger/20'
  return 'text-muted bg-elevated border-border'
}

function paymentLabel(key: string) {
  const labels: Record<string, string> = {
    alipay: '支付宝',
    wxpay: '微信支付',
    wechat: '微信支付',
    stripe: 'Stripe',
    easypay: '易支付',
    airwallex: 'Airwallex',
  }
  return labels[key] ?? key
}

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

function keyGroupLabel(groupId: LlmServerGroupId | null | undefined, groups: LlmServerGroup[]) {
  if (groupId == null || groupId === '') return '--'
  const match = groups.find(group => groupValue(group) === String(groupId))
  return match ? groupLabel(match) : String(groupId)
}

export function LLMService() {
  const qc = useQueryClient()
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
  const [amount, setAmount] = useState('10')
  const [paymentType, setPaymentType] = useState('')
  const [activeOrder, setActiveOrder] = useState<LlmServerCreateOrderResult | null>(null)

  const config = useQuery({
    queryKey: ['llm-server-config'],
    queryFn: api.llmServerConfig,
  })
  const health = useQuery({
    queryKey: ['llm-server-health'],
    queryFn: api.llmServerHealth,
    refetchOnWindowFocus: false,
  })
  const settings = useQuery({
    queryKey: QK.settings,
    queryFn: api.settings,
  })
  const profile = useQuery({
    queryKey: ['llm-server-profile', token],
    queryFn: () => api.llmServerProfile(token),
    enabled: !!token,
    retry: false,
  })
  const usage = useQuery({
    queryKey: ['llm-server-usage', token],
    queryFn: () => api.llmServerUsageStats(token),
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
  const checkout = useQuery({
    queryKey: ['llm-server-checkout', token],
    queryFn: () => api.llmServerCheckoutInfo(token),
    enabled: !!token,
    retry: false,
  })
  const orders = useQuery({
    queryKey: ['llm-server-orders', token],
    queryFn: () => api.llmServerOrders(token),
    enabled: !!token,
    retry: false,
  })

  useEffect(() => {
    if (config.data?.base_url) setServerUrl(config.data.base_url)
  }, [config.data?.base_url])

  const paymentTypes = useMemo(() => {
    const methods = checkout.data?.methods ?? {}
    return Object.entries(methods)
      .filter(([, cfg]) => cfg?.enabled !== false)
      .map(([key]) => key)
  }, [checkout.data?.methods])

  useEffect(() => {
    if (!paymentType && paymentTypes.length > 0) setPaymentType(paymentTypes[0])
  }, [paymentType, paymentTypes])

  const groupItems = useMemo(() => normalizeGroups(groups.data), [groups.data])

  useEffect(() => {
    if (groupItems.length === 0) {
      if (selectedGroupId) setSelectedGroupId('')
      return
    }
    const availableValues = groupItems.map(groupValue).filter(Boolean)
    if (selectedGroupId && availableValues.includes(selectedGroupId)) return

    const defaultGroupId = !Array.isArray(groups.data)
      ? groups.data?.default_group_id ?? groups.data?.default_group
      : null
    const defaultValue = defaultGroupId == null ? '' : String(defaultGroupId)
    const nextValue = defaultValue && availableValues.includes(defaultValue)
      ? defaultValue
      : availableValues[0]
    setSelectedGroupId(nextValue ?? '')
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
    const appliedKey = currentTail
      ? items.find(k => keyTail(k.key).endsWith(currentTail))
      : undefined
    const nextKey = appliedKey ?? items.find(k => k.status === 'active') ?? items[0]
    if (nextKey?.id) setSelectedKeyId(nextKey.id)
  }, [keys.data?.items, selectedKeyId, settings.data?.ai_api_key_masked])

  const saveConfig = useMutation({
    mutationFn: () => api.llmServerSaveConfig(serverUrl),
    onSuccess: (data) => {
      setServerUrl(data.base_url)
      qc.invalidateQueries({ queryKey: ['llm-server-health'] })
      toast('LLM 服务器地址已保存', 'success')
    },
  })

  const login = useMutation({
    mutationFn: () => api.llmServerLogin(email.trim(), password),
    onSuccess: (data) => {
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setToken(data.access_token)
      setPassword('')
      toast('LLM 服务已登录', 'success')
    },
  })

  const register = useMutation({
    mutationFn: () => api.llmServerRegister({
      email: email.trim(),
      password,
      verify_code: verifyCode.trim() || undefined,
      promo_code: promoCode.trim() || undefined,
    }),
    onSuccess: (data) => {
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setToken(data.access_token)
      setPassword('')
      toast('账户已创建', 'success')
    },
  })

  const createKey = useMutation({
    mutationFn: () => {
      const payload: { name: string; group_id?: LlmServerGroupId | null } = {
        name: keyName.trim() || 'OpenTDX Stock Panel',
      }
      const groupId = groupPayloadValue(selectedGroupId)
      if (groupId != null) payload.group_id = groupId
      return api.llmServerCreateKey(token, payload)
    },
    onSuccess: (data) => {
      setSelectedKeyId(data.id)
      qc.invalidateQueries({ queryKey: ['llm-server-keys', token] })
      toast('API Key 已创建', 'success')
    },
  })

  const deleteKey = useMutation({
    mutationFn: (id: number) => api.llmServerDeleteKey(token, id),
    onSuccess: () => {
      setSelectedKeyId(null)
      qc.invalidateQueries({ queryKey: ['llm-server-keys', token] })
      toast('API Key 已删除', 'success')
    },
  })

  const useKey = useMutation({
    mutationFn: () => api.llmServerUseKey(selectedKey?.key ?? '', model, config.data?.base_url ?? serverUrl),
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
      toast('OpenTDX AI 已切换到 LLM 服务', 'success')
    },
  })

  const createOrder = useMutation({
    mutationFn: () => api.llmServerCreateOrder(token, {
      amount: Number(amount),
      payment_type: paymentType,
      order_type: 'balance',
      return_url: `${window.location.origin}/llm-service`,
    }),
    onSuccess: (data) => {
      setActiveOrder(data)
      qc.invalidateQueries({ queryKey: ['llm-server-orders', token] })
      toast('充值订单已创建', 'success')
    },
  })

  const verifyOrder = useMutation({
    mutationFn: (outTradeNo: string) => api.llmServerVerifyOrder(token, outTradeNo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['llm-server-profile', token] })
      qc.invalidateQueries({ queryKey: ['llm-server-orders', token] })
      toast('订单状态已刷新', 'success')
    },
  })

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    setToken('')
    setSelectedKeyId(null)
    setActiveOrder(null)
  }

  const selectedKeyUsable = isUsableApiKey(selectedKey?.key)
  const canUseKey = selectedKeyUsable && !!model.trim() && !useKey.isPending
  const canCreateKey = !createKey.isPending && (!groups.isLoading || groupItems.length === 0 || !!selectedGroupId)
  const canCreateOrder = !!paymentType && Number(amount) > 0 && !createOrder.isPending

  return (
    <>
      <PageHeader
        title="LLM 服务"
        subtitle="账户、余额、API Key 与 OpenTDX AI 接入。"
        right={
          token && (
            <button
              onClick={logout}
              className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border bg-surface px-3 text-xs text-secondary hover:text-danger"
            >
              <LogOut className="h-3.5 w-3.5" />
              退出
            </button>
          )
        }
      />

      <div className="space-y-5 px-4 py-4 sm:px-6 lg:px-8 lg:py-6">
        <section className="grid gap-4 xl:grid-cols-[1.3fr_0.8fr]">
          <Panel icon={Server} title="服务器">
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                value={serverUrl}
                onChange={e => setServerUrl(e.target.value)}
                className="h-9 min-w-0 flex-1 rounded-lg bg-base px-3 text-xs font-mono text-foreground ring-1 ring-border/40 focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
              <button
                onClick={() => saveConfig.mutate()}
                disabled={saveConfig.isPending}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-accent px-3 text-xs font-medium text-white disabled:opacity-50"
              >
                {saveConfig.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                保存
              </button>
              <button
                onClick={() => health.refetch()}
                className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg border border-border bg-base px-3 text-xs text-secondary hover:text-foreground"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                检测
              </button>
            </div>
            <div className="mt-3 flex flex-col gap-2 text-xs sm:flex-row sm:items-center">
              <span className={cn('inline-flex h-6 items-center rounded-full border px-2', health.data?.ok ? 'border-bear/20 bg-bear/10 text-bear' : 'border-warning/20 bg-warning/10 text-warning')}>
                {health.isFetching ? '检测中' : health.data?.ok ? '可连接' : '未连接'}
              </span>
              <span className="truncate text-muted">
                OpenAI 兼容地址：{config.data?.gateway_base_url ?? `${serverUrl.replace(/\/$/, '')}/v1`}
              </span>
            </div>
          </Panel>

          <Panel icon={Plug} title="OpenTDX AI">
            <div className="space-y-2 text-xs">
              <Line label="当前地址" value={settings.data?.ai_base_url || '--'} mono />
              <Line label="当前模型" value={settings.data?.ai_model || '--'} />
              <Line label="连接状态" value={settings.data?.ai_configured ? '已配置' : '未配置'} />
            </div>
          </Panel>
        </section>

        {!token ? (
          <section className="grid gap-4 xl:grid-cols-[0.85fr_1.15fr]">
            <Panel icon={LogIn} title={authMode === 'login' ? '登录账户' : '注册账户'}>
              <div className="mb-4 inline-flex rounded-lg bg-elevated p-1 text-xs">
                <button
                  onClick={() => setAuthMode('login')}
                  className={cn('rounded-md px-3 py-1.5', authMode === 'login' ? 'bg-base text-foreground' : 'text-muted')}
                >
                  登录
                </button>
                <button
                  onClick={() => setAuthMode('register')}
                  className={cn('rounded-md px-3 py-1.5', authMode === 'register' ? 'bg-base text-foreground' : 'text-muted')}
                >
                  注册
                </button>
              </div>
              <div className="space-y-3">
                <Field label="邮箱">
                  <input value={email} onChange={e => setEmail(e.target.value)} className={inputCls} />
                </Field>
                <Field label="密码">
                  <input type="password" value={password} onChange={e => setPassword(e.target.value)} className={inputCls} />
                </Field>
                {authMode === 'register' && (
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="验证码">
                      <input value={verifyCode} onChange={e => setVerifyCode(e.target.value)} className={inputCls} />
                    </Field>
                    <Field label="邀请码/优惠码">
                      <input value={promoCode} onChange={e => setPromoCode(e.target.value)} className={inputCls} />
                    </Field>
                  </div>
                )}
                <button
                  onClick={() => authMode === 'login' ? login.mutate() : register.mutate()}
                  disabled={!email.trim() || !password || login.isPending || register.isPending}
                  className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-accent text-sm font-semibold text-white disabled:opacity-40"
                >
                  {(login.isPending || register.isPending) ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
                  {authMode === 'login' ? '登录' : '创建账户'}
                </button>
              </div>
            </Panel>

            <Panel icon={Wallet} title="账户入口">
              <div className="grid gap-3 sm:grid-cols-2">
                <QuickLink href={`${serverUrl.replace(/\/$/, '')}/register`} label="注册页" />
                <QuickLink href={`${serverUrl.replace(/\/$/, '')}/login`} label="登录页" />
                <QuickLink href={`${serverUrl.replace(/\/$/, '')}/purchase`} label="充值页" />
                <QuickLink href={`${serverUrl.replace(/\/$/, '')}/keys`} label="API Key" />
              </div>
            </Panel>
          </section>
        ) : (
          <>
            <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Stat title="余额" value={money(profile.data?.balance)} icon={Wallet} />
              <Stat title="今日请求" value={String(usage.data?.today_requests ?? 0)} icon={Zap} />
              <Stat title="今日扣费" value={compactMoney(usage.data?.today_actual_cost)} icon={CreditCard} />
              <Stat title="有效 Key" value={String(usage.data?.active_api_keys ?? keys.data?.items?.filter(k => k.status === 'active').length ?? 0)} icon={KeyRound} />
            </section>

            <section className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
              <Panel icon={KeyRound} title="API Key">
                <div className="mb-4 flex flex-col gap-2 sm:flex-row">
                  <input
                    value={keyName}
                    onChange={e => setKeyName(e.target.value)}
                    className={`${inputCls} min-w-0 flex-1`}
                  />
                  <select
                    value={selectedGroupId}
                    onChange={e => setSelectedGroupId(e.target.value)}
                    disabled={groups.isLoading || groupItems.length === 0}
                    className="h-9 min-w-[180px] rounded-lg bg-base px-3 text-xs text-foreground ring-1 ring-border/40 focus:outline-none focus:ring-2 focus:ring-accent/30 disabled:opacity-50"
                  >
                    {groups.isLoading && <option value="">加载分组...</option>}
                    {!groups.isLoading && groupItems.length === 0 && <option value="">服务端默认分组</option>}
                    {groupItems.map(group => {
                      const value = groupValue(group)
                      return <option key={value || groupLabel(group)} value={value}>{groupLabel(group)}</option>
                    })}
                  </select>
                  <button
                    onClick={() => createKey.mutate()}
                    disabled={!canCreateKey}
                    className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-accent px-3 text-xs font-medium text-white disabled:opacity-50"
                  >
                    {createKey.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                    新建
                  </button>
                </div>
                {groups.isError && (
                  <div className="mb-3 rounded-lg border border-warning/20 bg-warning/10 px-3 py-2 text-xs text-warning">
                    暂时无法读取可用分组，可继续新建并使用服务端默认分组。
                  </div>
                )}
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="min-w-[760px] w-full text-xs">
                    <thead className="bg-elevated/60 text-muted">
                      <tr>
                        <th className="w-9 px-3 py-2" />
                        <th className="px-3 py-2 text-left">名称</th>
                        <th className="px-3 py-2 text-left">分组</th>
                        <th className="px-3 py-2 text-left">Key</th>
                        <th className="px-3 py-2 text-left">状态</th>
                        <th className="px-3 py-2 text-right">已用</th>
                        <th className="w-12 px-3 py-2" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {(keys.data?.items ?? []).map(k => (
                        <tr key={k.id} className={selectedKeyId === k.id ? 'bg-accent/5' : undefined}>
                          <td className="px-3 py-2">
                            <input type="radio" checked={selectedKeyId === k.id} onChange={() => setSelectedKeyId(k.id)} />
                          </td>
                          <td className="px-3 py-2 text-foreground">{k.name}</td>
                          <td className="px-3 py-2 text-muted">{keyGroupLabel(k.group_id, groupItems)}</td>
                          <td className="px-3 py-2 font-mono text-muted">{maskKey(k.key)}</td>
                          <td className="px-3 py-2">{k.status}</td>
                          <td className="px-3 py-2 text-right font-mono">{money(k.quota_used)}</td>
                          <td className="px-3 py-2 text-right">
                            <button
                              onClick={() => deleteKey.mutate(k.id)}
                              className="text-muted hover:text-danger"
                              title="删除"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))}
                      {keys.isLoading && (
                        <tr>
                          <td colSpan={7} className="px-3 py-8 text-center text-muted">加载中...</td>
                        </tr>
                      )}
                      {!keys.isLoading && (keys.data?.items ?? []).length === 0 && (
                        <tr>
                          <td colSpan={7} className="px-3 py-8 text-center text-muted">暂无 API Key</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </Panel>

              <Panel icon={Check} title="一键接入">
                <div className="space-y-3">
                  <Field label="模型">
                    <input value={model} onChange={e => setModel(e.target.value)} className={inputCls} />
                  </Field>
                  <div className="rounded-lg border border-border bg-base px-3 py-2 text-xs">
                    <Line label="选中 Key" value={selectedKey?.name ?? '--'} />
                    <Line label="分组" value={keyGroupLabel(selectedKey?.group_id, groupItems)} />
                    <Line label="网关地址" value={config.data?.gateway_base_url ?? `${serverUrl.replace(/\/$/, '')}/v1`} mono />
                  </div>
                  {selectedKey && !selectedKeyUsable && (
                    <div className="rounded-lg border border-warning/20 bg-warning/10 px-3 py-2 text-xs leading-relaxed text-warning">
                      当前 Key 只有脱敏值,无法直接接入。请新建 Key 后立即使用,或在「设置 → AI」中粘贴完整 Key。
                    </div>
                  )}
                  <button
                    onClick={() => useKey.mutate()}
                    disabled={!canUseKey}
                    className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-accent text-sm font-semibold text-white disabled:opacity-40"
                  >
                    {useKey.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
                    使用此 Key
                  </button>
                </div>
              </Panel>
            </section>

            <section className="grid gap-4 xl:grid-cols-[0.8fr_1.2fr]">
              <Panel icon={CreditCard} title="余额充值">
                <div className="space-y-3">
                  <Field label="金额">
                    <input type="number" value={amount} onChange={e => setAmount(e.target.value)} min={checkout.data?.global_min ?? 1} className={inputCls} />
                  </Field>
                  <Field label="支付方式">
                    <select value={paymentType} onChange={e => setPaymentType(e.target.value)} className={inputCls}>
                      {paymentTypes.map(t => <option key={t} value={t}>{paymentLabel(t)}</option>)}
                    </select>
                  </Field>
                  <button
                    onClick={() => createOrder.mutate()}
                    disabled={!canCreateOrder}
                    className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-accent text-sm font-semibold text-white disabled:opacity-40"
                  >
                    {createOrder.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CreditCard className="h-4 w-4" />}
                    创建订单
                  </button>
                  {activeOrder && (
                    <div className="rounded-lg border border-border bg-base p-3 text-xs">
                      <Line label="订单号" value={activeOrder.out_trade_no ?? String(activeOrder.order_id)} mono />
                      <Line label="实付" value={money(activeOrder.pay_amount)} />
                      {activeOrder.pay_url && <QuickLink href={activeOrder.pay_url} label="打开支付页" compact />}
                      {activeOrder.qr_code && (
                        <img
                          src={activeOrder.qr_code.startsWith('http') || activeOrder.qr_code.startsWith('data:') ? activeOrder.qr_code : `data:image/png;base64,${activeOrder.qr_code}`}
                          className="mt-2 h-32 w-32 rounded-lg bg-white object-contain p-1"
                          alt="支付二维码"
                        />
                      )}
                      {activeOrder.out_trade_no && (
                        <button
                          onClick={() => verifyOrder.mutate(activeOrder.out_trade_no!)}
                          className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-3 text-xs text-secondary hover:text-foreground"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                          刷新订单
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </Panel>

              <Panel icon={Wallet} title="最近订单">
                <div className="space-y-2">
                  {(orders.data?.items ?? []).map(o => (
                    <div key={o.id} className="grid grid-cols-[1fr_auto] items-center gap-3 rounded-lg border border-border bg-base px-3 py-2 text-xs sm:grid-cols-[1fr_auto_auto]">
                      <div className="min-w-0">
                        <div className="truncate font-mono text-foreground">{o.out_trade_no}</div>
                        <div className="mt-0.5 text-muted">{paymentLabel(o.payment_type)} · {money(o.pay_amount)}</div>
                      </div>
                      <span className={cn('rounded-full border px-2 py-0.5', orderStatusClass(o.status))}>{orderStatusLabel(o.status)}</span>
                      {o.out_trade_no && (
                        <button
                          onClick={() => verifyOrder.mutate(o.out_trade_no)}
                          className="justify-self-end text-muted hover:text-foreground"
                          title="刷新"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  ))}
                  {!orders.isLoading && (orders.data?.items ?? []).length === 0 && (
                    <div className="rounded-lg border border-border bg-base px-3 py-8 text-center text-xs text-muted">暂无订单</div>
                  )}
                </div>
              </Panel>
            </section>
          </>
        )}
      </div>
    </>
  )
}

const inputCls = 'h-9 w-full rounded-lg bg-base px-3 text-xs text-foreground ring-1 ring-border/40 focus:outline-none focus:ring-2 focus:ring-accent/30'

function Panel({ icon: Icon, title, children }: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="mb-4 flex items-center gap-2.5">
        <Icon className="h-4 w-4 text-secondary" />
        <h2 className="text-sm font-medium text-foreground">{title}</h2>
      </div>
      {children}
    </section>
  )
}

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
      <span className={cn('min-w-0 truncate text-right text-foreground', mono && 'font-mono')}>{value}</span>
    </div>
  )
}

function Stat({ title, value, icon: Icon }: {
  title: string
  value: string
  icon: React.ComponentType<{ className?: string }>
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted">{title}</span>
        <Icon className="h-4 w-4 text-secondary" />
      </div>
      <div className="mt-3 font-mono text-xl font-semibold text-foreground">{value}</div>
    </section>
  )
}

function QuickLink({ href, label, compact }: { href: string; label: string; compact?: boolean }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={cn(
        'inline-flex items-center justify-between gap-2 rounded-lg border border-border bg-base text-xs text-secondary hover:border-accent/40 hover:text-accent',
        compact ? 'mt-2 h-8 px-3' : 'h-12 px-3',
      )}
    >
      <span>{label}</span>
      <ExternalLink className="h-3.5 w-3.5" />
    </a>
  )
}
