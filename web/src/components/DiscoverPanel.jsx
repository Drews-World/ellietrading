import { useState } from 'react'
import styles from './DiscoverPanel.module.css'

const SECTOR_COLORS = {
  Technology: 'indigo',
  Healthcare: 'green',
  Finance: 'blue',
  Financials: 'blue',
  Energy: 'yellow',
  'Consumer Discretionary': 'orange',
  'Consumer Staples': 'teal',
  Industrials: 'gray',
  Materials: 'brown',
  Utilities: 'purple',
  'Real Estate': 'pink',
  'Communication Services': 'cyan',
  default: 'indigo',
}

export default function DiscoverPanel({ config, onAnalyze, isRunning }) {
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState('')
  const [loading, setLoading] = useState(false)
  const [picks, setPicks] = useState([])
  const [error, setError] = useState(null)

  const handleFind = async () => {
    setLoading(true)
    setError(null)
    setPicks([])
    try {
      const r = await fetch('/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          llm_provider: config.llm_provider,
          model: config.quick_think_llm,
          theme,
          count: 5,
        }),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Discovery failed')
      setPicks(data.picks || [])
      if (!data.picks?.length) setError('No picks returned. Try a different theme or provider.')
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.wrap}>
      <button
        className={[styles.toggleBar, open && styles.toggleBarOpen].filter(Boolean).join(' ')}
        onClick={() => setOpen(o => !o)}
      >
        <span className={styles.toggleLeft}>
          <span className={styles.toggleIcon}>🔍</span>
          <span className={styles.toggleTitle}>Discover Stocks</span>
          <span className={styles.toggleSub}>Let AI find opportunities for you to analyze</span>
        </span>
        <span className={styles.chevron}>{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className={styles.body}>
          <div className={styles.searchRow}>
            <input
              className={styles.themeInput}
              value={theme}
              onChange={e => setTheme(e.target.value)}
              placeholder='Optional: "AI stocks", "dividend plays", "beaten-down tech", "energy sector"…'
              onKeyDown={e => e.key === 'Enter' && !loading && handleFind()}
            />
            <button
              className={styles.findBtn}
              onClick={handleFind}
              disabled={loading || isRunning}
            >
              {loading ? <><span className={styles.spinner} />Scanning…</> : 'Find Opportunities'}
            </button>
          </div>

          {error && <p className={styles.error}>{error}</p>}

          {loading && !picks.length && (
            <div className={styles.skeletonGrid}>
              {[1, 2, 3, 4, 5].map(i => (
                <div key={i} className={styles.skeleton} />
              ))}
            </div>
          )}

          {picks.length > 0 && (
            <div className={styles.pickGrid}>
              {picks.map((pick, i) => {
                const colorKey = SECTOR_COLORS[pick.sector] || 'indigo'
                return (
                  <div key={i} className={styles.card}>
                    <div className={styles.cardTop}>
                      <span className={styles.ticker}>{pick.ticker}</span>
                      <span className={[styles.sectorBadge, styles[`sector_${colorKey}`]].join(' ')}>
                        {pick.sector || 'Equity'}
                      </span>
                    </div>
                    <p className={styles.company}>{pick.company}</p>
                    <p className={styles.reason}>{pick.reason}</p>
                    <button
                      className={styles.analyzeBtn}
                      onClick={() => onAnalyze(pick.ticker)}
                      disabled={isRunning}
                    >
                      {isRunning ? 'Running…' : 'Analyze →'}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
