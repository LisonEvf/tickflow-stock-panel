import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Pencil, Plus, RefreshCw, Save, Trash2, X } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { api, type TradingFeeSettings, type TradingTrade, type TradingTradePayload } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

type TradeSide = 'buy' | 'sell'

interface AccountForm {
  principal: string
  cashAdjustment: string
  commissionPct: string
  minCommission: string
  stampTaxPct: string
  transferPct: string
}

interface TradeForm {
  symbol: string
  name: string
  side: TradeSide
  tradeTime: string
  price: string
  quantity: string
  fee: string
  note: string
}

const EMPTY_ACCOUNT_FORM: AccountForm = {
  principal: '100000',
  cashAdjustment: '0',
  commissionPct: '0.025',
  minCommission: '5',
  stampTaxPct: '0.05',
  transferPct: '0.001',
}

const INPUT_CLASS = 'h-9 w-full rounded-btn border border-border bg-base px-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted focus:border-accent'

function nowLocalInput(): string {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

function emptyTradeForm(): TradeForm {
  return {
    symbol: '',
    name: '',
    side: 'buy',
    tradeTime: nowLocalInput(),
    price: '',
    quantity: '',
    fee: '',
    note: '',
  }
}

function toMoney(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function toPrice(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toFixed(2)
}

function toPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return `${(Number(v) * 100).toFixed(2)}%`
}

function signedClass(v: number | null | undefined): string {
  const n = Number(v ?? 0)
  if (n > 0) return 'text-danger'
  if (n < 0) return 'text-bear'
  return 'text-secondary'
}

function pctToRate(v: string): number {
  return Math.max(0, Number(v || 0)) / 100
}

function rateToPct(v: number | null | undefined): string {
  return String(((Number(v ?? 0)) * 100).toFixed(4)).replace(/0+$/, '').replace(/\.$/, '')
}

function calcFee(side: TradeSide, price: number, quantity: number, fee: TradingFeeSettings | undefined): number {
  if (!fee || price <= 0 || quantity <= 0) return 0
  const amount = price * quantity
  const commission = Math.max(amount * fee.commission_rate, fee.min_commission)
  const stamp = side === 'sell' ? amount * fee.stamp_tax_rate : 0
  const transfer = amount * fee.transfer_fee_rate
  return commission + stamp + transfer
}

function accountToForm(fee: TradingFeeSettings | undefined, principal?: number, cashAdjustment?: number): AccountForm {
  return {
    principal: String(principal ?? 100000),
    cashAdjustment: String(cashAdjustment ?? 0),
    commissionPct: rateToPct(fee?.commission_rate ?? 0.00025),
    minCommission: String(fee?.min_commission ?? 5),
    stampTaxPct: rateToPct(fee?.stamp_tax_rate ?? 0.0005),
    transferPct: rateToPct(fee?.transfer_fee_rate ?? 0.00001),
  }
}

function tradeToForm(trade: TradingTrade): TradeForm {
  return {
    symbol: trade.symbol,
    name: trade.name ?? '',
    side: trade.side,
    tradeTime: String(trade.trade_time || '').slice(0, 16),
    price: String(trade.price),
    quantity: String(trade.quantity),
    fee: String(trade.fee ?? ''),
    note: trade.note ?? '',
  }
}

export function Trading() {
  const qc = useQueryClient()
  const portfolio = useQuery({
    queryKey: QK.tradingPortfolio,
    queryFn: api.tradingPortfolio,
  })

  const [accountForm, setAccountForm] = useState<AccountForm>(EMPTY_ACCOUNT_FORM)
  const [tradeForm, setTradeForm] = useState<TradeForm>(emptyTradeForm)
  const [editingTradeId, setEditingTradeId] = useState<string | null>(null)

  useEffect(() => {
    const account = portfolio.data?.account
    if (!account) return
    setAccountForm(accountToForm(account.fee_settings, account.principal, account.cash_adjustment))
  }, [portfolio.data?.account])

  const accountMutation = useMutation({
    mutationFn: () => api.tradingUpdateAccount({
      principal: Number(accountForm.principal || 0),
      cash_adjustment: Number(accountForm.cashAdjustment || 0),
      fee_settings: {
        commission_rate: pctToRate(accountForm.commissionPct),
        min_commission: Number(accountForm.minCommission || 0),
        stamp_tax_rate: pctToRate(accountForm.stampTaxPct),
        transfer_fee_rate: pctToRate(accountForm.transferPct),
      },
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.tradingPortfolio }),
  })

  const addTrade = useMutation({
    mutationFn: (payload: TradingTradePayload) => api.tradingAddTrade(payload),
    onSuccess: () => {
      setTradeForm(emptyTradeForm())
      qc.invalidateQueries({ queryKey: QK.tradingPortfolio })
    },
  })

  const updateTrade = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: TradingTradePayload }) => api.tradingUpdateTrade(id, payload),
    onSuccess: () => {
      setEditingTradeId(null)
      setTradeForm(emptyTradeForm())
      qc.invalidateQueries({ queryKey: QK.tradingPortfolio })
    },
  })

  const deleteTrade = useMutation({
    mutationFn: (id: string) => api.tradingDeleteTrade(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.tradingPortfolio }),
  })

  const feeSettings: TradingFeeSettings | undefined = useMemo(() => ({
    commission_rate: pctToRate(accountForm.commissionPct),
    min_commission: Number(accountForm.minCommission || 0),
    stamp_tax_rate: pctToRate(accountForm.stampTaxPct),
    transfer_fee_rate: pctToRate(accountForm.transferPct),
  }), [accountForm.commissionPct, accountForm.minCommission, accountForm.stampTaxPct, accountForm.transferPct])

  const feePreview = useMemo(() => {
    const explicit = tradeForm.fee.trim()
    if (explicit !== '') return Number(explicit || 0)
    return calcFee(tradeForm.side, Number(tradeForm.price || 0), Number(tradeForm.quantity || 0), feeSettings)
  }, [feeSettings, tradeForm.fee, tradeForm.price, tradeForm.quantity, tradeForm.side])

  const grossAmount = Number(tradeForm.price || 0) * Number(tradeForm.quantity || 0)
  const summary = portfolio.data?.summary
  const positions = portfolio.data?.positions ?? []
  const trades = portfolio.data?.trades ?? []

  const submitTrade = () => {
    const payload: TradingTradePayload = {
      symbol: tradeForm.symbol.trim().toUpperCase(),
      name: tradeForm.name.trim(),
      side: tradeForm.side,
      trade_time: tradeForm.tradeTime,
      price: Number(tradeForm.price || 0),
      quantity: Number(tradeForm.quantity || 0),
      fee: tradeForm.fee.trim() === '' ? undefined : Number(tradeForm.fee || 0),
      note: tradeForm.note.trim(),
    }
    if (editingTradeId) {
      updateTrade.mutate({ id: editingTradeId, payload })
    } else {
      addTrade.mutate(payload)
    }
  }

  const resetTrade = () => {
    setEditingTradeId(null)
    setTradeForm(emptyTradeForm())
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="交易录入" subtitle="手工同步账户 · 仓位参与 AI 个股分析" />

      <div className="flex-1 overflow-auto px-5 py-5">
        <div className="grid gap-3 lg:grid-cols-4">
          <Stat label="总资产" value={toMoney(summary?.total_assets)} />
          <Stat label="可用现金" value={toMoney(summary?.cash)} />
          <Stat label="持仓市值" value={toMoney(summary?.market_value)} sub={toPct(summary?.position_ratio)} />
          <Stat label="总盈亏" value={toMoney(summary?.total_pnl)} valueClass={signedClass(summary?.total_pnl)} />
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
          <section className="rounded-card border border-border bg-surface p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">账户与费用</h2>
              <button
                className="inline-flex h-7 items-center gap-1.5 rounded-btn border border-border px-2 text-xs text-secondary hover:text-foreground"
                onClick={() => accountMutation.mutate()}
                disabled={accountMutation.isPending}
              >
                <Save className="h-3.5 w-3.5" />
                保存
              </button>
            </div>
            <div className="mt-4 grid gap-3">
              <Field label="本金">
                <input className={INPUT_CLASS} value={accountForm.principal} type="number" step="1000" onChange={e => setAccountForm(f => ({ ...f, principal: e.target.value }))} />
              </Field>
              <Field label="现金校准">
                <input className={INPUT_CLASS} value={accountForm.cashAdjustment} type="number" step="100" onChange={e => setAccountForm(f => ({ ...f, cashAdjustment: e.target.value }))} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="佣金%">
                  <input className={INPUT_CLASS} value={accountForm.commissionPct} type="number" step="0.001" onChange={e => setAccountForm(f => ({ ...f, commissionPct: e.target.value }))} />
                </Field>
                <Field label="最低佣金">
                  <input className={INPUT_CLASS} value={accountForm.minCommission} type="number" step="0.1" onChange={e => setAccountForm(f => ({ ...f, minCommission: e.target.value }))} />
                </Field>
                <Field label="印花税%">
                  <input className={INPUT_CLASS} value={accountForm.stampTaxPct} type="number" step="0.001" onChange={e => setAccountForm(f => ({ ...f, stampTaxPct: e.target.value }))} />
                </Field>
                <Field label="过户费%">
                  <input className={INPUT_CLASS} value={accountForm.transferPct} type="number" step="0.0001" onChange={e => setAccountForm(f => ({ ...f, transferPct: e.target.value }))} />
                </Field>
              </div>
            </div>
          </section>

          <section className="rounded-card border border-border bg-surface p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">{editingTradeId ? '编辑成交' : '录入成交'}</h2>
              {editingTradeId && (
                <button className="inline-flex h-7 items-center gap-1 rounded-btn px-2 text-xs text-secondary hover:bg-elevated" onClick={resetTrade}>
                  <X className="h-3.5 w-3.5" />
                  取消
                </button>
              )}
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-6">
              <Field label="方向">
                <div className="grid grid-cols-2 rounded-btn border border-border bg-base p-0.5">
                  {(['buy', 'sell'] as TradeSide[]).map(side => (
                    <button
                      key={side}
                      className={`h-8 rounded text-xs ${tradeForm.side === side ? (side === 'buy' ? 'bg-danger/15 text-danger' : 'bg-bear/15 text-bear') : 'text-secondary hover:text-foreground'}`}
                      onClick={() => setTradeForm(f => ({ ...f, side }))}
                    >
                      {side === 'buy' ? '买入' : '卖出'}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label="代码">
                <input className={`${INPUT_CLASS} font-mono uppercase`} value={tradeForm.symbol} onChange={e => setTradeForm(f => ({ ...f, symbol: e.target.value.toUpperCase() }))} placeholder="000001.SZ" />
              </Field>
              <Field label="名称">
                <input className={INPUT_CLASS} value={tradeForm.name} onChange={e => setTradeForm(f => ({ ...f, name: e.target.value }))} />
              </Field>
              <Field label="价格">
                <input className={INPUT_CLASS} value={tradeForm.price} type="number" step="0.01" onChange={e => setTradeForm(f => ({ ...f, price: e.target.value }))} />
              </Field>
              <Field label="数量">
                <input className={INPUT_CLASS} value={tradeForm.quantity} type="number" step="100" onChange={e => setTradeForm(f => ({ ...f, quantity: e.target.value }))} />
              </Field>
              <Field label="成交时间">
                <input className={INPUT_CLASS} value={tradeForm.tradeTime} type="datetime-local" onChange={e => setTradeForm(f => ({ ...f, tradeTime: e.target.value }))} />
              </Field>
              <Field label="费用">
                <input className={INPUT_CLASS} value={tradeForm.fee} type="number" step="0.01" placeholder={toMoney(feePreview)} onChange={e => setTradeForm(f => ({ ...f, fee: e.target.value }))} />
              </Field>
              <Field label="备注">
                <input className={INPUT_CLASS} value={tradeForm.note} onChange={e => setTradeForm(f => ({ ...f, note: e.target.value }))} />
              </Field>
              <div className="lg:col-span-3 flex items-end justify-between gap-3">
                <div className="text-xs text-secondary">
                  <span className="font-mono text-foreground">{toMoney(grossAmount)}</span>
                  <span className="mx-2 text-muted/50">/</span>
                  <span>费用 {toMoney(feePreview)}</span>
                </div>
                <button
                  className="inline-flex h-9 items-center gap-1.5 rounded-btn bg-accent px-3 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-60"
                  onClick={submitTrade}
                  disabled={addTrade.isPending || updateTrade.isPending}
                >
                  {editingTradeId ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                  {editingTradeId ? '更新' : '录入'}
                </button>
              </div>
            </div>
          </section>
        </div>

        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <section className="rounded-card border border-border bg-surface p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">当前持仓</h2>
              <button
                aria-label="刷新持仓"
                className="rounded-btn p-1 text-secondary hover:bg-elevated hover:text-foreground"
                onClick={() => portfolio.refetch()}
              >
                <RefreshCw className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-3 overflow-auto">
              <table className="min-w-full text-left text-xs">
                <thead className="border-b border-border text-muted">
                  <tr>
                    <th className="py-2 pr-3 font-medium">标的</th>
                    <th className="py-2 pr-3 text-right font-medium">数量</th>
                    <th className="py-2 pr-3 text-right font-medium">成本/现价</th>
                    <th className="py-2 pr-3 text-right font-medium">市值</th>
                    <th className="py-2 text-right font-medium">浮盈亏</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {positions.map(pos => (
                    <tr key={pos.symbol}>
                      <td className="py-2 pr-3">
                        <div className="font-mono text-foreground">{pos.symbol}</div>
                        <div className="text-muted">{pos.name || '--'}</div>
                      </td>
                      <td className="py-2 pr-3 text-right font-mono text-foreground">{pos.quantity}</td>
                      <td className="py-2 pr-3 text-right font-mono">
                        <div className="text-foreground">{toPrice(pos.avg_cost)}</div>
                        <div className="text-muted">{toPrice(pos.latest_price)}</div>
                      </td>
                      <td className="py-2 pr-3 text-right font-mono text-foreground">
                        <div>{toMoney(pos.market_value)}</div>
                        <div className="text-muted">{toPct(pos.weight)}</div>
                      </td>
                      <td className={`py-2 text-right font-mono ${signedClass(pos.unrealized_pnl)}`}>
                        <div>{toMoney(pos.unrealized_pnl)}</div>
                        <div>{toPct(pos.unrealized_pnl_pct)}</div>
                      </td>
                    </tr>
                  ))}
                  {positions.length === 0 && (
                    <tr>
                      <td className="py-8 text-center text-muted" colSpan={5}>暂无持仓</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-card border border-border bg-surface p-4">
            <h2 className="text-sm font-semibold text-foreground">成交流水</h2>
            <div className="mt-3 overflow-auto">
              <table className="min-w-full text-left text-xs">
                <thead className="border-b border-border text-muted">
                  <tr>
                    <th className="py-2 pr-3 font-medium">时间</th>
                    <th className="py-2 pr-3 font-medium">标的</th>
                    <th className="py-2 pr-3 text-right font-medium">方向</th>
                    <th className="py-2 pr-3 text-right font-medium">价格/数量</th>
                    <th className="py-2 pr-3 text-right font-medium">费用</th>
                    <th className="py-2 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {trades.map(trade => (
                    <tr key={trade.id}>
                      <td className="py-2 pr-3 font-mono text-muted">{String(trade.trade_time).slice(0, 16).replace('T', ' ')}</td>
                      <td className="py-2 pr-3">
                        <div className="font-mono text-foreground">{trade.symbol}</div>
                        <div className="text-muted">{trade.name || trade.note || '--'}</div>
                      </td>
                      <td className={`py-2 pr-3 text-right font-medium ${trade.side === 'buy' ? 'text-danger' : 'text-bear'}`}>{trade.side === 'buy' ? '买入' : '卖出'}</td>
                      <td className="py-2 pr-3 text-right font-mono text-foreground">
                        <div>{toPrice(trade.price)}</div>
                        <div className="text-muted">{trade.quantity}</div>
                      </td>
                      <td className="py-2 pr-3 text-right font-mono text-foreground">{toMoney(trade.fee)}</td>
                      <td className="py-2 text-right">
                        <div className="inline-flex gap-1">
                          <button
                            aria-label={`编辑 ${trade.symbol} ${String(trade.trade_time).slice(0, 16)}`}
                            className="rounded-btn p-1 text-secondary hover:bg-elevated hover:text-foreground"
                            onClick={() => { setEditingTradeId(trade.id); setTradeForm(tradeToForm(trade)) }}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            aria-label={`删除 ${trade.symbol} ${String(trade.trade_time).slice(0, 16)}`}
                            className="rounded-btn p-1 text-secondary hover:bg-danger/10 hover:text-danger"
                            onClick={() => deleteTrade.mutate(trade.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {trades.length === 0 && (
                    <tr>
                      <td className="py-8 text-center text-muted" colSpan={6}>暂无成交</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, sub, valueClass }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <section className="rounded-card border border-border bg-surface px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={`mt-1 font-mono text-xl font-semibold ${valueClass ?? 'text-foreground'}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-secondary">{sub}</div>}
    </section>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] text-muted">{label}</span>
      {children}
    </label>
  )
}
