import { useState } from 'react'
import styles from './DecisionPanel.module.css'

const SIGNAL_META = {
  Buy:         { color: 'green',  glyph: '↑', label: 'BUY',  action: 'Analysts recommend buying — consider entering a position.' },
  Overweight:  { color: 'green',  glyph: '↑', label: 'BUY',  action: 'Analysts recommend increasing your position in this stock.' },
  Hold:        { color: 'yellow', glyph: '→', label: 'HOLD', action: 'No action needed — hold your current position and wait.' },
  Underweight: { color: 'red',    glyph: '↓', label: 'SELL', action: 'Analysts recommend reducing your position in this stock.' },
  Sell:        { color: 'red',    glyph: '↓', label: 'SELL', action: 'Analysts recommend selling — consider exiting your position.' },
}

export default function DecisionPanel({ decision, error }) {
  const [expanded, setExpanded] = useState(false)

  if (error) {
    return (
      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div className={styles.panelLeft}>
            <span className={styles.panelIcon}>⚠️</span>
            <span className={styles.panelTitle}>Error</span>
          </div>
        </div>
        <div className={styles.errorBody}>
          <pre className={styles.errorText}>{error}</pre>
        </div>
      </section>
    )
  }

  if (!decision) return null

  const meta = SIGNAL_META[decision.signal] || { color: 'indigo', glyph: '?', label: decision.signal || '—' }

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <div className={styles.panelLeft}>
          <span className={styles.panelIcon}>🎯</span>
          <span className={styles.panelTitle}>Final Decision</span>
        </div>
        <span className={styles.meta}>{decision.ticker} · {decision.date}</span>
      </div>

      <div className={styles.body}>
        <div className={[styles.signal, styles[`signal_${meta.color}`]].join(' ')}>
          <span className={styles.glyph}>{meta.glyph}</span>
          <div>
            <div className={styles.signalLabel}>{meta.label}</div>
            <div className={styles.signalSub}>{meta.action}</div>
            {decision.entry_price && (
              <div className={styles.signalSub}>Entry price: ${decision.entry_price}</div>
            )}
          </div>
        </div>

        <div className={styles.reasoning}>
          <button className={styles.toggleBtn} onClick={() => setExpanded(e => !e)}>
            {expanded ? '▾ Hide reasoning' : '▸ Show full reasoning'}
          </button>
          {expanded && (
            <pre className={styles.reasoningText}>{decision.reasoning}</pre>
          )}
        </div>
      </div>
    </section>
  )
}
