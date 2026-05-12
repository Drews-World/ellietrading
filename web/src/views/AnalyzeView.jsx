import { useState, useCallback, useEffect, useRef } from 'react'
import ConfigPanel from '../components/ConfigPanel'
import DiscoverPanel from '../components/DiscoverPanel'
import AgentFeed from '../components/AgentFeed'
import AgentDetailDrawer from '../components/AgentDetailDrawer'
import DecisionPanel from '../components/DecisionPanel'
import ResultPanel from '../components/ResultPanel'
import RunHistory from '../components/RunHistory'
import styles from './AnalyzeView.module.css'

const INITIAL_CONFIG = {
  ticker: 'NVDA',
  date: new Date().toISOString().split('T')[0],
  llm_provider: 'google',
  deep_think_llm: 'gemini-2.5-pro',
  quick_think_llm: 'gemini-2.5-flash',
  max_debate_rounds: 1,
}

export default function AnalyzeView() {
  const [config, setConfig] = useState(INITIAL_CONFIG)
  const [isRunning, setIsRunning] = useState(false)
  const [agents, setAgents] = useState({})
  const [activeAgent, setActiveAgent] = useState(null)
  const [statusMsg, setStatusMsg] = useState('')
  const [decision, setDecision] = useState(null)
  const [error, setError] = useState(null)
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [pendingRunId, setPendingRunId] = useState(() => sessionStorage.getItem('ta_pending_run_id'))
  const isRunningRef = useRef(false)
  const [history, setHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ta_history') || '[]') } catch { return [] }
  })

  const resetState = useCallback(() => {
    setAgents({})
    setActiveAgent(null)
    setStatusMsg('')
    setDecision(null)
    setError(null)
    setSelectedAgent(null)
    setPendingRunId(null)
    sessionStorage.removeItem('ta_pending_run_id')
  }, [])

  const saveToHistory = useCallback((entry) => {
    setHistory(prev => {
      const next = [entry, ...prev].slice(0, 50)
      localStorage.setItem('ta_history', JSON.stringify(next))
      return next
    })
  }, [])

  const handleEvent = useCallback((type, payload) => {
    if (type === 'run_started') {
      setPendingRunId(payload.run_id)
      sessionStorage.setItem('ta_pending_run_id', payload.run_id)
    } else if (type === 'status') {
      setStatusMsg(payload.message)
    } else if (type === 'agent_running') {
      setActiveAgent(payload.agent)
      setStatusMsg(`${payload.node} running…`)
      setAgents(prev => ({
        ...prev,
        [payload.agent]: { ...(prev[payload.agent] || {}), status: 'running', node: payload.node },
      }))
    } else if (type === 'agent_complete') {
      setAgents(prev => ({
        ...prev,
        [payload.agent]: { status: 'done', snippet: payload.snippet, report: payload.report, node: payload.node },
      }))
      setActiveAgent(null)
      setStatusMsg(`${payload.node} complete`)
    } else if (type === 'final_decision') {
      setDecision(payload)
      setActiveAgent(null)
      setStatusMsg('Analysis complete')
      setPendingRunId(null)
      sessionStorage.removeItem('ta_pending_run_id')
      saveToHistory({
        id: payload.run_id || Date.now(),
        ticker: payload.ticker,
        date: payload.date,
        signal: payload.signal,
        entry_price: payload.entry_price,
        ts: new Date().toISOString(),
      })
    } else if (type === 'error') {
      setError(payload.message)
    }
  }, [saveToHistory])

  // Keep a ref in sync so the visibility handler always sees the latest value
  useEffect(() => { isRunningRef.current = isRunning }, [isRunning])

  // Tab-switch recovery: when the user returns to this tab, poll for completed run
  useEffect(() => {
    if (!pendingRunId) return
    let cancelled = false

    const check = async () => {
      if (cancelled || !isRunningRef.current) return
      try {
        const r = await fetch(`/run/${pendingRunId}`)
        if (r.ok && !cancelled) {
          const run = await r.json()
          handleEvent('final_decision', {
            signal:      run.signal,
            reasoning:   run.reasoning,
            ticker:      run.ticker,
            date:        run.trade_date,
            entry_price: run.entry_price,
            run_id:      run.id,
          })
          setIsRunning(false)
        }
      } catch { /* run not saved yet — SSE is still streaming */ }
    }

    const onVisibility = () => {
      if (document.visibilityState === 'visible') check()
    }

    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [pendingRunId, handleEvent])

  const runAnalysis = useCallback(async (overrideConfig) => {
    resetState()
    setIsRunning(true)
    // Guard: if called as a button onClick, overrideConfig is a MouseEvent — ignore it
    const effectiveConfig = (overrideConfig?.ticker) ? overrideConfig : config

    try {
      const resp = await fetch('/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(effectiveConfig),
      })
      if (!resp.ok) {
        setError(`HTTP ${resp.status}: ${await resp.text()}`)
        return
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop()

        let eventType = 'message'
        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            const raw = line.slice(5).trim()
            if (!raw) continue
            try { handleEvent(eventType, JSON.parse(raw)) } catch { /* ignore */ }
            eventType = 'message'
          }
        }
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setIsRunning(false)
    }
  }, [config, resetState, handleEvent])

  const handleDiscoverAnalyze = useCallback((ticker) => {
    const newConfig = { ...config, ticker }
    setConfig(newConfig)
    runAnalysis(newConfig)
  }, [config, runAnalysis])

  return (
    <div className={[styles.layout, decision && styles.layoutWide].filter(Boolean).join(' ')}>
      <div className={styles.left}>
        <ConfigPanel config={config} onChange={setConfig} onRun={runAnalysis} isRunning={isRunning} />
        <DiscoverPanel config={config} onAnalyze={handleDiscoverAnalyze} isRunning={isRunning} />
        <AgentFeed
          agents={agents}
          activeAgent={activeAgent}
          statusMsg={statusMsg}
          isRunning={isRunning}
          onSelectAgent={setSelectedAgent}
          selectedAgent={selectedAgent}
        />
        {error && <DecisionPanel decision={null} error={error} />}
      </div>

      <div className={[styles.right, decision && styles.rightWide].filter(Boolean).join(' ')}>
        {decision
          ? <ResultPanel decision={decision} />
          : <RunHistory
              history={history}
              onClear={() => { setHistory([]); localStorage.removeItem('ta_history') }}
              onLoad={(h) => setConfig(prev => ({ ...prev, ticker: h.ticker, date: h.date }))}
            />
        }
        {decision && (
          <div style={{ marginTop: 14 }}>
            <RunHistory
              history={history}
              onClear={() => { setHistory([]); localStorage.removeItem('ta_history') }}
              onLoad={(h) => setConfig(prev => ({ ...prev, ticker: h.ticker, date: h.date }))}
            />
          </div>
        )}
      </div>

      {selectedAgent && agents[selectedAgent] && (
        <AgentDetailDrawer
          agentId={selectedAgent}
          data={agents[selectedAgent]}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  )
}
