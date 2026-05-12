import { useState, useEffect, useCallback } from 'react'
import ResultPanel from '../components/ResultPanel'
import styles from './PortfolioView.module.css'

// ── Formatting helpers ────────────────────────────────────────────────────────

const SIGNAL_COLOR = {
  Buy: 'green', Overweight: 'green',
  Hold: 'yellow',
  Sell: 'red', Underweight: 'red',
  default: 'indigo',
}

const SIGNAL_LABEL = {
  Buy: 'BUY ↑', Overweight: 'BUY ↑',
  Hold: 'HOLD →',
  Sell: 'SELL ↓', Underweight: 'SELL ↓',
}

const ACTION_COLOR = {
  BUY:  'green',
  ADD:  'blue',
  SELL: 'red',
  HOLD: 'gray',
}

function fmt(n, digits = 2) {
  if (n == null) return '—'
  return Number(n).toFixed(digits)
}

function fmtPct(n) {
  if (n == null) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function fmtDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

function fmtMoney(n) {
  if (n == null) return '—'
  return `$${Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function Stat({ label, value, color }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={[styles.statValue, color && styles[`statValue_${color}`]].filter(Boolean).join(' ')}>
        {value}
      </span>
    </div>
  )
}

// ── Live Positions Tab ────────────────────────────────────────────────────────

function LivePositionsTab() {
  const [positions, setPositions] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/alpaca/positions')
      const data = await r.json()
      setPositions(Array.isArray(data) ? data : [])
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <p className={styles.empty}>Loading positions…</p>

  if (positions.length === 0) return <p className={styles.empty}>No open positions.</p>

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>SYMBOL</th>
            <th>QTY</th>
            <th>AVG COST</th>
            <th>CURRENT</th>
            <th>MARKET VALUE</th>
            <th>UNREALIZED P&L</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(p => {
            const pl = parseFloat(p.unrealized_pl || 0)
            const plPct = parseFloat(p.unrealized_plpc || 0)
            return (
              <tr key={p.symbol} className={styles.row}>
                <td className={styles.ticker}>{p.symbol}</td>
                <td>{p.qty}</td>
                <td>{fmtMoney(p.avg_entry_price)}</td>
                <td>{fmtMoney(p.current_price)}</td>
                <td>{fmtMoney(p.market_value)}</td>
                <td className={pl >= 0 ? styles.pnl_green : styles.pnl_red}>
                  {fmtMoney(pl)}
                  <span className={styles.dim}> ({fmtPct(plPct * 100)})</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Trade History Tab ─────────────────────────────────────────────────────────

function TradeHistoryTab() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/portfolio/history')
      const data = await r.json()
      setHistory(Array.isArray(data) ? data : [])
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <p className={styles.empty}>Loading trade history…</p>

  if (history.length === 0) return <p className={styles.empty}>No trade history yet.</p>

  return (
    <div className={styles.historyList}>
      {history.map((entry, i) => {
        const actionColor = ACTION_COLOR[entry.action] || 'gray'
        const isOpen = expanded === i
        return (
          <div key={i} className={styles.historyEntry}>
            <div className={styles.historyTop} onClick={() => setExpanded(isOpen ? null : i)}>
              <div className={styles.historyLeft}>
                <span className={[styles.badge, styles[`badge_${actionColor}`]].join(' ')}>
                  {entry.action}
                </span>
                <span className={styles.historyTicker}>{entry.ticker}</span>
                {entry.qty > 0 && <span className={styles.dim}>{entry.qty} shares</span>}
                {entry.price && <span className={styles.dim}>@ ${fmt(entry.price)}</span>}
                <span className={styles.dim}>signal: {entry.signal}</span>
              </div>
              <div className={styles.historyRight}>
                <span className={styles.dim}>{fmtDate(entry.ts)}</span>
                {entry.reasoning && (
                  <button className={styles.expandBtn}>{isOpen ? '▲ Hide' : '▼ Reasoning'}</button>
                )}
              </div>
            </div>
            {isOpen && entry.reasoning && (
              <div className={styles.historyReasoning}>
                <p>{entry.reasoning}</p>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Analysis Runs Tab ─────────────────────────────────────────────────────────

function AnalysisRunsTab() {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch('/portfolio')
      const data = await r.json()
      setRuns(data.runs || [])
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const deleteRun = useCallback(async (id) => {
    setDeleting(id)
    try {
      await fetch(`/portfolio/${id}`, { method: 'DELETE' })
      setRuns(prev => prev.filter(r => r.id !== id))
    } finally {
      setDeleting(null)
    }
  }, [])

  // Summary stats
  const totalRuns = runs.length
  const withPnl = runs.filter(r => r.pnl_pct != null)
  const avgPnl = withPnl.length
    ? withPnl.reduce((s, r) => s + r.pnl_pct, 0) / withPnl.length
    : null
  const wins = withPnl.filter(r => r.pnl_pct > 0).length
  const winRate = withPnl.length ? Math.round(wins / withPnl.length * 100) : null

  return (
    <>
      <div className={styles.stats}>
        <Stat label="Total Runs" value={totalRuns} />
        <Stat label="Avg P&L" value={avgPnl != null ? fmtPct(avgPnl) : '—'} color={avgPnl == null ? null : avgPnl >= 0 ? 'green' : 'red'} />
        <Stat label="Win Rate" value={winRate != null ? `${winRate}%` : '—'} color={winRate == null ? null : winRate >= 50 ? 'green' : 'red'} />
        <Stat label="Tracked" value={withPnl.length} />
      </div>

      {loading && runs.length === 0 ? (
        <p className={styles.empty}>Loading portfolio…</p>
      ) : runs.length === 0 ? (
        <p className={styles.empty}>No runs yet. Run an analysis to start tracking.</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>TICKER</th>
                <th>TRADE DATE</th>
                <th>SIGNAL</th>
                <th>ENTRY $</th>
                <th>CURRENT $</th>
                <th>P&L</th>
                <th>PROVIDER</th>
                <th>RUN AT</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {runs.map(run => {
                const color = SIGNAL_COLOR[run.signal] || 'cyan'
                const pnlColor = run.pnl_pct == null ? null : run.pnl_pct >= 0 ? 'green' : 'red'
                const isOpen = expanded === run.id
                return [
                  <tr
                    key={run.id}
                    className={[styles.row, isOpen && styles.rowOpen].filter(Boolean).join(' ')}
                    onClick={() => setExpanded(isOpen ? null : run.id)}
                  >
                    <td className={styles.ticker}>{run.ticker}</td>
                    <td>{run.trade_date}</td>
                    <td>
                      <span className={[styles.badge, styles[`badge_${color}`]].join(' ')}>
                        {SIGNAL_LABEL[run.signal] || run.signal?.toUpperCase() || '—'}
                      </span>
                    </td>
                    <td>${fmt(run.entry_price)}</td>
                    <td>{run.current_price ? `$${fmt(run.current_price)}` : '—'}</td>
                    <td className={pnlColor ? styles[`pnl_${pnlColor}`] : ''}>
                      {fmtPct(run.pnl_pct)}
                    </td>
                    <td className={styles.dim}>{run.provider || '—'}</td>
                    <td className={styles.dim}>{fmtDate(run.timestamp)}</td>
                    <td>
                      <button
                        className={styles.deleteBtn}
                        disabled={deleting === run.id}
                        onClick={e => { e.stopPropagation(); deleteRun(run.id) }}
                        title="Delete"
                      >✕</button>
                    </td>
                  </tr>,
                  isOpen && (
                    <tr key={`${run.id}-detail`} className={styles.detailRow}>
                      <td colSpan={9}>
                        <div className={styles.detailWrap}>
                          <ResultPanel decision={{
                            ticker:      run.ticker,
                            date:        run.trade_date,
                            signal:      run.signal,
                            entry_price: run.entry_price,
                            reasoning:   run.reasoning,
                          }} />
                        </div>
                      </td>
                    </tr>
                  )
                ]
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

// ── Main PortfolioView ────────────────────────────────────────────────────────

export default function PortfolioView() {
  const [tab, setTab] = useState('positions')

  const TABS = [
    { id: 'positions', label: 'Live Positions' },
    { id: 'history',   label: 'Trade History' },
    { id: 'runs',      label: 'Analysis Runs' },
  ]

  return (
    <div className={styles.wrap}>
      <div className={styles.pageHeader}>
        <div>
          <h2 className={styles.title}>Portfolio</h2>
          <p className={styles.sub}>Live positions, fund trade history, and all analysis runs</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className={styles.tabs}>
        {TABS.map(t => (
          <button
            key={t.id}
            className={[styles.tab, tab === t.id && styles.tabActive].filter(Boolean).join(' ')}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'positions' && <LivePositionsTab />}
      {tab === 'history'   && <TradeHistoryTab />}
      {tab === 'runs'      && <AnalysisRunsTab />}
    </div>
  )
}
