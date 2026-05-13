import { useState, useEffect, useRef } from 'react'
import styles from './PasswordModal.module.css'

export default function PasswordModal({ onSuccess, onClose }) {
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const inputRef = useRef(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!password.trim()) return
    setLoading(true)
    setError('')
    try {
      const r = await fetch('/auth/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (r.ok) {
        sessionStorage.setItem('ellie_auth', '1')
        onSuccess()
      } else {
        setError('Incorrect password.')
        setPassword('')
        inputRef.current?.focus()
      }
    } catch {
      setError('Could not reach server.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <div className={styles.logo}>
          <span className={styles.logoIcon}>◈</span>
          <span className={styles.logoText}>ELLIE</span>
        </div>
        <p className={styles.subtitle}>Owner access required</p>

        <form className={styles.form} onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            className={styles.input}
            type="password"
            placeholder="Password"
            value={password}
            onChange={e => { setPassword(e.target.value); setError('') }}
            disabled={loading}
            autoComplete="current-password"
          />
          {error && <p className={styles.error}>{error}</p>}
          <button className={styles.btn} type="submit" disabled={loading || !password.trim()}>
            {loading ? 'Checking…' : 'Sign In'}
          </button>
        </form>

        <button className={styles.cancelLink} onClick={onClose}>
          ← Back to portfolio
        </button>
      </div>
    </div>
  )
}
