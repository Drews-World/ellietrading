import { useState, useEffect, useCallback, useRef } from 'react'
import styles from './MonitorView.module.css'

const SIGNAL_COLOR = {
  Buy: 'green', Overweight: 'green',
  Hold: 'yellow',
  Sell: 'red', Underweight: 'red',
}

const SIGNAL_PLAIN = {
  Buy: 'BUY ↑', Overweight: 'BUY ↑',
  Hold: 'HOLD →',
  Sell: 'SELL ↓', Underweight: 'SELL ↓',
}

const INTERVAL_OPTIONS = [
  { value: 4,   label: 'Every 4 hours' },
  { value: 8,   label: 'Every 8 hours' },
  { value: 12,  label: 'Every 12 hours' },
  { value: 24,  label: 'Daily' },
  { value: 72,  label: 'Every 3 days' },
  { value: 168, label: 'Weekly' },
]

function timeAgo(isoStr) {
  if (!isoStr) return '—'
  const diff = Date.now() - new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z')).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function timeUntil(isoStr) {
  if (!isoStr) return '—'
  const diff = new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z')).getTime() - Date.now()
  if (diff <= 0) return 'soon'
  const m = Math.ceil(diff / 60000)
  if (m < 60) return `in ${m}m`
  return `in ${Math.ceil(m / 60)}h`
}

// More precise countdown: "21h 14m", "3d 4h", "overdue"
function countdown(isoStr) {
  if (!isoStr) return '—'
  const diff = new Date(isoStr + (isoStr.endsWith('Z') ? '' : 'Z')).getTime() - Date.now()
  if (diff <= 0) return 'overdue'
  const totalMins = Math.floor(diff / 60000)
  const h = Math.floor(totalMins / 60)
  const m = totalMins % 60
  if (h === 0) return `${m}m`
  if (h < 24) return `${h}h ${m}m`
  const d = Math.floor(h / 24)
  const rh = h % 24
  return `${d}d ${rh}h`
}

