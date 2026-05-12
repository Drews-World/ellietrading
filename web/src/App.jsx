import { useState, useCallback, useEffect } from 'react'
import styles from './App.module.css'
import Header from './components/Header'
import NavSidebar from './components/NavSidebar'
import AnalyzeView from './views/AnalyzeView'
import PortfolioView from './views/PortfolioView'
import SettingsView from './views/SettingsView'
import MonitorView from './views/MonitorView'
import ScoutView from './views/ScoutView'

export default function App() {
  const [activeView, setActiveView] = useState('analyze')
  const [monitorUnread, setMonitorUnread] = useState(0)

  useEffect(() => {
    const poll = async () => {
      try {
        const r = await fetch('/monitor')
        const d = await r.json()
        setMonitorUnread((d.alerts || []).filter(a => !a.read).length)
      } catch { /* ignore */ }
    }
    poll()
    const iv = setInterval(poll, 60000)
    return () => clearInterval(iv)
  }, [])

  return (
    <div className={styles.app}>
      <Header activeView={activeView} onNav={setActiveView} />
      <div className={styles.body}>
        <NavSidebar activeView={activeView} onNav={setActiveView} monitorUnread={monitorUnread} />
        <main className={styles.main}>
          {activeView === 'analyze'   && <AnalyzeView />}
          {activeView === 'portfolio' && <PortfolioView />}
          {activeView === 'monitor'   && <MonitorView />}
          {activeView === 'scout'     && <ScoutView />}
          {activeView === 'settings'  && <SettingsView />}
        </main>
      </div>
    </div>
  )
}
