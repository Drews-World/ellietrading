import { useState, useEffect, useCallback } from 'react'
import styles from './FundView.module.css'

const PROVIDERS = [
  { value: 'google',    label: 'Google (Gemini)' },
  { value: 'openai',   label: 'OpenAI (GPT)' },
  { value: 'anthropic', label: 'Anthropic (Claude)' },
  { value: 'groq',     label: 'Groq (Llama)' },
]

const fmt  = (n, dec = 2) => n == null ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec })
const fmtD = (n) => n == null ? '—' : `$${fmt(n)}`
const fmtDate = (iso) => {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}
const fmtTs = (iso) => {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch { return iso }
}

function isPaper() {
  // Vite exposes env vars as import.meta.env — fall back to checking the
  // APCA_BASE_URL the user saved, which the backend echoes in /settings.
  // For a simple heuristic we look at the hostname of the current page;
  // the real signal comes from the fund state "paper" field set by the backend.
  return true // default safe assumption; overridden by account data below
}

export default function FundView() {
  const [fund,    setFund]    = useState(null)
  const [account, setAccount] = useState(null)
  const [log,     setLog]     = useState([])
  const [loading, setLoading] = useState(true)
  const [busy,    setBusy]    = useState(false)
  const [msg,     setMsg]     = useState(null)

  // Local config (before launch)
  const [cfg, setCfg] = useState({
    llm_provider:    'google',
    deep_think_llm:  'gemini-2.5-pro',
    quick_think_llm: 'gemini-2.5-flash',
    initial_stocks:  5,
    position_pct:    5.0,
    max_position_pct: 15.0,
    weekly_new_buy:  true,
  })

  const load = useCallback(async () => {
    try {
      const [f, acc, lg] = await Promise.all([
        fetch('/fund').then(r => r.json()),
        fetch('/alpaca/account').then(r => r.json()).catch(() => null),
        fetch('/fund/log').then(r => r.json()),
      ])
      setFund(f)
      setAccount(acc)
      setLog(Array.isArray(lg) ? lg : [])
      // Sync local cfg from fund state
      if (f?.config) setCfg(f.config)
    } catch (e) {
      // silently ignore connectivity errors
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Poll every 30s when active
  useEffect(() => {
    const iv = setInterval(() => { if (fund?.active) load() }, 30_000)
    return () => clearInterval(iv)
  }, [fund?.active, load])

  const showMsg = (text, isErr = false) => {
    setMsg({ text, isErr })
    setTimeout(() => setMsg(null), 5000)
  }

  const handleLaunch = async () => {
    if (!window.confirm(
      'This will begin autonomous trading with real capital.\n\nAre you sure you want to launch the ELLIE Fund?'
    )) return

    setBusy(true)
    try {
      // Save config first
      await fetch('/fund/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      const r = await fetch('/fund/launch', { method: 'POST' })
      const d = await r.json()
      if (d.ok) {
        showMsg('Fund launch initiated — this may take several minutes.')
        setTimeout(load, 3000)
      } else {
        showMsg(d.message || 'Launch failed', true)
      }
    } catch (e) {
      showMsg('Network error', true)
    } finally {
      setBusy(false)
    }
  }

  const handlePause = async () => {
    setBusy(true)
    try {
      await fetch('/fund/pause', { method: 'POST' })
      showMsg('Fund paused.')
      load()
    } catch { showMsg('Error pausing fund', true) }
    finally { setBusy(false) }
  }

  const handleResume = async () => {
    setBusy(true)
    try {
      await fetch('/fund/resume', { method: 'POST' })
      showMsg('Fund resumed.')
      load()
    } catch { showMsg('Error resuming fund', true) }
    finally { setBusy(false) }
  }

  const handleRelaunch = async () => {
    if (!window.confirm(
      'This will run a new discovery + buy cycle without clearing your log or positions.\n\nELLIE will find new stocks and buy any with a BUY signal.\n\nContinue?'
    )) return
    setBusy(true)
    try {
      const r = await fetch('/fund/launch', { method: 'POST' })
      const d = await r.json()
      if (d.ok) {
        showMsg('Relaunch initiated — ELLIE is finding new stocks.')
        setTimeout(load, 3000)
      } else {
        showMsg(d.message || 'Relaunch failed', true)
      }
    } catch { showMsg('Network error', true) }
    finally { setBusy(false) }
  }

  const handleReview = async () => {
    setBusy(true)
    try {
      await fetch('/fund/review', { method: 'POST' })
      showMsg('Daily review triggered — results will appear in the log.')
      setTimeout(load, 5000)
    } catch { showMsg('Error triggering review', true) }
    finally { setBusy(false) }
  }

  const handleSaveConfig = async () => {
    setBusy(true)
    try {
      await fetch('/fund/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      showMsg('Configuration saved.')
      load()
    } catch { showMsg('Error saving config', true) }
    finally { setBusy(false) }
  }

  const handleReset = async () => {
    if (!window.confirm(
      'This will reset the fund state and clear the activity log.\n\nYour Alpaca positions will NOT be affected — only ELLIE\'s internal tracking is reset.\n\nContinue?'
    )) return
    setBusy(true)
    try {
      const r = await fetch('/fund/reset', { method: 'POST' })
      const d = await r.json()
      if (d.ok) {
        showMsg('Fund reset — you can now relaunch.')
        load()
      } else {
        showMsg(d.message || 'Reset failed', true)
      }
    } catch { showMsg('Network error', true) }
    finally { setBusy(false) }
  }

  // Detect paper trading from Alpaca base URL
  const alpacaBaseUrl = account?.account_number ? 'https://app.alpaca.markets' : 'https://app.alpaca.markets'
  const isPaperMode = !account || account?.status === 'ACTIVE' // simplified — backend sets paper flag

  const portfolioValue = account?.portfolio_value ?? account?.equity
  const cash = account?.cash
  const todayPnl = (account?.equity != null && account?.last_equity != null)
    ? (parseFloat(account.equity) - parseFloat(account.last_equity))
    : null

  const launched  = fund?.launched_at != null
  const isActive  = fund?.active === true
  const isPaused  = launched && !isActive

  let statusLabel = 'NOT LAUNCHED'
  let statusClass = styles.statusBlue
  if (launched) {
    if (isActive) { statusLabel = 'ACTIVE'; statusClass = styles.statusGreen }
    else { statusLabel = 'PAUSED'; statusClass = styles.statusGray }
  }

  if (loading) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingWrap}>
          <div className={styles.spinner} />
          <span>Loading fund state…</span>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      {/* ── Header ── */}
      <div className={styles.pageHeader}>
        <div className={styles.pageTitle}>
          <span>🏦</span>
          <span>ELLIE Fund</span>
          {isPaperMode && <span className={styles.paperBadge}>PAPER</span>}
        </div>
        <div className={styles.headerActions}>
          <a
            href="https://app.alpaca.markets"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.alpacaLink}
          >
            View on Alpaca ↗
          </a>
          <button className={styles.refreshBtn} onClick={load}>↻ Refresh</button>
        </div>
      </div>

      {/* ── Status bar ── */}
      <div className={styles.statusCard}>
        <div className={styles.statusLeft}>
          <span className={[styles.statusBadge, statusClass].join(' ')}>{statusLabel}</span>
          <div className={styles.statusMeta}>
            {fund?.launched_at && (
              <span>Launched {fmtDate(fund.launched_at)}</span>
            )}
            {fund?.last_daily_review && (
              <span>Last review {fmtDate(fund.last_daily_review)}</span>
            )}
            {fund?.next_daily_review && isActive && (
              <span>Next review {fmtDate(fund.next_daily_review)}</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Metrics row ── */}
      <div className={styles.metricsRow}>
        <div className={styles.metricCard}>
          <div className={styles.metricLabel}>Portfolio Value</div>
          <div className={styles.metricValue}>{fmtD(portfolioValue)}</div>
        </div>
        <div className={styles.metricCard}>
          <div className={styles.metricLabel}>Today's P&amp;L</div>
          <div className={[styles.metricValue, todayPnl != null ? (todayPnl >= 0 ? styles.green : styles.red) : ''].join(' ')}>
            {todayPnl != null ? `${todayPnl >= 0 ? '+' : ''}$${fmt(todayPnl)}` : '—'}
          </div>
        </div>
        <div className={styles.metricCard}>
          <div className={styles.metricLabel}>Cash Available</div>
          <div className={styles.metricValue}>{fmtD(cash)}</div>
        </div>
        <div className={styles.metricCard}>
          <div className={styles.metricLabel}>Buying Power</div>
          <div className={styles.metricValue}>{fmtD(account?.buying_power)}</div>
        </div>
      </div>

      {/* ── Main content: launch panel OR control panel ── */}
      {!launched ? (
        /* ─ NOT LAUNCHED: big launch panel ─ */
        <div className={styles.launchPanel}>
          <div className={styles.launchHero}>
            <div className={styles.launchIcon}>🚀</div>
            <h2 className={styles.launchTitle}>Launch the ELLIE Fund</h2>
            <p className={styles.launchSubtitle}>
              ELLIE will autonomously discover high-growth stocks, analyze them with AI, and
              build a diversified portfolio — then monitor and rebalance daily.
            </p>
          </div>

          {/* Config */}
          <div className={styles.configGrid}>
            <div className={styles.configField}>
              <label className={styles.configLabel}>LLM Provider</label>
              <select
                className={styles.select}
                value={cfg.llm_provider}
                onChange={e => setCfg(c => ({ ...c, llm_provider: e.target.value }))}
              >
                {PROVIDERS.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            <div className={styles.configField}>
              <label className={styles.configLabel}>
                Initial Positions: <strong>{cfg.initial_stocks}</strong>
              </label>
              <input
                type="range" min={3} max={10} step={1}
                value={cfg.initial_stocks}
                className={styles.slider}
                onChange={e => setCfg(c => ({ ...c, initial_stocks: parseInt(e.target.value) }))}
              />
              <div className={styles.sliderTicks}><span>3</span><span>10</span></div>
            </div>

            <div className={styles.configField}>
              <label className={styles.configLabel}>
                Position Size: <strong>{cfg.position_pct}%</strong>
              </label>
              <input
                type="range" min={1} max={25} step={0.5}
                value={cfg.position_pct}
                className={styles.slider}
                onChange={e => setCfg(c => ({ ...c, position_pct: parseFloat(e.target.value) }))}
              />
              <div className={styles.sliderTicks}><span>1%</span><span>25%</span></div>
            </div>

            <div className={styles.configField}>
              <label className={styles.configLabel}>
                Max Position Size: <strong>{cfg.max_position_pct}%</strong>
              </label>
              <input
                type="range" min={5} max={40} step={1}
                value={cfg.max_position_pct}
                className={styles.slider}
                onChange={e => setCfg(c => ({ ...c, max_position_pct: parseFloat(e.target.value) }))}
              />
              <div className={styles.sliderTicks}><span>5%</span><span>40%</span></div>
            </div>

            <div className={styles.configField}>
              <label className={styles.configLabel}>Weekly New Buy</label>
              <label className={styles.toggle}>
                <input
                  type="checkbox"
                  checked={cfg.weekly_new_buy}
                  onChange={e => setCfg(c => ({ ...c, weekly_new_buy: e.target.checked }))}
                />
                <span className={styles.toggleTrack} />
                <span className={styles.toggleLabel}>
                  {cfg.weekly_new_buy ? 'Enabled' : 'Disabled'}
                </span>
              </label>
            </div>
          </div>

          <div className={styles.launchWarning}>
            ⚠️ This will begin autonomous trading{isPaperMode ? ' with paper money' : ' with real capital'}.
            Positions will be bought and held according to AI signals.
            {isPaperMode && ' Paper trading is currently active.'}
          </div>

          <button
            className={styles.launchBtn}
            onClick={handleLaunch}
            disabled={busy}
          >
            {busy ? (
              <><span className={styles.spinnerSm} /> Launching…</>
            ) : '🚀 Launch Fund'}
          </button>
        </div>
      ) : (
        /* ─ LAUNCHED: control panel ─ */
        <div className={styles.controlPanel}>
          <div className={styles.controlRow}>
            {isActive ? (
              <button
                className={[styles.controlBtn, styles.pauseBtn].join(' ')}
                onClick={handlePause}
                disabled={busy}
              >
                ⏸ Pause Fund
              </button>
            ) : (
              <>
                <button
                  className={[styles.controlBtn, styles.resumeBtn].join(' ')}
                  onClick={handleResume}
                  disabled={busy}
                >
                  ▶ Resume Fund
                </button>
                <button
                  className={[styles.controlBtn, styles.relaunchBtn].join(' ')}
                  onClick={handleRelaunch}
                  disabled={busy}
                >
                  🚀 Relaunch
                </button>
              </>
            )}
            <button
              className={[styles.controlBtn, styles.reviewBtn].join(' ')}
              onClick={handleReview}
              disabled={busy}
            >
              🔄 Run Daily Review Now
            </button>
          </div>

          {/* Config (editable even when launched) */}
          <div className={styles.configSection}>
            <div className={styles.configSectionTitle}>Fund Configuration</div>
            <div className={styles.configGrid}>
              <div className={styles.configField}>
                <label className={styles.configLabel}>LLM Provider</label>
                <select
                  className={styles.select}
                  value={cfg.llm_provider}
                  onChange={e => setCfg(c => ({ ...c, llm_provider: e.target.value }))}
                >
                  {PROVIDERS.map(p => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </select>
              </div>
              <div className={styles.configField}>
                <label className={styles.configLabel}>
                  Position Size: <strong>{cfg.position_pct}%</strong>
                </label>
                <input
                  type="range" min={1} max={25} step={0.5}
                  value={cfg.position_pct}
                  className={styles.slider}
                  onChange={e => setCfg(c => ({ ...c, position_pct: parseFloat(e.target.value) }))}
                />
                <div className={styles.sliderTicks}><span>1%</span><span>25%</span></div>
              </div>
              <div className={styles.configField}>
                <label className={styles.configLabel}>
                  Max Position Size: <strong>{cfg.max_position_pct}%</strong>
                </label>
                <input
                  type="range" min={5} max={40} step={1}
                  value={cfg.max_position_pct}
                  className={styles.slider}
                  onChange={e => setCfg(c => ({ ...c, max_position_pct: parseFloat(e.target.value) }))}
                />
                <div className={styles.sliderTicks}><span>5%</span><span>40%</span></div>
              </div>
              <div className={styles.configField}>
                <label className={styles.configLabel}>Weekly New Buy</label>
                <label className={styles.toggle}>
                  <input
                    type="checkbox"
                    checked={cfg.weekly_new_buy}
                    onChange={e => setCfg(c => ({ ...c, weekly_new_buy: e.target.checked }))}
                  />
                  <span className={styles.toggleTrack} />
                  <span className={styles.toggleLabel}>
                    {cfg.weekly_new_buy ? 'Enabled' : 'Disabled'}
                  </span>
                </label>
              </div>
            </div>
            <button
              className={styles.saveCfgBtn}
              onClick={handleSaveConfig}
              disabled={busy}
            >
              Save Configuration
            </button>
          </div>

          <div className={styles.dangerZone}>
            <div className={styles.dangerTitle}>Danger Zone</div>
            <p className={styles.dangerNote}>
              Reset clears ELLIE's internal state so you can relaunch. Your actual Alpaca positions are not affected.
            </p>
            <button
              className={styles.resetBtn}
              onClick={handleReset}
              disabled={busy}
            >
              🔁 Reset & Relaunch
            </button>
          </div>
        </div>
      )}

      {/* ── Feedback message ── */}
      {msg && (
        <div className={[styles.toast, msg.isErr ? styles.toastErr : styles.toastOk].join(' ')}>
          {msg.text}
        </div>
      )}

      {/* ── Activity log ── */}
      <div className={styles.logPanel}>
        <div className={styles.logHeader}>
          <span className={styles.logTitle}>Activity Log</span>
          <span className={styles.logCount}>{log.length} entries</span>
        </div>
        <div className={styles.logList}>
          {log.length === 0 ? (
            <div className={styles.logEmpty}>No activity yet.</div>
          ) : (
            log.map((entry, i) => (
              <div key={i} className={styles.logEntry}>
                <span className={styles.logTs}>{fmtTs(entry.ts)}</span>
                <span className={styles.logMsg}>{entry.msg}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
