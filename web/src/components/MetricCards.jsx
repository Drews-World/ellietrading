import styles from './MetricCards.module.css'

function fmtCap(n) {
  if (!n) return '—'
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(1)}B`
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(0)}M`
  return `$${n}`
}

function fmtPct(n) {
  if (n == null) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${(n * 100).toFixed(1)}%`
}

function fmtPE(n) {
  return n == null ? '—' : n.toFixed(1) + 'x'
}

function Week52Bar({ low, high, current }) {
  if (!low || !high || !current) return <div className={styles.rangeEmpty}>—</div>
  const pct = Math.max(0, Math.min(100, ((current - low) / (high - low)) * 100))
  const isLow  = pct < 30
  const isHigh = pct > 70
  return (
    <div className={styles.rangeWrap}>
      <span className={styles.rangeLow}>${low.toFixed(0)}</span>
      <div className={styles.rangeBar}>
        <div className={styles.rangeFill} style={{ width: `${pct}%` }}>
          <div className={[
            styles.rangeThumb,
            isLow ? styles.thumbLow : isHigh ? styles.thumbHigh : styles.thumbMid,
          ].join(' ')} />
        </div>
      </div>
      <span className={styles.rangeHigh}>${high.toFixed(0)}</span>
    </div>
  )
}

function BetaLabel({ beta }) {
  if (beta == null) return <span className={styles.metaVal}>—</span>
  const label = beta > 1.5 ? 'High volatility' : beta < 0.8 ? 'Low volatility' : 'Average volatility'
  const cls   = beta > 1.5 ? styles.valRed : beta < 0.8 ? styles.valGreen : styles.valYellow
  return <span className={[styles.metaVal, cls].join(' ')}>{beta.toFixed(2)} · {label}</span>
}

function GrowthVal({ n }) {
  if (n == null) return <span className={styles.metaVal}>—</span>
  const cls = n >= 0 ? styles.valGreen : styles.valRed
  return <span className={[styles.metaVal, cls].join(' ')}>{fmtPct(n)} YoY</span>
}

export default function MetricCards({ metrics }) {
  if (!metrics) return null
  const { trailing_pe, forward_pe, market_cap, week_52_high, week_52_low,
          current_price, beta, profit_margins, revenue_growth, dividend_yield } = metrics

  return (
    <div className={styles.grid}>
      <Metric label="Market Cap" value={fmtCap(market_cap)} />
      <Metric label="P/E (Trailing)" value={fmtPE(trailing_pe)} sub={`Forward: ${fmtPE(forward_pe)}`} />
      <Metric label="Profit Margin" value={fmtPct(profit_margins)} colored n={profit_margins} />
      <Metric label="Revenue Growth" custom={<GrowthVal n={revenue_growth} />} />
      <Metric label="Beta (Volatility)" custom={<BetaLabel beta={beta} />} />
      <Metric label="Dividend Yield" value={dividend_yield ? fmtPct(dividend_yield) : 'None'} />
      <div className={styles.rangeCard}>
        <span className={styles.metaLabel}>52-Week Range</span>
        <Week52Bar low={week_52_low} high={week_52_high} current={current_price} />
        {current_price && <span className={styles.currentLabel}>Current: ${current_price.toFixed(2)}</span>}
      </div>
    </div>
  )
}

function Metric({ label, value, sub, colored, n, custom }) {
  let valClass = styles.metaVal
  if (colored && n != null) valClass = [styles.metaVal, n >= 0 ? styles.valGreen : styles.valRed].join(' ')
  return (
    <div className={styles.card}>
      <span className={styles.metaLabel}>{label}</span>
      {custom || <span className={valClass}>{value}</span>}
      {sub && <span className={styles.metaSub}>{sub}</span>}
    </div>
  )
}
