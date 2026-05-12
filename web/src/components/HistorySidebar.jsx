import styles from './HistorySidebar.module.css'

const SIGNAL_COLOR = {
  Buy:         'green',
  Overweight:  'green',
  Hold:        'yellow',
  Underweight: 'red',
  Sell:        'red',
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

export default function HistorySidebar({ history, onClear }) {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.header}>
        <span className={styles.label}>// HISTORY</span>
        {history.length > 0 && (
          <button className={styles.clearBtn} onClick={onClear}>CLR</button>
        )}
      </div>

      <div className={styles.list}>
        {history.length === 0 && (
          <p className={styles.empty}>No runs yet.</p>
        )}
        {history.map(h => {
          const color = SIGNAL_COLOR[h.signal] || 'cyan'
          return (
            <div key={h.id} className={styles.entry}>
              <div className={styles.entryTop}>
                <span className={styles.ticker}>{h.ticker}</span>
                <span className={[styles.signal, styles[`signal_${color}`]].join(' ')}>
                  {h.signal?.toUpperCase() || '—'}
                </span>
              </div>
              <div className={styles.entryBottom}>
                <span className={styles.tradeDate}>{h.date}</span>
                <span className={styles.ts}>{formatDate(h.ts)}</span>
              </div>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
