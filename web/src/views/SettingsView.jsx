import { useState, useEffect, useRef, useCallback } from 'react'
import styles from './SettingsView.module.css'

const PROVIDER_KEY_DEFS = [
  { key: 'OPENAI_API_KEY',       label: 'OpenAI',       placeholder: 'sk-…',    doc: 'Required for GPT-4o, o1, and gpt-5.4 models.' },
  { key: 'ANTHROPIC_API_KEY',    label: 'Anthropic',    placeholder: 'sk-ant-…', doc: 'Required for Claude Opus, Sonnet, and Haiku models.' },
  { key: 'GOOGLE_API_KEY',       label: 'Google',       placeholder: 'AIza…',   doc: 'Required for Gemini 2.5 Pro / Flash models.' },
  { key: 'XAI_API_KEY',          label: 'xAI (Grok)',   placeholder: 'xai-…',   doc: 'Required for Grok-3 and Grok-3-mini models.' },
  { key: 'DEEPSEEK_API_KEY',     label: 'DeepSeek',     placeholder: 'sk-…',    doc: 'Required for DeepSeek-V3 and R1 models.' },
  { key: 'GROQ_API_KEY',         label: 'Groq',         placeholder: 'gsk_…',   doc: 'Required for Llama 3.3 70B, Llama 3.1, Gemma, and other Groq-hosted models. Free tier at console.groq.com.' },
  { key: 'ALPHA_VANTAGE_API_KEY',label: 'Alpha Vantage',placeholder: '…',       doc: 'Optional. Enables premium financial data. Free tier available at alphavantage.co.' },
]

const ALPACA_KEY_DEFS = [
  { key: 'APCA_API_KEY_ID',     label: 'API Key ID',    placeholder: 'PKABF…',                         doc: 'Your Alpaca API key ID. Get it from app.alpaca.markets → API Keys.' },
  { key: 'APCA_API_SECRET_KEY', label: 'Secret Key',    placeholder: 'GpD9c…',                         doc: 'Your Alpaca secret key. Only shown once when generated — save it somewhere safe.' },
  { key: 'APCA_BASE_URL',       label: 'Endpoint',      placeholder: 'https://paper-api.alpaca.markets/v2', doc: 'Paper trading: https://paper-api.alpaca.markets/v2 — Live trading: https://api.alpaca.markets/v2' },
]

const DISCORD_KEY_DEFS = [
  { key: 'DISCORD_WEBHOOK_URL', label: 'Webhook URL',  placeholder: 'https://discord.com/api/webhooks/…', doc: 'Paste a webhook URL to get analysis results and monitor alerts sent to a Discord channel. Create one in Server Settings → Integrations → Webhooks.' },
  { key: 'DISCORD_BOT_TOKEN',   label: 'Bot Token',    placeholder: 'MTY…',  doc: 'Optional. A bot token lets you use !analyze, !portfolio, and !ask commands in Discord. Create a bot at discord.com/developers/applications.' },
  { key: 'DISCORD_CHANNEL_ID',  label: 'Channel ID',   placeholder: '123456789…', doc: 'Optional. Restricts bot commands to a specific channel. Right-click a channel in Discord → Copy Channel ID (Developer Mode must be on).' },
]

