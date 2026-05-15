import { useState, useEffect } from 'react'
import styles from './PnlCard.module.css'

const PERIODS = [
  { key: 'today', label: 'Today' },
  { key: '7d',    label: '7D'    },
  { key: '30d',   label: '30D'   },
  { key: '1y',    label: '1Y'    },
  { key: 'all',   label: 'All'   },
]

const fmt = (n, dec = 2) =>
  n == null ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec })

export default function PnlCard({ cardClassName }) {
  const [period,  setPeriod]  = useState('30d')
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`/alpaca/pnl?period=${period}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => { setData(null); setLoading(false) })
  }, [period])

  const pnl    = data?.pnl    ?? null
  const pnlPct = data?.pnl_pct ?? null
  const isPos  = pnl == null ? null : pnl >= 0

  const colorCls = isPos === true ? styles.green : isPos === false ? styles.red : ''

  return (
    <div className={[styles.card, cardClassName].filter(Boolean).join(' ')}>
      <div className={styles.label}>P&amp;L</div>

      <div className={[styles.value, colorCls].filter(Boolean).join(' ')}>
        {loading
          ? '—'
          : pnl == null
            ? '—'
            : `${pnl >= 0 ? '+' : ''}$${fmt(Math.abs(pnl))}${pnl < 0 ? ' ▼' : ''}`
        }
      </div>

      {!loading && pnlPct != null && (
        <div className={[styles.sub, colorCls].filter(Boolean).join(' ')}>
          {pnlPct >= 0 ? '+' : ''}{fmt(pnlPct)}%
        </div>
      )}

      <div className={styles.chips}>
        {PERIODS.map(p => (
          <button
            key={p.key}
            className={[styles.chip, period === p.key ? styles.chipActive : ''].filter(Boolean).join(' ')}
            onClick={() => setPeriod(p.key)}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  )
}