function FundAutomations({ fund, onRunReview }) {
  const [reviewing, setReviewing] = useState(false)
  // Tick every 60s so countdowns stay live
  const [, setTick] = useState(0)
  useEffect(() => {
    const iv = setInterval(() => setTick(t => t + 1), 60000)
    return () => clearInterval(iv)
  }, [])

  const isActive = fund?.active
  const weeklyBuyEnabled = fund?.config?.weekly_new_buy ?? true

  const handleRunReview = async () => {
    setReviewing(true)
    try {
      await fetch('/fund/review', { method: 'POST' })
      onRunReview()
    } finally {
      setReviewing(false)
    }
  }

  return (
    <div className={styles.section}>
      <div className={styles.sectionHeader}>
        <span className={styles.sectionTitle}>Fund Automations</span>
        <span className={isActive ? styles.statusActive : styles.statusInactive}>
          {isActive ? '● Monitoring' : '○ Inactive'}
        </span>
      </div>
      {!isActive ? (
        <p className={styles.empty}>Fund is not active — launch the fund from the Fund tab to enable automated monitoring.</p>
      ) : (
        <div className={styles.scheduleGrid}>
          {/* Daily Snapshot */}
          <div className={styles.scheduleCard}>
            <span className={styles.scheduleLabel}>DAILY SNAPSHOT</span>
            <span className={styles.scheduleCountdown}>
              {countdown(fund?.next_daily_review)}
            </span>
            <div className={styles.scheduleMeta}>
              <span>Portfolio P&amp;L snapshot sent to Discord at market close. No AI, no trades.</span>
            </div>
            <div className={styles.scheduleTimes}>
              <span>Last: {timeAgo(fund?.last_daily_review)}</span>
              <span>Next: {fund?.next_daily_review
                ? new Date(fund.next_daily_review).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                : '—'}</span>
            </div>
            <button
              className={styles.runBtn}
              onClick={handleRunReview}
              disabled={reviewing}
            >
              {reviewing ? 'Running…' : '▶ Run Now'}
            </button>
          </div>

          {/* Bi-Weekly Analysis */}
          <div className={styles.scheduleCard}>
            <span className={styles.scheduleLabel}>BI-WEEKLY ANALYSIS</span>
            <span className={styles.scheduleCountdown}>
              {countdown(fund?.next_biweekly_analysis)}
            </span>
            <div className={styles.scheduleMeta}>
              <span>AI reviews every held position. Sells weak signals, adds to strong ones. Respects the {fund?.config?.min_hold_days ?? 14}-day hold minimum.</span>
            </div>
            <div className={styles.scheduleTimes}>
              <span>Last: {timeAgo(fund?.last_biweekly_analysis)}</span>
              <span>Next: {fund?.next_biweekly_analysis
                ? new Date(fund.next_biweekly_analysis).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                : '—'}</span>
            </div>
          </div>

          {/* Weekly Report */}
          <div className={styles.scheduleCard}>
            <span className={styles.scheduleLabel}>WEEKLY REPORT</span>
            <span className={styles.scheduleCountdown}>
              {countdown(fund?.next_weekly_report)}
            </span>
            <div className={styles.scheduleMeta}>
              <span>Performance summary + P&amp;L sent to Discord every Sunday.</span>
              {weeklyBuyEnabled && (
                <span className={styles.weeklyBuyTag}>+ New Buy</span>
              )}
            </div>
            <div className={styles.scheduleTimes}>
              <span>Last: {timeAgo(fund?.last_weekly_report)}</span>
              <span>Next: {fund?.next_weekly_report
                ? new Date(fund.next_weekly_report).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                : '—'}</span>
            </div>
            {weeklyBuyEnabled && (
              <div className={styles.weeklyBuyNote}>
                Will discover &amp; buy 1 new position alongside the report.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function MonitorView() {
  const [data, setData] = useState({ monitors: [], alerts: [] })
  const [fund, setFund] = useState(null)
  const [discordConfigured, setDiscordConfigured] = useState(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null) // 'ok' | 'fail'
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    ticker: '',
    interval_hours: 24,
    llm_provider: 'google',
    deep_think_llm: 'gemini-2.5-pro',
    quick_think_llm: 'gemini-2.5-flash',
  })
  const [adding, setAdding] = useState(false)
  const [running, setRunning] = useState({})
  const prevAlertIds = useRef(new Set())

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const [monRes, fundRes, settingsRes] = await Promise.all([
        fetch('/monitor'),
        fetch('/fund'),
        fetch('/settings'),
      ])
      const d = await monRes.json()
      const f = await fundRes.json()
      const s = await settingsRes.json()
      prevAlertIds.current = new Set((d.alerts || []).map(a => a.id))
      setData(d)
      setFund(f)
      setDiscordConfigured(s?.DISCORD_WEBHOOK_URL?.set ?? false)
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const iv = setInterval(() => load(true), 30000)
    return () => clearInterval(iv)
  }, [load])

  const handleTestDiscord = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await fetch('/discord/test', { method: 'POST' })
      setTestResult(r.ok ? 'ok' : 'fail')
    } catch {
      setTestResult('fail')
    } finally {
      setTesting(false)
      setTimeout(() => setTestResult(null), 4000)
    }
  }

  const handleAdd = async () => {
    if (!form.ticker.trim()) return
    setAdding(true)
    try {
      await fetch('/monitor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, ticker: form.ticker.trim().toUpperCase() }),
      })
      setShowForm(false)
      setForm({ ticker: '', interval_hours: 24, llm_provider: 'google', deep_think_llm: 'gemini-2.5-pro', quick_think_llm: 'gemini-2.5-flash' })
      await load()
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (id) => {
    await fetch(`/monitor/${id}`, { method: 'DELETE' })
    setData(prev => ({ ...prev, monitors: prev.monitors.filter(m => m.id !== id) }))
  }

  const handleRunNow = async (id) => {
    setRunning(prev => ({ ...prev, [id]: true }))
    try {
      await fetch(`/monitor/${id}/run`, { method: 'POST' })
      await load(true)
    } finally {
      setRunning(prev => ({ ...prev, [id]: false }))
    }
  }

  const markAllRead = async () => {
    await fetch('/monitor/alerts/read-all', { method: 'POST' })
    setData(prev => ({ ...prev, alerts: prev.alerts.map(a => ({ ...a, read: true })) }))
  }

  const unread = data.alerts.filter(a => !a.read).length

  return (
    <div className={styles.wrap}>
      <div className={styles.pageHeader}>
        <div>
          <h2 className={styles.title}>Monitor</h2>
          <p className={styles.sub}>
            Auto-analyzes your watchlist on a schedule and alerts you when signals change.
            Each run costs ~the same as a manual analysis.
          </p>
        </div>
        <div className={styles.headerActions}>
          {discordConfigured === false ? (
            <span className={styles.discordOff}>⚠ No Discord webhook — configure in Settings</span>
          ) : discordConfigured === true ? (
            <button
              className={testResult === 'ok' ? styles.discordOk : testResult === 'fail' ? styles.discordFail : styles.discordBtn}
              onClick={handleTestDiscord}
              disabled={testing}
            >
              {testing ? 'Sending…' : testResult === 'ok' ? '✓ Sent' : testResult === 'fail' ? '✕ Failed' : '● Discord · Test'}
            </button>
          ) : null}
          <button className={styles.addBtn} onClick={() => setShowForm(s => !s)}>
            {showForm ? '✕ Cancel' : '+ Watch Ticker'}
          </button>
        </div>
      </div>

      <FundAutomations fund={fund} onRunReview={() => load(true)} />

      {showForm && (
        <div className={styles.formCard}>
          <div className={styles.formGrid}>
            <div className={styles.field}>
              <label className={styles.label}>TICKER</label>
              <input
                className={styles.input}
                value={form.ticker}
                onChange={e => setForm(p => ({ ...p, ticker: e.target.value.toUpperCase() }))}
                placeholder="NVDA"
                maxLength={10}
                autoFocus
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>CHECK EVERY</label>
              <select
                className={styles.select}
                value={form.interval_hours}
                onChange={e => setForm(p => ({ ...p, interval_hours: Number(e.target.value) }))}
              >
                {INTERVAL_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>
          <p className={styles.formNote}>
            Uses your current Google / Gemini settings. First analysis runs within 5 minutes of adding.
          </p>
          <button
            className={styles.submitBtn}
            onClick={handleAdd}
            disabled={adding || !form.ticker.trim()}
          >
            {adding ? 'Adding…' : 'Start Monitoring'}
          </button>
        </div>
      )}

      {data.alerts.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <span className={styles.sectionTitle}>
              Alerts
              {unread > 0 && <span className={styles.badge}>{unread} new</span>}
            </span>
            {unread > 0 && (
              <button className={styles.textBtn} onClick={markAllRead}>Mark all read</button>
            )}
          </div>
          <div className={styles.alertList}>
            {data.alerts.slice(0, 20).map(alert => {
              const color = SIGNAL_COLOR[alert.signal] || 'indigo'
              return (
                <div
                  key={alert.id}
                  className={[styles.alertRow, !alert.read && styles.alertUnread].filter(Boolean).join(' ')}
                >
                  <span className={[styles.dot, styles[`dot_${color}`]].join(' ')} />
                  <div className={styles.alertBody}>
                    <span className={styles.alertTicker}>{alert.ticker}</span>
                    <span className={styles.alertMsg}>{alert.message}</span>
                    {alert.price != null && (
                      <span className={styles.alertPrice}>${alert.price.toFixed(2)}</span>
                    )}
                  </div>
                  <span className={styles.alertTs}>{timeAgo(alert.ts)}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionTitle}>Watchlist</span>
          <button className={styles.textBtn} onClick={() => load(true)}>↻ Refresh</button>
        </div>
        {loading && data.monitors.length === 0 ? (
          <p className={styles.empty}>Loading…</p>
        ) : data.monitors.length === 0 ? (
          <p className={styles.empty}>No tickers monitored yet. Click "+ Watch Ticker" to add your first.</p>
        ) : (
          <div className={styles.cardGrid}>
            {data.monitors.map(m => {
              const color = SIGNAL_COLOR[m.last_signal] || 'indigo'
              const isRunning = m.is_running || running[m.id]
              return (
                <div key={m.id} className={styles.card}>
                  <div className={styles.cardTop}>
                    <span className={styles.cardTicker}>{m.ticker}</span>
                    {m.last_signal ? (
                      <span className={[styles.signalBadge, styles[`badge_${color}`]].join(' ')}>
                        {SIGNAL_PLAIN[m.last_signal] || m.last_signal}
                      </span>
                    ) : isRunning ? (
                      <span className={styles.runningBadge}>Analyzing…</span>
                    ) : (
                      <span className={styles.pendingBadge}>Pending</span>
                    )}
                  </div>

                  <div className={styles.cardMeta}>
                    {m.last_price != null && <span>${m.last_price.toFixed(2)}</span>}
                    <span>Checked {timeAgo(m.last_checked_at)}</span>
                    <span>Next {isRunning ? '(running…)' : timeUntil(m.next_check_at)}</span>
                    <span>
                      {m.interval_hours % 24 === 0
                        ? `Every ${m.interval_hours / 24}d`
                        : `Every ${m.interval_hours}h`}
                    </span>
                  </div>

                  {m.last_error && (
                    <p className={styles.cardError}>⚠ {m.last_error}</p>
                  )}

                  <div className={styles.cardActions}>
                    <button
                      className={styles.runBtn}
                      onClick={() => handleRunNow(m.id)}
                      disabled={isRunning}
                    >
                      {isRunning ? 'Running…' : '▶ Check Now'}
                    </button>
                    <button className={styles.deleteBtn} onClick={() => handleDelete(m.id)}>
                      ✕ Remove
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