export default function SettingsView() {
  const [status, setStatus] = useState({})  // { KEY: { set, preview } }
  const [form, setForm] = useState({})
  const [show, setShow] = useState({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loadError, setLoadError] = useState(null)

  useEffect(() => {
    fetch('/settings')
      .then(r => r.json())
      .then(data => setStatus(data))
      .catch(() => setLoadError('Could not reach backend. Is uvicorn running?'))
  }, [])

  const set = (key, val) => setForm(prev => ({ ...prev, [key]: val }))
  const toggleShow = (key) => setShow(prev => ({ ...prev, [key]: !prev[key] }))

  const handleSave = async () => {
    const payload = {}
    for (const [k, v] of Object.entries(form)) {
      if (v && v.trim()) payload[k] = v.trim()
    }
    if (!Object.keys(payload).length) return

    setSaving(true)
    setSaved(false)
    try {
      const r = await fetch('/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!r.ok) throw new Error(await r.text())

      // Re-fetch status
      const updated = await fetch('/settings').then(r => r.json())
      setStatus(updated)
      setForm({})
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      alert(`Save failed: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  const dirty = Object.values(form).some(v => v && v.trim())

  return (
    <div className={styles.wrap}>
      <div className={styles.pageHeader}>
        <div>
          <h2 className={styles.title}>Settings</h2>
          <p className={styles.sub}>API keys are saved to your local <code>.env</code> file — never sent anywhere else.</p>
        </div>
      </div>

      {loadError && <div className={styles.errorBanner}>{loadError}</div>}

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionIcon}>🔑</span>
          <span className={styles.sectionLabel}>API Keys</span>
        </div>

        <div className={styles.keyList}>
          {PROVIDER_KEY_DEFS.map(({ key, label, placeholder, doc }) => {
            const st = status[key] || {}
            const isSet = st.set
            const val = form[key] ?? ''
            const visible = show[key]

            return (
              <div key={key} className={styles.keyRow}>
                <div className={styles.keyMeta}>
                  <div className={styles.keyTop}>
                    <span className={[styles.dot, isSet ? styles.dotGreen : styles.dotGray].join(' ')} />
                    <span className={styles.keyLabel}>{label}</span>
                    {isSet && <span className={styles.preview}>{st.preview}</span>}
                    {!isSet && <span className={styles.notSet}>not set</span>}
                  </div>
                  <p className={styles.keyDoc}>{doc}</p>
                </div>

                <div className={styles.inputWrap}>
                  <input
                    className={styles.input}
                    type={visible ? 'text' : 'password'}
                    value={val}
                    onChange={e => set(key, e.target.value)}
                    placeholder={isSet ? '(leave blank to keep current)' : placeholder}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button
                    className={styles.eyeBtn}
                    onClick={() => toggleShow(key)}
                    type="button"
                    tabIndex={-1}
                  >
                    {visible ? '🙈' : '👁'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>

        <div className={styles.actions}>
          <button
            className={styles.saveBtn}
            onClick={handleSave}
            disabled={!dirty || saving}
          >
            {saving ? '…Saving' : saved ? '✓ Saved' : 'Save Keys'}
          </button>
          {saved && <span className={styles.savedMsg}>Keys written to .env</span>}
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionIcon}>💬</span>
          <span className={styles.sectionLabel}>Discord Integration</span>
        </div>
        <p className={styles.keyDoc} style={{ marginBottom: 12, padding: '0 2px' }}>
          Connect Discord to receive analysis alerts and run commands from your server.
          Webhook URL is enough for notifications — add a Bot Token for two-way chat commands.
          Restart the server after saving to activate the bot.
        </p>

        <div className={styles.keyList}>
          {DISCORD_KEY_DEFS.map(({ key, label, placeholder, doc }) => {
            const st = status[key] || {}
            const isSet = st.set
            const val = form[key] ?? ''
            const visible = show[key]

            return (
              <div key={key} className={styles.keyRow}>
                <div className={styles.keyMeta}>
                  <div className={styles.keyTop}>
                    <span className={[styles.dot, isSet ? styles.dotGreen : styles.dotGray].join(' ')} />
                    <span className={styles.keyLabel}>{label}</span>
                    {isSet && <span className={styles.preview}>{st.preview}</span>}
                    {!isSet && <span className={styles.notSet}>not set</span>}
                  </div>
                  <p className={styles.keyDoc}>{doc}</p>
                </div>

                <div className={styles.inputWrap}>
                  <input
                    className={styles.input}
                    type={visible ? 'text' : 'password'}
                    value={val}
                    onChange={e => set(key, e.target.value)}
                    placeholder={isSet ? '(leave blank to keep current)' : placeholder}
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button
                    className={styles.eyeBtn}
                    onClick={() => toggleShow(key)}
                    type="button"
                    tabIndex={-1}
                  >
                    {visible ? '🙈' : '👁'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>

        <div className={styles.actions}>
          <button
            className={styles.saveBtn}
            onClick={handleSave}
            disabled={!dirty || saving}
          >
            {saving ? '…Saving' : saved ? '✓ Saved' : 'Save'}
          </button>
          {saved && <span className={styles.savedMsg}>Keys written to .env</span>}
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionIcon}>📈</span>
          <span className={styles.sectionLabel}>Alpaca Brokerage</span>
        </div>
        <p className={styles.keyDoc} style={{ marginBottom: 12, padding: '0 2px' }}>
          Connect Alpaca to view your positions, P&L, and enable auto-trading.
          Use the paper trading endpoint while testing — switch to live when ready.
          Get keys at <strong>app.alpaca.markets → API Keys</strong>.
        </p>
        <div className={styles.keyList}>
          {ALPACA_KEY_DEFS.map(({ key, label, placeholder, doc }) => {
            const st = status[key] || {}
            const isSet = st.set
            const val = form[key] ?? ''
            const visible = show[key]
            return (
              <div key={key} className={styles.keyRow}>
                <div className={styles.keyMeta}>
                  <div className={styles.keyTop}>
                    <span className={[styles.dot, isSet ? styles.dotGreen : styles.dotGray].join(' ')} />
                    <span className={styles.keyLabel}>{label}</span>
                    {isSet && <span className={styles.preview}>{st.preview}</span>}
                    {!isSet && <span className={styles.notSet}>not set</span>}
                  </div>
                  <p className={styles.keyDoc}>{doc}</p>
                </div>
                <div className={styles.inputWrap}>
                  <input
                    type={visible ? 'text' : 'password'}
                    className={styles.keyInput}
                    value={val}
                    placeholder={placeholder}
                    onChange={e => { setForm(f => ({ ...f, [key]: e.target.value })); setDirty(true) }}
                  />
                  <button className={styles.eyeBtn} onClick={() => setShow(s => ({ ...s, [key]: !s[key] }))}>
                    {visible ? '🙈' : '👁'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
        <div className={styles.actions}>
          <button className={styles.saveBtn} onClick={handleSave} disabled={!dirty || saving}>
            {saving ? '…Saving' : saved ? '✓ Saved' : 'Save'}
          </button>
          {saved && <span className={styles.savedMsg}>Keys written to .env</span>}
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionIcon}>📡</span>
          <span className={styles.sectionLabel}>Data Vendors</span>
        </div>
        <div className={styles.infoGrid}>
          <InfoCard title="yfinance" status="active" desc="Default. No API key required. Provides price data, fundamentals, and news via Yahoo Finance." />
          <InfoCard title="Alpha Vantage" status={status['ALPHA_VANTAGE_API_KEY']?.set ? 'active' : 'inactive'} desc="Premium financial data. Set ALPHA_VANTAGE_API_KEY above to enable. Free tier: 25 req/day." />
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <span className={styles.sectionIcon}>ℹ️</span>
          <span className={styles.sectionLabel}>About</span>
        </div>
        <div className={styles.about}>
          <p>TradingAgents v0.2.4 · Multi-agent LLM financial analysis framework by <a href="https://github.com/TauricResearch" target="_blank" rel="noreferrer">Tauric Research</a></p>
          <p>Web UI built on FastAPI + React/Vite. Agents run locally on your machine. Your API keys are used only to call the respective LLM providers.</p>
        </div>
      </div>

      <LogsPanel />
    </div>
  )
}

function LogsPanel() {
  const [logs, setLogs] = useState([])
  const [filter, setFilter] = useState('ALL')   // ALL | ERROR | WARN
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const bottomRef = useRef(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const r = await fetch('/logs?n=500')
      if (r.ok) setLogs(await r.json())
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!autoRefresh) return
    const iv = setInterval(() => load(true), 8000)
    return () => clearInterval(iv)
  }, [autoRefresh, load])

  const levelClass = (level) => {
    if (level === 'ERROR' || level === 'CRITICAL') return styles.logError
    if (level === 'WARNING') return styles.logWarn
    return styles.logInfo
  }

  const formatTs = (ts) => {
    if (!ts) return ''
    try {
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch { return ts.slice(11, 19) }
  }

  const visible = logs.filter(e => {
    if (filter === 'ERROR' && e.level !== 'ERROR' && e.level !== 'CRITICAL') return false
    if (filter === 'WARN' && e.level !== 'WARNING' && e.level !== 'ERROR' && e.level !== 'CRITICAL') return false
    if (search && !e.msg?.toLowerCase().includes(search.toLowerCase()) && !e.src?.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  return (
    <div className={styles.section}>
      <div className={styles.sectionHeader}>
        <span className={styles.sectionIcon}>📋</span>
        <span className={styles.sectionLabel}>Application Logs</span>
      </div>

      <div className={styles.logToolbar}>
        <div className={styles.logFilters}>
          {['ALL', 'WARN', 'ERROR'].map(f => (
            <button
              key={f}
              className={[styles.filterBtn, filter === f && styles.filterActive].filter(Boolean).join(' ')}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <input
          className={styles.logSearch}
          placeholder="Search…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <button
          className={[styles.filterBtn, autoRefresh && styles.filterActive].filter(Boolean).join(' ')}
          onClick={() => setAutoRefresh(a => !a)}
          title="Auto-refresh every 8s"
        >
          {autoRefresh ? '⏵ Live' : '⏸ Paused'}
        </button>
        <button className={styles.filterBtn} onClick={() => load()}>↻</button>
      </div>

      <div className={styles.logBox}>
        {loading && logs.length === 0 ? (
          <div className={styles.logEmpty}>Loading…</div>
        ) : visible.length === 0 ? (
          <div className={styles.logEmpty}>No log entries{search ? ' matching search' : ''}.</div>
        ) : (
          visible.map((e, i) => (
            <div key={i} className={[styles.logRow, levelClass(e.level)].join(' ')}>
              <span className={styles.logTs}>{formatTs(e.ts)}</span>
              <span className={styles.logLevel}>{(e.level || 'INFO').slice(0, 4)}</span>
              {e.src && e.src !== 'ellie' && <span className={styles.logSrc}>{e.src}</span>}
              <span className={styles.logMsg}>{e.msg}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <div className={styles.logFooter}>
        {visible.length} of {logs.length} entries
        {autoRefresh && <span className={styles.logLive}> · live</span>}
      </div>
    </div>
  )
}

function InfoCard({ title, status, desc }) {
  return (
    <div className={styles.infoCard}>
      <div className={styles.infoCardTop}>
        <span className={styles.infoTitle}>{title}</span>
        <span className={[styles.statusBadge, status === 'active' ? styles.statusActive : styles.statusInactive].join(' ')}>
          {status === 'active' ? 'ACTIVE' : 'INACTIVE'}
        </span>
      </div>
      <p className={styles.infoDesc}>{desc}</p>
    </div>
  )
}
