import { useState, useEffect } from 'react'
import styles from './Header.module.css'

export default function Header() {
  const [time, setTime] = useState(getTime())

  useEffect(() => {
    const iv = setInterval(() => setTime(getTime()), 1000)
    return () => clearInterval(iv)
  }, [])

  return (
    <header className={styles.header}>
      <div className={styles.left}>
        <div className={styles.logo}>
          <span className={styles.logoE}>E</span>
        </div>
        <div className={styles.brand}>
          <span className={styles.brandName}>ELLIE Trading</span>
          <span className={styles.brandSub}>Multi-Agent Intelligence Platform</span>
        </div>
      </div>

      <div className={styles.right}>
        <div className={styles.liveChip}>
          <span className={styles.liveDot} />
          <span>Live</span>
        </div>
        <span className={styles.clock}>{time}</span>
        <span className={styles.version}>v0.2.4</span>
      </div>
    </header>
  )
}

function getTime() {
  return new Date().toLocaleTimeString('en-US', {
    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
