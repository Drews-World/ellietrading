import styles from './NavSidebar.module.css'

const NAV = [
  { id: 'analyze',    icon: '⚡', label: 'Analyze' },
  { id: 'portfolio',  icon: '💼', label: 'Portfolio' },
  { id: 'operations', icon: '🏢', label: 'Ops' },
  { id: 'fund',       icon: '🏦', label: 'Fund' },
  { id: 'brokerage',  icon: '📊', label: 'Broker' },
  { id: 'settings',   icon: '⚙', label: 'Settings' },
]

export default function NavSidebar({ activeView, onNav, monitorUnread = 0 }) {
  return (
    <nav className={styles.nav}>
      {NAV.map(item => (
        <button
          key={item.id}
          className={[styles.item, activeView === item.id && styles.active].filter(Boolean).join(' ')}
          onClick={() => onNav(item.id)}
          title={item.label}
        >
          <span className={styles.iconWrap}>
            <span className={styles.icon}>{item.icon}</span>
            {item.id === 'monitor' && monitorUnread > 0 && (
              <span className={styles.dot} />
            )}
          </span>
          <span className={styles.label}>{item.label}</span>
        </button>
      ))}
    </nav>
  )
}
