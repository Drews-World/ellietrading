import { useState, useEffect, useCallback } from 'react'
import AgentFeed from '../components/AgentFeed'
import styles from './OperationsView.module.css'

// All agent IDs that AgentFeed knows about
const ALL_AGENTS = [
  'market', 'social', 'news', 'fundamentals',
  'bull_researcher', 'bear_researcher', 'research_manager',
  'trader', 'aggressive', 'conservative', 'neutral',
  'portfolio_manager',
]

const ANALYSIS_AGENTS = [
  'market', 'social', 'news', 'fundamentals',
  'bull_researcher', 'bear_researcher', 'research_manager',
]

function deriveAgentStates(fund, log) {
  // Default: all idle
  const idle = Object.fromEntries(ALL_AGENTS.map(id => [id, { status: 'idle', snippet: '' }]))

  if (!fund?.active || !log?.length) return idle

  const recent = (log[0]?.msg || '').toLowerCase()

  if (/analyzing|cooling down 75s/.test(recent)) {
    return Object.fromEntries(ALL_AGENTS.map(id => [
      id,
      ANALYSIS_AGENTS.includes(id)
        ? { status: 'running', snippet: 'Analyzing…' }
        : { status: 'idle', snippet: '' },
    ]))
  }

  if (/bought|sold|closed/.test(recent)) {
    return Object.fromEntries(ALL_AGENTS.map(id => [
      id,
      (id === 'trader' || id === 'portfolio_manager')
        ? { status: 'done', snippet: recent }
        : { status: 'idle', snippet: '' },
    ]))
  }

  if (/review/.test(recent)) {
    return Object.fromEntries(ALL_AGENTS.map(id => [
      id,
      (id === 'research_manager' || id === 'portfolio_manager')
        ? { status: 'running', snippet: 'Reviewing positions…' }
        : { status: 'idle', snippet: '' },
    ]))
  }

  if (/launch complete|fund launch complete/.test(recent)) {
    return Object.fromEntries(ALL_AGENTS.map(id => [id, { status: 'done', snippet: 'Launch complete' }]))
  }

  return idle
}

function fmtTs(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return iso }
}

function fmtDateTs(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

export default function OperationsView() {
  const [fund, setFund] = useState(null)
  const [log, setLog] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const [fundRes, logRes] = await Promise.all([
        fetch('/fund').then(r => r.json()),
        fetch('/fund/log').then(r => r.json()),
      ])
      setFund(fundRes)
      setLog(Array.isArray(logRes) ? logRes : [])
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Poll every 10 seconds
  useEffect(() => {
    const iv = setInterval(load, 10_000)
    return () => clearInterval(iv)
  }, [load])

  const agentStates = deriveAgentStates(fund, log)
  const lastLogTs = log[0]?.ts || null

  // Status badge
  let statusLabel = 'NOT LAUNCHED'
  let statusClass = styles.statusGray
  if (fund?.active) {
    statusLabel = 'ACTIVE'
    statusClass = styles.statusGreen
  } else if (fund?.launched_at && !fund?.active) {
    statusLabel = 'PAUSED'
    statusClass = styles.statusYellow
  }

  return (
    <div className={styles.page}>
      {/* ── Status bar ── */}
      <div className={styles.statusBar}>
        <div className={styles.statusLeft}>
          <span className={[styles.statusBadge, statusClass].join(' ')}>{statusLabel}</span>
          {lastLogTs && (
            <span className={styles.statusMeta}>Last activity: {fmtDateTs(lastLogTs)}</span>
          )}
          {fund?.next_daily_review && (
            <span className={styles.statusMeta}>Next review: {fmtDateTs(fund.next_daily_review)}</span>
          )}
        </div>
        <button className={styles.refreshBtn} onClick={load} disabled={loading}>
          {loading ? '↻ Loading…' : '↻ Refresh'}
        </button>
      </div>

      {/* ── Agent Feed ── */}
      <AgentFeed
        agents={agentStates}
        activeAgent={null}
        statusMsg={log[0]?.msg || ''}
        isRunning={fund?.active || false}
        onSelectAgent={null}
        selectedAgent={null}
      />

      {/* ── Activity log ── */}
      <div className={styles.logPanel}>
        <div className={styles.logHeader}>
          <span className={styles.logTitle}>Fund Activity Log</span>
          <span className={styles.logCount}>{log.length} entries</span>
        </div>
        <div className={styles.logList}>
          {log.length === 0 ? (
            <div className={styles.logEmpty}>No activity yet. Launch the fund to begin.</div>
          ) : (
            log.slice(0, 20).map((entry, i) => (
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
