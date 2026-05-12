import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import styles from './PriceChart.module.css'

function fmt$(n) { return `$${Number(n).toFixed(2)}` }

function shortDate(d) {
  const dt = new Date(d + 'T12:00:00Z')
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipDate}>{shortDate(label)}</div>
      <div className={styles.tooltipPrice}>{fmt$(payload[0].value)}</div>
    </div>
  )
}

export default function PriceChart({ prices = [], analysisDate, ticker }) {
  if (!prices.length) return null

  const first = prices[0].close
  const last  = prices[prices.length - 1].close
  const isUp  = last >= first
  const color = isUp ? '#059669' : '#dc2626'
  const gradId = `grad-${ticker}`

  const min = Math.min(...prices.map(p => p.low))  * 0.998
  const max = Math.max(...prices.map(p => p.high)) * 1.002

  // Show ~10 evenly spaced X labels
  const step = Math.max(1, Math.floor(prices.length / 10))
  const tickDates = prices.filter((_, i) => i % step === 0).map(p => p.date)

  const changePct = ((last - first) / first * 100).toFixed(2)
  const changeSign = isUp ? '+' : ''

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.label}>3-Month Price</span>
        <span className={[styles.change, isUp ? styles.up : styles.down].join(' ')}>
          {changeSign}{changePct}%
        </span>
      </div>

      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={prices} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={color} stopOpacity={0.18} />
              <stop offset="95%" stopColor={color} stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="date"
            ticks={tickDates}
            tickFormatter={shortDate}
            tick={{ fontSize: 10, fill: 'var(--text-dim)' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[min, max]}
            tickFormatter={v => `$${v >= 1000 ? (v/1000).toFixed(1)+'k' : v.toFixed(0)}`}
            tick={{ fontSize: 10, fill: 'var(--text-dim)' }}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <Tooltip content={<CustomTooltip />} />
          {analysisDate && (
            <ReferenceLine
              x={analysisDate}
              stroke="var(--indigo)"
              strokeDasharray="4 3"
              label={{ value: 'Analysis', position: 'top', fontSize: 9, fill: 'var(--indigo)' }}
            />
          )}
          <Area
            type="monotone"
            dataKey="close"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradId})`}
            dot={false}
            activeDot={{ r: 4, fill: color, strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
