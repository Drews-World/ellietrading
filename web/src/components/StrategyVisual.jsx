import styles from './StrategyVisual.module.css'

const CONFIG = {
  Buy: {
    color: 'green', label: 'BUY', glyph: '↑',
    meaning:  'Analysts believe this stock is undervalued or set to grow.',
    action:   'Consider buying shares. You make money if the price goes up.',
    risk:     'If the price drops, you lose money. Only invest what you can afford to lose.',
    stopHint: (entry) => entry ? `If it falls below $${(entry * 0.95).toFixed(2)} (−5%), consider selling to limit losses.` : null,
  },
  Overweight: {
    color: 'green', label: 'BUY', glyph: '↑',
    meaning:  'Analysts think this stock will outperform the market.',
    action:   'Consider buying shares or increasing your current position.',
    risk:     'Stocks can go down even when analysts are bullish. Diversify.',
    stopHint: (entry) => entry ? `Consider a stop-loss around $${(entry * 0.95).toFixed(2)} (−5%).` : null,
  },
  Hold: {
    color: 'yellow', label: 'HOLD', glyph: '→',
    meaning:  'Analysts see no strong reason to buy more or sell right now.',
    action:   'If you own it, keep it. If you don\'t, wait for a clearer signal.',
    risk:     'The stock could move either way — monitor it and check back later.',
    stopHint: () => null,
  },
  Sell: {
    color: 'red', label: 'SELL', glyph: '↓',
    meaning:  'Analysts believe this stock is overvalued or facing headwinds.',
    action:   'Consider selling shares you own to avoid further losses.',
    risk:     'If you short this stock, you profit if it falls — but risk is unlimited if it rises.',
    stopHint: (entry) => entry ? `If it rises above $${(entry * 1.05).toFixed(2)} (+5%), consider cutting losses.` : null,
  },
  Underweight: {
    color: 'red', label: 'SELL', glyph: '↓',
    meaning:  'Analysts think this stock will underperform the broader market.',
    action:   'Reduce your position or avoid buying. Better opportunities exist elsewhere.',
    risk:     'Stock could still rise even with a bearish signal — nothing is guaranteed.',
    stopHint: () => null,
  },
}

function BetaRisk({ beta }) {
  if (beta == null) return null
  const level = beta > 1.5 ? 'High' : beta < 0.8 ? 'Low' : 'Medium'
  const pct   = Math.min(100, (beta / 2.5) * 100)
  const cls   = beta > 1.5 ? styles.riskHigh : beta < 0.8 ? styles.riskLow : styles.riskMed
  return (
    <div className={styles.riskRow}>
      <span className={styles.riskLabel}>Volatility Risk</span>
      <div className={styles.riskBar}>
        <div className={[styles.riskFill, cls].join(' ')} style={{ width: `${pct}%` }} />
      </div>
      <span className={[styles.riskLevel, cls].join(' ')}>{level}</span>
    </div>
  )
}

export default function StrategyVisual({ signal, entryPrice, metrics }) {
  const cfg = CONFIG[signal]
  if (!cfg) return null

  const stopHint = cfg.stopHint(entryPrice)
  const beta = metrics?.beta

  return (
    <div className={[styles.wrap, styles[`wrap_${cfg.color}`]].join(' ')}>
      <div className={styles.top}>
        <div className={styles.signalBlock}>
          <span className={[styles.glyph, styles[`glyph_${cfg.color}`]].join(' ')}>{cfg.glyph}</span>
          <div>
            <div className={[styles.signalLabel, styles[`label_${cfg.color}`]].join(' ')}>{cfg.label}</div>
            {entryPrice && (
              <div className={styles.entryPrice}>at ${entryPrice.toFixed(2)}</div>
            )}
          </div>
        </div>
        <div className={styles.sections}>
          <InfoRow icon="💡" title="What this means" text={cfg.meaning} />
          <InfoRow icon="✅" title="What to do" text={cfg.action} />
          <InfoRow icon="⚠️" title="Key risk" text={cfg.risk} />
          {stopHint && <InfoRow icon="🛑" title="Stop-loss suggestion" text={stopHint} />}
        </div>
      </div>
      <BetaRisk beta={beta} />
    </div>
  )
}

function InfoRow({ icon, title, text }) {
  return (
    <div className={styles.infoRow}>
      <span className={styles.infoIcon}>{icon}</span>
      <div>
        <span className={styles.infoTitle}>{title}: </span>
        <span className={styles.infoText}>{text}</span>
      </div>
    </div>
  )
}
