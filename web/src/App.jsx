import { useState, useCallback, useEffect } from 'react'
import styles from './App.module.css'
import Header from './components/Header'
import NavSidebar from './components/NavSidebar'
import PasswordModal from './components/PasswordModal'
import PublicView from './views/PublicView'
import AnalyzeView from './views/AnalyzeView'
import PortfolioView from './views/PortfolioView'
import SettingsView from './views/SettingsView'
import BrokerageView from './views/BrokerageView'
import FundView from './views/FundView'
import OperationsView from './views/OperationsView'

function useAuth() {
  const [authed, setAuthed] = useState(() => !!sessionStorage.getItem('ellie_auth'))
  const login  = () => setAuthed(true)
  const logout = () => { sessionStorage.removeItem('ellie_auth'); setAuthed(false) }
  return { authed, login, logout }
}

export default function App() {
  const { authed, login } = useAuth()
  const [showModal, setShowModal]   = useState(false)
  const [activeView, setActiveView] = useState('analyze')
  const [monitorUnread, setMonitorUnread] = useState(0)

  useEffect(() => {
    if (!authed) return
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
  }, [authed])

  // ── Public view (unauthenticated) ────────────────────────────────────────
  if (!authed) {
    return (
      <>
        <PublicView onLoginClick={() => setShowModal(true)} />
        {showModal && (
          <PasswordModal
            onSuccess={() => { login(); setShowModal(false) }}
            onClose={() => setShowModal(false)}
          />
        )}
      </>
    )
  }

  // ── Full app (authenticated) ──────────────────────────────────────────────
  return (
    <div className={styles.app}>
      <Header activeView={activeView} onNav={setActiveView} />
      <div className={styles.body}>
        <NavSidebar activeView={activeView} onNav={setActiveView} monitorUnread={monitorUnread} />
        <main className={styles.main}>
          {activeView === 'analyze'    && <AnalyzeView />}
          {activeView === 'portfolio'  && <PortfolioView />}
          {activeView === 'operations' && <OperationsView />}
          {activeView === 'fund'       && <FundView />}
          {activeView === 'brokerage'  && <BrokerageView />}
          {activeView === 'settings'   && <SettingsView />}
        </main>
      </div>
    </div>
  )
}
