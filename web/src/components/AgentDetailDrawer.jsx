import { useEffect } from 'react'
import styles from './AgentDetailDrawer.module.css'

const AGENT_META = {
  market:           { label: 'Market Analyst',       icon: '📊', color: 'indigo' },
  social:           { label: 'Sentiment Analyst',    icon: '💬', color: 'purple' },
  news:             { label: 'News Analyst',          icon: '📰', color: 'blue' },
  fundamentals:     { label: 'Fundamentals Analyst', icon: '📈', color: 'green' },
  bull_researcher:  { label: 'Bull Researcher',      icon: '🐂', color: 'green' },
  bear_researcher:  { label: 'Bear Researcher',      icon: '🐻', color: 'red' },
  research_manager: { label: 'Research Manager',     icon: '🔬', color: 'indigo' },
  trader:           { label: 'Trader',               icon: '⚡', color: 'yellow' },
  aggressive:       { label: 'Risk: Aggressive',     icon: '🔥', color: 'red' },
  conservative:     { label: 'Risk: Conservative',   icon: '🛡️', color: 'purple' },
  neutral:          { label: 'Risk: Neutral',        icon: '⚖️',  color: 'blue' },
  portfolio_manager:{ label: 'Portfolio Manager',    icon: '💼', color: 'green' },
}

export default function AgentDetailDrawer({ agentId, data, onClose }) {
  const meta = AGENT_META[agentId] || { label: agentId, icon: '?', color: 'cyan' }

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} />
      <div className={styles.drawer}>
        <div className={styles.drawerHeader}>
          <div className={styles.drawerTitle}>
            <span className={styles.icon}>{meta.icon}</span>
            <span className={[styles.label, styles[`color_${meta.color}`]].join(' ')}>
              {meta.label}
            </span>
            <span className={styles.statusPill}>
              {data.status === 'done' ? '✓ Complete' : '● Running'}
            </span>
          </div>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <div className={styles.drawerBody}>
          {data.report ? (
            <pre className={styles.report}>{data.report}</pre>
          ) : data.snippet ? (
            <pre className={styles.report}>{data.snippet}</pre>
          ) : (
            <p className={styles.empty}>No output available yet.</p>
          )}
        </div>
      </div>
    </>
  )
}
