import { useState, useEffect, useCallback } from 'react'
import ResultPanel from '../components/ResultPanel'
import styles from './PortfolioView.module.css'

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

function fmt(n, digits = 2) {
  if (n == null) return '—'
  return n.toFixed(digits)
}

function fmtPct(n) {
  if (n == null) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

export default function PortfolioView() {
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
    <div className={styles.wrap}>
      <div className={styles.pageHeader}>
        <div>
          <h2 className={styles.title}>Portfolio Tracker</h2>
          <p className={styles.sub}>All analysis runs · prices updated live via yfinance</p>
        </div>
        <button className={styles.refreshBtn} onClick={load} disabled={loading}>
          {loading ? '↻ Loading…' : '↻ Refresh'}
        </button>
      </div>

      {/* Summary row */}
      <div className={styles.stats}>
        <Stat label="Total Runs" value={totalRuns} />
        <Stat label="Avg P&L" value={avgPnl != null ? fmtPct(avgPnl) : '—'} color={avgPnl == null ? null : avgPnl >= 0 ? 'green' : 'red'} />
        <Stat label="Win Rate" value={winRate != null ? `${winRate}%` : '—'} color={winRate == null ? null : winRate >= 50 ? 'green' : 'red'} />
        <Stat label="Tracked" value={withPnl.length} />
      </div>

      {/* Table */}
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
    </div>
  )
}

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
