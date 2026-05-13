import { useState, useEffect } from 'react'
import styles from './BrokerageView.module.css'

const fmt  = (n, dec = 2) => n == null ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec })
const fmtD = (n) => n == null ? '—' : `$${fmt(n)}`
const pct  = (n) => n == null ? '—' : `${n >= 0 ? '+' : ''}${fmt(n)}%`
const clr  = (n) => n >= 0 ? styles.green : styles.red

export default function BrokerageView() {
  const [account,   setAccount]   = useState(null)
  const [positions, setPositions] = useState([])
  const [orders,    setOrders]    = useState([])
  const [config,    setConfig]    = useState(null)
  const [tab,       setTab]       = useState('positions')
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)

  // Manual order state
  const [orderSymbol, setOrderSymbol] = useState('')
  const [orderSide,   setOrderSide]   = useState('buy')
  const [orderQty,    setOrderQty]    = useState('')
  const [orderBusy,   setOrderBusy]   = useState(false)
  const [orderMsg,    setOrderMsg]    = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [acc, pos, ord, cfg] = await Promise.all([
        fetch('/alpaca/account').then(r => r.json()),
        fetch('/alpaca/positions').then(r => r.json()),
        fetch('/alpaca/orders').then(r => r.json()),
        fetch('/alpaca/config').then(r => r.json()),
      ])
      setAccount(acc)
      setPositions(Array.isArray(pos) ? pos : [])
      setOrders(Array.isArray(ord) ? ord : [])
      setConfig(cfg)
    } catch (e) {
      setError('Could not connect to Alpaca. Check your API keys in Settings.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // Auto-refresh every 30s
  useEffect(() => {
    const iv = setInterval(load, 30_000)
    return () => clearInterval(iv)
  }, [])

  const saveConfig = async (patch) => {
    const next = { ...config, ...patch }
    setConfig(next)
    await fetch('/alpaca/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(next),
    })
  }

  const submitOrder = async () => {
    if (!orderSymbol || !orderQty) return
    setOrderBusy(true)
    setOrderMsg(null)
    try {
      const res = await fetch('/alpaca/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: orderSymbol.toUpperCase(), side: orderSide, qty: parseFloat(orderQty) }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Order failed')
      setOrderMsg({ ok: true, text: `✓ Order submitted — ${orderSide.toUpperCase()} ${orderQty} ${orderSymbol.toUpperCase()}` })
      setOrderSymbol(''); setOrderQty('')
      setTimeout(load, 2000)
    } catch (e) {
      setOrderMsg({ ok: false, text: e.message })
    } finally {
      setOrderBusy(false)
    }
  }

  const closePosition = async (symbol) => {
    if (!confirm(`Close entire position in ${symbol}?`)) return
    await fetch(`/alpaca/positions/${symbol}`, { method: 'DELETE' })
    setTimeout(load, 1500)
  }

  if (loading && !account) return (
    <div className={styles.loading}>
      <span className={styles.spinner} />
      <span>Connecting to Alpaca…</span>
    </div>
  )

  if (error) return (
    <div className={styles.error}>
      <span>⚠️</span>
      <p>{error}</p>
      <a href="#" onClick={e => { e.preventDefault(); /* switch to settings */ }}>Go to Settings →</a>
    </div>
  )

  const todayPnl    = account?.pnl_today ?? 0
  const todayPnlPct = account?.pnl_today_pct ?? 0
  const isPaper     = config?.paper !== false

  return (
    <div className={styles.page}>

      {/* ── Header ── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageTitle}>
          <span>📊</span>
          <span>Brokerage</span>
          {isPaper && <span className={styles.paperBadge}>PAPER</span>}
        </div>
        <button className={styles.refreshBtn} onClick={load}>↺ Refresh</button>
      </div>

      {/* ── Account metrics ── */}
      {account && (
        <div className={styles.metricsRow}>
          <MetricCard label="Portfolio Value"  value={fmtD(account.portfolio_value)} />
          <MetricCard label="Cash"             value={fmtD(account.cash)} />
          <MetricCard label="Buying Power"     value={fmtD(account.buying_power)} />
          <MetricCard
            label="Today's P&L"
            value={`${todayPnl >= 0 ? '+' : ''}${fmtD(todayPnl)}`}
            sub={pct(todayPnlPct)}
            color={todayPnl >= 0 ? 'green' : 'red'}
          />
        </div>
      )}

      {/* ── Auto-trade config ── */}
      {config && (
        <div className={styles.autoTradeCard}>
          <div className={styles.autoTradeHeader}>
            <div className={styles.autoTradeTitle}>
              <span>🤖</span>
              <span>Auto-Trading</span>
              <span className={config.auto_trade ? styles.badgeOn : styles.badgeOff}>
                {config.auto_trade ? 'ENABLED' : 'OFF'}
              </span>
            </div>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                checked={config.auto_trade}
                onChange={e => saveConfig({ auto_trade: e.target.checked })}
              />
              <span className={styles.slider} />
            </label>
          </div>

          {config.auto_trade && (
            <div className={styles.autoTradeControls}>
              <label className={styles.controlLabel}>
                Position size (% of portfolio)
                <div className={styles.sliderRow}>
                  <input
                    type="range" min="1" max="25" step="0.5"
                    value={config.position_pct}
                    onChange={e => setConfig(c => ({ ...c, position_pct: parseFloat(e.target.value) }))}
                    onMouseUp={() => saveConfig({})}
                  />
                  <span className={styles.sliderVal}>{config.position_pct}%</span>
                </div>
              </label>
              <label className={styles.controlLabel}>
                Max position (% of portfolio)
                <div className={styles.sliderRow}>
                  <input
                    type="range" min="5" max="50" step="1"
                    value={config.max_position_pct}
                    onChange={e => setConfig(c => ({ ...c, max_position_pct: parseFloat(e.target.value) }))}
                    onMouseUp={() => saveConfig({})}
                  />
                  <span className={styles.sliderVal}>{config.max_position_pct}%</span>
                </div>
              </label>
              <p className={styles.autoTradeNote}>
                ⚡ When ELLIE recommends BUY, it will automatically purchase {config.position_pct}% of your portfolio value in that stock.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Tabs ── */}
      <div className={styles.tabs}>
        {['positions', 'orders', 'trade'].map(t => (
          <button
            key={t}
            className={[styles.tab, tab === t && styles.tabActive].filter(Boolean).join(' ')}
            onClick={() => setTab(t)}
          >
            {t === 'positions' ? `Positions (${positions.length})` : t === 'orders' ? 'Order History' : '+ Place Order'}
          </button>
        ))}
      </div>

      {/* ── Positions ── */}
      {tab === 'positions' && (
        <div className={styles.tableWrap}>
          {positions.length === 0
            ? <div className={styles.empty}>No open positions</div>
            : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Avg Cost</th>
                    <th>Current</th>
                    <th>Market Value</th>
                    <th>Unrealized P&L</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map(p => (
                    <tr key={p.symbol}>
                      <td className={styles.symbol}>{p.symbol}</td>
                      <td>{p.qty}</td>
                      <td>{fmtD(p.avg_entry_price)}</td>
                      <td>{fmtD(p.current_price)}</td>
                      <td>{fmtD(p.market_value)}</td>
                      <td className={clr(p.unrealized_pl)}>
                        {fmtD(p.unrealized_pl)}
                        <span className={styles.subPct}> {pct(p.unrealized_plpc)}</span>
                      </td>
                      <td>
                        <button className={styles.closeBtn} onClick={() => closePosition(p.symbol)}>
                          Close
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      )}

      {/* ── Orders ── */}
      {tab === 'orders' && (
        <div className={styles.tableWrap}>
          {orders.length === 0
            ? <div className={styles.empty}>No recent orders</div>
            : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Fill Price</th>
                    <th>Status</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map(o => (
                    <tr key={o.id}>
                      <td className={styles.symbol}>{o.symbol}</td>
                      <td className={o.side === 'buy' ? styles.green : styles.red}>
                        {o.side?.toUpperCase()}
                      </td>
                      <td>{o.qty ?? '—'}</td>
                      <td>{o.filled_avg_price ? fmtD(o.filled_avg_price) : '—'}</td>
                      <td><span className={styles.statusChip}>{o.status}</span></td>
                      <td className={styles.dim}>{o.submitted_at ? new Date(o.submitted_at).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      )}

      {/* ── Manual trade ── */}
      {tab === 'trade' && (
        <div className={styles.tradeCard}>
          <div className={styles.tradeGrid}>
            <label className={styles.tradeLabel}>
              Symbol
              <input
                className={styles.tradeInput}
                value={orderSymbol}
                onChange={e => setOrderSymbol(e.target.value.toUpperCase())}
                placeholder="AAPL"
                maxLength={8}
              />
            </label>
            <label className={styles.tradeLabel}>
              Side
              <select className={styles.tradeSelect} value={orderSide} onChange={e => setOrderSide(e.target.value)}>
                <option value="buy">BUY</option>
                <option value="sell">SELL</option>
              </select>
            </label>
            <label className={styles.tradeLabel}>
              Shares
              <input
                className={styles.tradeInput}
                type="number"
                min="1"
                value={orderQty}
                onChange={e => setOrderQty(e.target.value)}
                placeholder="10"
              />
            </label>
          </div>
          <button
            className={[styles.tradeBtn, orderSide === 'sell' && styles.tradeBtnSell].filter(Boolean).join(' ')}
            onClick={submitOrder}
            disabled={orderBusy || !orderSymbol || !orderQty}
          >
            {orderBusy ? 'Submitting…' : `${orderSide.toUpperCase()} ${orderQty || ''} ${orderSymbol || 'shares'}`}
          </button>
          {orderMsg && (
            <div className={[styles.orderMsg, orderMsg.ok ? styles.orderMsgOk : styles.orderMsgErr].join(' ')}>
              {orderMsg.text}
            </div>
          )}
        </div>
      )}

    </div>
  )
}

function MetricCard({ label, value, sub, color }) {
  return (
    <div className={styles.metricCard}>
      <div className={styles.metricLabel}>{label}</div>
      <div className={[styles.metricValue, color && styles[color]].filter(Boolean).join(' ')}>{value}</div>
      {sub && <div className={styles.metricSub}>{sub}</div>}
    </div>
  )
}
