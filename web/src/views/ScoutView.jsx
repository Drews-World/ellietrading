import { useState, useEffect, useCallback } from 'react'
import styles from './ScoutView.module.css'

const INTERVALS = [
  { value: 6,   label: 'Every 6 hours' },
  { value: 12,  label: 'Every 12 hours' },
  { value: 24,  label: 'Every day' },
  { value: 48,  label: 'Every 2 days' },
  { value: 168, label: 'Every week' },
]

const PROVIDERS = [
  { value: 'google',    label: 'Google (Gemini)' },
  { value: 'openai',   label: 'OpenAI (GPT)' },
  { value: 'anthropic', label: 'Anthropic (Claude)' },
  { value: 'groq',     label: 'Groq (Llama)' },
]

function fmtDate(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
  catch { return iso }
}

export default function ScoutView() {
  const [scout, setScout]         = useState(null)
  const [localCfg, setLocalCfg]   = useState(null)
  const [saving, setSaving]       = useState(false)
  const [savedMsg, setSavedMsg]   = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await fetch('/scout')
      const d = await r.json()
      setScout(d)
      setLocalCfg(prev => prev ?? d.config)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { load() }, [load])

  // Poll every 5s while a scan is running
  useEffect(() => {
    if (!scout?.is_running) return
    const iv = setInterval(load, 5000)
    return () => clearInterval(iv)
  }, [scout?.is_running, load])

  const saveConfig = async (cfg) => {
    setSaving(true)
    try {
      const r = await fetch('/scout/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cfg),
      })
      const d = await r.json()
      setScout(d)
      setLocalCfg(d.config)
      setSavedMsg(true)
      setTimeout(() => setSavedMsg(false), 2500)
    } catch { /* ignore */ } finally {
      setSaving(false)
    }
  }

  const toggleEnabled = () => {
    const next = { ...localCfg, enabled: !localCfg.enabled }
    setLocalCfg(next)
    saveConfig(next)
  }

  const runNow = async () => {
    await fetch('/scout/run', { method: 'POST' })
    setScout(prev => ({ ...prev, is_running: true }))
  }

  const dismiss = async (id) => {
    await fetch(`/scout/recommendations/${id}`, { method: 'DELETE' })
    setScout(prev => ({
      ...prev,
      recommendations: prev.recommendations.filter(r => r.id !== id),
    }))
  }

  if (!scout || !localCfg) return <div className={styles.loading}>Loading…</div>

  const { is_running, last_run, next_run, recommendations, last_error } = scout
  const enabled = localCfg.enabled

  return (
    <div className={styles.wrap}>
      {/* Header */}
      <div className={styles.pageHeader}>
        <div>
          <h2 className={styles.title}>Market Scout</h2>
          <p className={styles.sub}>
            Autonomous AI agent that discovers stocks, runs full analysis, and surfaces BUY signals
          </p>
        </div>
        <div className={styles.headerRight}>
          {is_running && <span className={styles.runningPill}>🔄 Scanning…</span>}
          <button className={styles.runBtn} onClick={runNow} disabled={is_running}>
            {is_running ? 'Running…' : '▶ Run Now'}
          </button>
        </div>
      </div>

      {/* Config card */}
      <div className={styles.configCard}>
        <div className={styles.toggleRow}>
          <div>
            <div className={styles.toggleLabel}>
              Auto-Scout is <strong>{enabled ? 'ON' : 'OFF'}</strong>
            </div>
            <div className={styles.toggleSub}>
              {enabled
                ? `Next scan: ${fmtDate(next_run)} · Last: ${fmtDate(last_run)}`
                : 'Enable to scan the market automatically on a schedule'}
            </div>
          </div>
          <button
            className={[styles.toggle, enabled && styles.toggleOn].filter(Boolean).join(' ')}
            onClick={toggleEnabled}
            disabled={saving}
          >
            <span className={styles.knob} />
          </button>
        </div>

        <div className={styles.configGrid}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>SCAN INTERVAL</span>
            <select
              className={styles.select}
              value={localCfg.interval_hours}
              onChange={e => setLocalCfg(p => ({ ...p, interval_hours: Number(e.target.value) }))}
            >
              {INTERVALS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>STOCKS PER SCAN</span>
            <select
              className={styles.select}
              value={localCfg.max_stocks}
              onChange={e => setLocalCfg(p => ({ ...p, max_stocks: Number(e.target.value) }))}
            >
              {[1, 2, 3, 4, 5].map(n => (
                <option key={n} value={n}>{n} stock{n > 1 ? 's' : ''}</option>
              ))}
            </select>
          </label>

          <label className={styles.field}>
            <span className={styles.fieldLabel}>LLM PROVIDER</span>
            <select
              className={styles.select}
              value={localCfg.llm_provider}
              onChange={e => setLocalCfg(p => ({ ...p, llm_provider: e.target.value }))}
            >
              {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          </label>

          <label className={[styles.field, styles.fieldFull].join(' ')}>
            <span className={styles.fieldLabel}>FOCUS THEME <span className={styles.optional}>(optional)</span></span>
            <input
              className={styles.input}
              type="text"
              placeholder="e.g. AI stocks, dividend growth, small-cap momentum, tech sector…"
              value={localCfg.theme}
              onChange={e => setLocalCfg(p => ({ ...p, theme: e.target.value }))}
            />
          </label>
        </div>

        <div className={styles.configFooter}>
          <button
            className={styles.saveBtn}
            onClick={() => saveConfig(localCfg)}
            disabled={saving}
          >
            {saving ? 'Saving…' : savedMsg ? '✓ Saved' : 'Save Config'}
          </button>
          {last_error && <span className={styles.errorMsg}>Error: {last_error}</span>}
        </div>
      </div>

      {/* How it works */}
      <div className={styles.howItWorks}>
        <span className={styles.howIcon}>💡</span>
        <span>
          The scout asks an LLM to identify promising stocks, then runs the full 12-agent analysis pipeline
          on each one. Only stocks where the Portfolio Manager says <strong>BUY</strong> appear below.
          Each scan can take 5–20 min per stock — choose a small count to start.
        </span>
      </div>

      {/* Recommendations */}
      <div className={styles.recsHeader}>
        <span className={styles.recsTitle}>BUY Recommendations</span>
        <span className={styles.recsCount}>{recommendations.length} found</span>
      </div>

      {recommendations.length === 0 ? (
        <div className={styles.empty}>
          {is_running
            ? '🔄 Scout is analyzing the market right now… this takes a few minutes per stock.'
            : 'No recommendations yet. Click "Run Now" or enable auto-scanning to get started.'}
        </div>
      ) : (
        <div className={styles.recGrid}>
          {recommendations.map(rec => (
            <RecCard key={rec.id} rec={rec} onDismiss={() => dismiss(rec.id)} />
          ))}
        </div>
      )}
    </div>
  )
}

function RecCard({ rec, onDismiss }) {
  const [expanded, setExpanded] = useState(false)
  const words = rec.reasoning ? rec.reasoning.split(' ') : []
  const snippet = words.slice(0, 55).join(' ') + (words.length > 55 ? '…' : '')

  const SECTOR_COLORS = {
    Technology: 'indigo', Healthcare: 'green', Energy: 'yellow',
    Financials: 'blue', 'Consumer Discretionary': 'orange',
    Industrials: 'gray', 'Communication Services': 'purple',
  }
  const sectorColor = SECTOR_COLORS[rec.sector] || 'indigo'

  return (
    <div className={styles.recCard}>
      <div className={styles.recTop}>
        <div className={styles.recLeft}>
          <span className={styles.recTicker}>{rec.ticker}</span>
          <span className={styles.buyBadge}>BUY ↑</span>
        </div>
        <button className={styles.dismissBtn} onClick={onDismiss} title="Dismiss">✕</button>
      </div>

      <div className={styles.recMeta}>
        {rec.company && <span className={styles.recCompany}>{rec.company}</span>}
        {rec.sector && (
          <span className={[styles.sectorBadge, styles[`sector_${sectorColor}`]].join(' ')}>
            {rec.sector}
          </span>
        )}
      </div>

      <div className={styles.recPriceRow}>
        <span className={styles.recPrice}>{rec.price ? `$${rec.price.toFixed(2)}` : '—'}</span>
        <span className={styles.recDate}>{fmtDate(rec.ts)}</span>
      </div>

      <p className={styles.recReasoning}>{expanded ? rec.reasoning : snippet}</p>

      <button className={styles.expandBtn} onClick={() => setExpanded(e => !e)}>
        {expanded ? 'Show less ↑' : 'Full reasoning ↓'}
      </button>
    </div>
  )
}
