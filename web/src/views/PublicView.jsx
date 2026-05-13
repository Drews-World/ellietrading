import { useState, useEffect, useCallback } from 'react'
import styles from './PublicView.module.css'

function fmtMoney(n) {
  if (n == null) return '—'
  return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n) {
  if (n == null) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${Number(n).toFixed(2)}%`
}

function timeAgo(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function PublicView({ onLoginClick }) {
  const [account, setAccount]     = useState(null)
  const [positions, setPositions] = useState([])
  const [activity, setActivity]   = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)

  const load = useCallback(async () => {
    try {
      const [accRes, posRes, logRes] = await Promise.all([
        fetch('/alpaca/account'),
        fetch('/alpaca/positions'),
        fetch('/fund/log'),
      ])
      if (!accRes.ok || !posRes.ok) throw new Error('Failed to load portfolio')
      const acc = await accRes.json()
      const pos = await posRes.json()
      const log = logRes.ok ? await logRes.json() : []

      setAccount(acc)
      setPositions(Array.isArray(pos) ? pos : [])

      // Filter log to buy/sell activity only
      const keywords = /\b(bought|sold|sell|buy|purchased|added|closed|position)\b/i
      const acts = (Array.isArray(log) ? log : [])
        .filter(e => keywords.test(e.msg || ''))
        .slice(0, 8)
      setActivity(acts)
      setError(null)
    } catch (e) {
      setError('Could not load portfolio data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const iv = setInterval(load, 5 * 60 * 1000)
    return () => clearInterval(iv)
  }, [load])

  const equity    = account ? parseFloat(account.equity    || 0) : null
  const cash      = account ? parseFloat(account.cash      || 0) : null
  const dayPnl    = account ? parseFloat(account.pnl_today || 0) : null
  const dayPnlPct = account ? parseFloat(account.pnl_today_pct || 0) : null

  return (
    <div className={styles.page}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.logo}>
            <span className={styles.logoIcon}>◈</span>
            <span className={styles.logoText}>ELLIE</span>
          </div>
          <span className={styles.tagline}>AI Hedge Fund · Live Portfolio</span>
        </div>
        <button className={styles.loginBtn} onClick={onLoginClick} title="Owner login">
          🔐
        </button>
      </header>

      <div className={styles.content}>
        {loading ? (
          <div className={styles.loading}>Loading portfolio…</div>
        ) : error ? (
          <div className={styles.error}>{error}</div>
        ) : (
          <>
            {/* Top metric cards */}
            <div className={styles.metrics}>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Portfolio Value</span>
                <span className={styles.metricValue}>{fmtMoney(equity)}</span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Today's P&amp;L</span>
                <span className={[
                  styles.metricValue,
                  dayPnl >= 0 ? styles.green : styles.red,
                ].join(' ')}>
                  {fmtMoney(dayPnl)}
                  <span className={styles.metricSub}>{fmtPct(dayPnlPct)}</span>
                </span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Cash Available</span>
                <span className={styles.metricValue}>{fmtMoney(cash)}</span>
              </div>
              <div className={styles.metricCard}>
                <span className={styles.metricLabel}>Positions</span>
                <span className={styles.metricValue}>{positions.length}</span>
              </div>
            </div>

            {/* Positions */}
            <section className={styles.section}>
              <h2 className={styles.sectionTitle}>Open Positions</h2>
              {positions.length === 0 ? (
                <p className={styles.empty}>No open positions.</p>
              ) : (
                <div className={styles.positionList}>
                  {positions.map(pos => {
                    const unrlPct = parseFloat(pos.unrealized_plpc || 0) * 100
                    const unrl    = parseFloat(pos.unrealized_pl   || 0)
                    const mktVal  = parseFloat(pos.market_value    || 0)
                    const isUp    = unrlPct >= 0
                    // Bar width as % of max position (capped at 100%)
                    const maxVal  = Math.max(...positions.map(p => parseFloat(p.market_value || 0)))
                    const barPct  = maxVal > 0 ? (mktVal / maxVal) * 100 : 0

                    return (
                      <div key={pos.symbol} className={styles.positionRow}>
                        <div className={styles.positionTop}>
                          <span className={styles.positionSymbol}>{pos.symbol}</span>
                          <span className={styles.positionQty}>{pos.qty} shares</span>
                          <span className={styles.positionValue}>{fmtMoney(mktVal)}</span>
                          <span className={[styles.positionPnl, isUp ? styles.green : styles.red].join(' ')}>
                            {fmtMoney(unrl)} ({fmtPct(unrlPct)})
                          </span>
                        </div>
                        <div className={styles.barTrack}>
                          <div
                            className={[styles.barFill, isUp ? styles.barGreen : styles.barRed].join(' ')}
                            style={{ width: `${barPct}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </section>

            {/* Recent activity */}
            {activity.length > 0 && (
              <section className={styles.section}>
                <h2 className={styles.sectionTitle}>Recent Activity</h2>
                <div className={styles.activityList}>
                  {activity.map((entry, i) => (
                    <div key={i} className={styles.activityRow}>
                      <span className={styles.activityMsg}>{entry.msg}</span>
                      <span className={styles.activityTs}>{timeAgo(entry.ts)}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>

      <footer className={styles.footer}>
        Managed autonomously by ELLIE · Updated every 5 min · Read-only view
      </footer>
    </div>
  )
}
