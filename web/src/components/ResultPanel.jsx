import { useEffect, useState } from 'react'
import PriceChart from './PriceChart'
import MetricCards from './MetricCards'
import StrategyVisual from './StrategyVisual'
import styles from './ResultPanel.module.css'

export default function ResultPanel({ decision }) {
  const [marketData, setMarketData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!decision?.ticker) return
    setLoading(true)
    setMarketData(null)
    fetch(`/market-data/${decision.ticker}`)
      .then(r => r.json())
      .then(d => setMarketData(d))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [decision?.ticker, decision?.date])

  if (!decision) return null

  const metrics = marketData?.metrics
  const prices  = marketData?.prices || []
  const news    = marketData?.news   || []

  return (
    <div className={styles.wrap}>
      {/* Company header */}
      <div className={styles.companyHeader}>
        <div>
          <div className={styles.companyName}>{metrics?.name || decision.ticker}</div>
          <div className={styles.companyMeta}>{decision.ticker} · Analysis date: {decision.date}</div>
        </div>
        {loading && <span className={styles.loading}>Loading market data…</span>}
      </div>

      {/* Strategy — most important, first */}
      <StrategyVisual
        signal={decision.signal}
        entryPrice={decision.entry_price}
        metrics={metrics}
      />

      {/* Price chart */}
      {prices.length > 0 && (
        <div className={styles.section}>
          <PriceChart prices={prices} analysisDate={decision.date} ticker={decision.ticker} />
        </div>
      )}

      {/* Key metrics */}
      {metrics && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>Key Metrics · Yahoo Finance</div>
          <MetricCards metrics={metrics} />
        </div>
      )}

      {/* News sources */}
      {news.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>Latest News · Yahoo Finance</div>
          <div className={styles.newsList}>
            {news.map((n, i) => (
              <a
                key={i}
                className={styles.newsItem}
                href={n.url || '#'}
                target="_blank"
                rel="noreferrer"
              >
                <span className={styles.newsSource}>{n.source}</span>
                <span className={styles.newsTitle}>{n.title}</span>
                <span className={styles.newsArrow}>↗</span>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Full reasoning toggle */}
      <div className={styles.section}>
        <button className={styles.toggleBtn} onClick={() => setExpanded(e => !e)}>
          {expanded ? '▾ Hide full analyst reasoning' : '▸ Show full analyst reasoning'}
        </button>
        {expanded && (
          <pre className={styles.reasoning}>{decision.reasoning}</pre>
        )}
      </div>
    </div>
  )
}
