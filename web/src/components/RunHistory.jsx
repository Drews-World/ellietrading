import styles from './RunHistory.module.css'

const SIGNAL_COLOR = {
  Buy: 'green', Overweight: 'green',
  Hold: 'yellow',
  Sell: 'red', Underweight: 'red',
  default: 'indigo',
}

function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

export default function RunHistory({ history, onClear, onLoad }) {
  return (
    <aside className={styles.aside}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.headerIcon}>🕐</span>
          <span className={styles.label}>History</span>
        </div>
        {history.length > 0 && (
          <button className={styles.clearBtn} onClick={onClear} title="Clear history">Clear</button>
        )}
      </div>

      <div className={styles.list}>
        {history.length === 0 && <p className={styles.empty}>No runs yet.</p>}
        {history.map(h => {
          const color = SIGNAL_COLOR[h.signal] || 'cyan'
          return (
            <div key={h.id} className={styles.entry} onClick={() => onLoad?.(h)} title="Load into config">
              <div className={styles.top}>
                <span className={styles.ticker}>{h.ticker}</span>
                <span className={[styles.badge, styles[`badge_${color}`]].join(' ')}>
                  {h.signal?.toUpperCase() || '—'}
                </span>
              </div>
              <div className={styles.bottom}>
                <span className={styles.tradeDate}>{h.date}</span>
                {h.entry_price && <span className={styles.price}>${h.entry_price}</span>}
              </div>
              <span className={styles.ts}>{fmtDate(h.ts)}</span>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
