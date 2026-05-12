import styles from './ConfigPanel.module.css'

const PROVIDERS = ['openai', 'anthropic', 'google', 'groq', 'xai', 'deepseek']

const MODELS = {
  openai: {
    deep: ['gpt-4o', 'gpt-4o-mini', 'o1', 'o3-mini', 'gpt-5.4'],
    quick: ['gpt-4o-mini', 'gpt-4o', 'o1-mini', 'gpt-5.4-mini'],
  },
  anthropic: {
    deep: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'],
    quick: ['claude-haiku-4-5-20251001', 'claude-sonnet-4-6', 'claude-opus-4-7'],
  },
  google: {
    deep: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-1.5-pro'],
    quick: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-1.5-flash'],
  },
  groq: {
    deep: ['llama3-groq-70b-8192-tool-use-preview', 'llama-3.3-70b-versatile', 'llama-3.1-70b-versatile'],
    quick: ['llama3-groq-8b-8192-tool-use-preview', 'llama3-groq-70b-8192-tool-use-preview', 'llama-3.1-8b-instant'],
  },
  xai: {
    deep: ['grok-3', 'grok-3-mini'],
    quick: ['grok-3-mini', 'grok-3'],
  },
  deepseek: {
    deep: ['deepseek-chat', 'deepseek-reasoner'],
    quick: ['deepseek-chat', 'deepseek-reasoner'],
  },
}

export default function ConfigPanel({ config, onChange, onRun, isRunning }) {
  const set = (key, val) => onChange(prev => ({ ...prev, [key]: val }))

  const models = MODELS[config.llm_provider] || MODELS.openai

  return (
    <section className={styles.panel}>
      <div className={styles.panelHeader}>
        <span className={styles.panelIcon}>⚡</span>
        <span className={styles.panelTitle}>New Analysis</span>
      </div>

      <div className={styles.grid}>
        <div className={styles.field}>
          <label className={styles.fieldLabel}>TICKER</label>
          <input
            className={styles.input}
            value={config.ticker}
            onChange={e => set('ticker', e.target.value.toUpperCase())}
            placeholder="NVDA"
            maxLength={10}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.fieldLabel}>DATE</label>
          <input
            type="date"
            className={styles.input}
            value={config.date}
            onChange={e => set('date', e.target.value)}
          />
        </div>

        <div className={styles.field}>
          <label className={styles.fieldLabel}>LLM PROVIDER</label>
          <select
            className={styles.select}
            value={config.llm_provider}
            onChange={e => {
              const p = e.target.value
              const m = MODELS[p] || MODELS.openai
              onChange(prev => ({
                ...prev,
                llm_provider: p,
                deep_think_llm: m.deep[0],
                quick_think_llm: m.quick[0],
              }))
            }}
          >
            {PROVIDERS.map(p => (
              <option key={p} value={p}>{p.toUpperCase()}</option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label className={styles.fieldLabel}>DEEP MODEL</label>
          <select
            className={styles.select}
            value={config.deep_think_llm}
            onChange={e => set('deep_think_llm', e.target.value)}
          >
            {models.deep.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label className={styles.fieldLabel}>QUICK MODEL</label>
          <select
            className={styles.select}
            value={config.quick_think_llm}
            onChange={e => set('quick_think_llm', e.target.value)}
          >
            {models.quick.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label className={styles.fieldLabel}>
            DEBATE ROUNDS&nbsp;
            <span className={styles.sliderVal}>{config.max_debate_rounds}</span>
          </label>
          <input
            type="range"
            min={1}
            max={5}
            className={styles.slider}
            value={config.max_debate_rounds}
            onChange={e => set('max_debate_rounds', Number(e.target.value))}
          />
        </div>
      </div>

      <div className={styles.footer}>
        <button
          className={styles.runBtn}
          onClick={onRun}
          disabled={isRunning || !config.ticker || !config.date}
        >
          {isRunning ? (
            <><span className={styles.spinner} />Analyzing…</>
          ) : (
            'Run Analysis'
          )}
        </button>
      </div>
    </section>
  )
}
