import { useState, useEffect, useRef } from 'react'
import styles from './AgentFeed.module.css'

/* ── Sprite asset paths ───────────────────────────────────────── */
const NPC_BASE    = '/spriteassets/craftpix-891167-blacksmith-herbalist-hunter-jeweler-free-npc-character-pack'
const GOLEM_BASE  = '/spriteassets/craftpix-891123-free-golems-chibi-2d-game-sprites'
const WRAITH_BASE = '/spriteassets/craftpix-net-563568-free-wraith-tiny-style-2d-sprites/PNG'
const BOSS_BASE   = '/spriteassets/craftpix-net-907874-free-top-down-boss-character-4-direction-pack'

const pad = n => String(n).padStart(3, '0')

/* ── Per-character animation configs ─────────────────────────── */
function makeNpc(name) {
  const b = `${NPC_BASE}/${name}/PNG/PNG Sequences`
  return {
    idle:    { frames: 30, url: i => `${b}/Idle/0_${name}_Idle_${pad(i)}.png` },
    working: { frames: 30, url: i => `${b}/Communication/0_${name}_Communication_${pad(i)}.png` },
    done:    { frames: 30, url: i => `${b}/Joy/0_${name}_Joy_${pad(i)}.png` },
  }
}

function makeGolem(n) {
  const b = `${GOLEM_BASE}/Golem_${n}/PNG/PNG Sequences`
  return {
    idle:    { frames: 18, url: i => `${b}/Idle/0_Golem_Idle_${pad(i)}.png` },
    working: { frames: 24, url: i => `${b}/Walking/0_Golem_Walking_${pad(i)}.png` },
    done:    { frames: 18, url: i => `${b}/Idle Blinking/0_Golem_Idle Blinking_${pad(i)}.png` },
  }
}

function makeWraith(nn) {
  const b = `${WRAITH_BASE}/Wraith_${nn}/PNG Sequences`
  const w = `Wraith_${nn}`
  return {
    idle:    { frames: 12, url: i => `${b}/Idle/${w}_Idle_${pad(i)}.png` },
    working: { frames: 18, url: i => `${b}/Casting Spells/${w}_Casting Spells_${pad(i)}.png` },
    done:    { frames: 12, url: i => `${b}/Idle Blink/${w}_Idle Blinking_${pad(i)}.png` },
  }
}

function makeBoss(boss) {
  const b = `${BOSS_BASE}/${boss}/PNG/PNG Sequences`
  return {
    idle:    { frames: 16, url: i => `${b}/Front - Idle/Front - Idle_${pad(i)}.png` },
    working: { frames: 20, url: i => `${b}/Front - Walking/Front - Walking_${pad(i)}.png` },
    done:    { frames: 16, url: i => `${b}/Front - Idle Blinking/Front - Idle Blinking_${pad(i)}.png` },
  }
}

/* ── Codename → animation config ─────────────────────────────── */
const SPRITE_CONFIGS = {
  marcus: makeNpc('Blacksmith'),    // Market Analyst   → data-grinding craftsman
  sam:    makeNpc('Herbalist'),     // Sentiment Analyst → reads the room
  nova:   makeNpc('Hunter'),        // News Analyst      → tracks stories
  fiona:  makeNpc('Jeweler'),       // Fundamentals      → finds the gems
  bull:   makeGolem('1'),           // Bull Researcher   → big & bullish
  bear:   makeWraith('01'),         // Bear Researcher   → dark & skeptical
  rex:    makeGolem('2'),           // Research Manager  → overseer golem
  tara:   makeGolem('3'),           // Trader            → action golem
  axel:   makeWraith('02'),         // Aggressive Risk   → dark energy
  cara:   makeWraith('03'),         // Conservative Risk → cautious wraith
  niko:   makeBoss('Giant Goblin'), // Neutral Risk      → imposing middleman
  pm:     makeBoss('Viking Leader'),// Portfolio Manager → the boss
}

/* ── Agent definitions ─────────────────────────────────────────── */
const AGENTS = [
  { id: 'market',           codename: 'marcus', name: 'Marcus',  role: 'Market Analyst',        icon: '📊', color: '#0891b2', bg: '#ecfeff' },
  { id: 'social',           codename: 'sam',    name: 'Sam',     role: 'Sentiment Analyst',     icon: '📡', color: '#7c3aed', bg: '#f5f3ff' },
  { id: 'news',             codename: 'nova',   name: 'Nova',    role: 'News Analyst',          icon: '📰', color: '#d97706', bg: '#fffbeb' },
  { id: 'fundamentals',     codename: 'fiona',  name: 'Fiona',   role: 'Fundamentals Analyst',  icon: '📈', color: '#059669', bg: '#ecfdf5' },
  { id: 'bull_researcher',  codename: 'bull',   name: 'Bruno',   role: 'Bull Researcher',       icon: '🐂', color: '#059669', bg: '#ecfdf5' },
  { id: 'bear_researcher',  codename: 'bear',   name: 'Bea',     role: 'Bear Researcher',       icon: '🐻', color: '#dc2626', bg: '#fef2f2' },
  { id: 'research_manager', codename: 'rex',    name: 'Rex',     role: 'Research Manager',      icon: '🔬', color: '#0891b2', bg: '#ecfeff' },
  { id: 'trader',           codename: 'tara',   name: 'Tara',    role: 'Trader',                icon: '⚡', color: '#d97706', bg: '#fffbeb' },
  { id: 'aggressive',       codename: 'axel',   name: 'Axel',    role: 'Risk: Aggressive',      icon: '🔥', color: '#dc2626', bg: '#fef2f2' },
  { id: 'conservative',     codename: 'cara',   name: 'Cara',    role: 'Risk: Conservative',    icon: '🛡️', color: '#7c3aed', bg: '#f5f3ff' },
  { id: 'neutral',          codename: 'niko',   name: 'Niko',    role: 'Risk: Neutral',         icon: '⚖️', color: '#2563eb', bg: '#eff6ff'  },
  { id: 'portfolio_manager',codename: 'pm',     name: 'The PM',  role: 'Portfolio Manager',     icon: '💼', color: '#0891b2', bg: '#ecfeff' },
]

const AGENT_MAP = Object.fromEntries(AGENTS.map(a => [a.id, a]))

const ACTIVITY = {
  market:           { working: 'Scanning price history & technicals…', done: 'Market report ready' },
  social:           { working: 'Reading Reddit & StockTwits…',         done: 'Sentiment report ready' },
  news:             { working: 'Scanning headlines & press…',          done: 'News report ready' },
  fundamentals:     { working: 'Pulling SEC filings & earnings…',      done: 'Fundamentals report ready' },
  bull_researcher:  { working: 'Building the bull case…',              done: 'Bull thesis complete' },
  bear_researcher:  { working: 'Building the bear case…',              done: 'Bear thesis complete' },
  research_manager: { working: 'Reviewing debate & judging…',          done: 'Research decision made' },
  trader:           { working: 'Forming trade plan…',                  done: 'Trade plan ready' },
  aggressive:       { working: 'Stress-testing risk…',                 done: 'Aggressive view ready' },
  conservative:     { working: 'Evaluating downside…',                 done: 'Conservative view ready' },
  neutral:          { working: 'Balancing risk/reward…',               done: 'Neutral view ready' },
  portfolio_manager:{ working: 'Making the final call…',               done: 'Decision delivered' },
}

const DATA_DESK    = ['market', 'social', 'news', 'fundamentals']
const DEBATE_AGENTS= ['bull_researcher', 'bear_researcher']
const BACK_OFFICE  = ['research_manager', 'trader']
const RISK_DESK    = ['aggressive', 'conservative', 'neutral']
const CEO_SUITE    = ['portfolio_manager']

export default function AgentFeed({ agents, activeAgent, statusMsg, isRunning, onSelectAgent, selectedAgent }) {
  const bullData = agents['bull_researcher']
  const bearData = agents['bear_researcher']
  const debateActive = bullData || bearData

  return (
    <section className={styles.floor}>
      {/* ── Floor header ── */}
      <div className={styles.floorHeader}>
        <div className={styles.floorTitle}>
          <span className={styles.floorIcon}>🏢</span>
          <span>Operations Floor</span>
        </div>
        <div className={styles.floorStatus}>
          {isRunning && <span className={styles.runningDot} />}
          {statusMsg
            ? <span className={styles.statusText}>{statusMsg}</span>
            : <span className={styles.statusHint}>Click a completed desk to read the full report</span>
          }
        </div>
      </div>

      <div className={styles.floorBody}>

        {/* ══ DATA COLLECTION WING ══ */}
        <FloorSection label="Data Collection Wing">
          <div className={styles.deskRow}>
            {DATA_DESK.map(id => (
              <Workstation key={id} agent={AGENT_MAP[id]} data={agents[id]}
                isSelected={selectedAgent === id}
                onClick={() => agents[id]?.status === 'done' && onSelectAgent?.(id)} />
            ))}
          </div>
        </FloorSection>

        {/* ══ CONFERENCE ROOM ══ */}
        <FloorSection label="Conference Room — Research & Debate">
          <div className={styles.conferenceRoom}>
            <ConferenceTable
              bullAgent={AGENT_MAP['bull_researcher']} bullData={bullData}
              bearAgent={AGENT_MAP['bear_researcher']} bearData={bearData}
              isDebateActive={!!debateActive}
              onSelectBull={() => bullData?.status === 'done' && onSelectAgent?.('bull_researcher')}
              onSelectBear={() => bearData?.status === 'done' && onSelectAgent?.('bear_researcher')}
              bullSelected={selectedAgent === 'bull_researcher'}
              bearSelected={selectedAgent === 'bear_researcher'}
            />
            <div className={styles.backOffice}>
              {BACK_OFFICE.map(id => (
                <Workstation key={id} agent={AGENT_MAP[id]} data={agents[id]}
                  compact
                  isSelected={selectedAgent === id}
                  onClick={() => agents[id]?.status === 'done' && onSelectAgent?.(id)} />
              ))}
            </div>
          </div>
        </FloorSection>

        {/* ══ RISK DESK + CEO SUITE ══ */}
        <div className={styles.bottomRow}>
          <FloorSection label="Risk Desk" flex>
            <div className={styles.deskRow}>
              {RISK_DESK.map(id => (
                <Workstation key={id} agent={AGENT_MAP[id]} data={agents[id]}
                  compact
                  isSelected={selectedAgent === id}
                  onClick={() => agents[id]?.status === 'done' && onSelectAgent?.(id)} />
              ))}
            </div>
          </FloorSection>

          <FloorSection label="CEO Suite" ceo>
            {CEO_SUITE.map(id => (
              <Workstation key={id} agent={AGENT_MAP[id]} data={agents[id]}
                ceo
                isSelected={selectedAgent === id}
                onClick={() => agents[id]?.status === 'done' && onSelectAgent?.(id)} />
            ))}
          </FloorSection>
        </div>

      </div>
    </section>
  )
}

/* ── Floor section wrapper ────────────────────────────────────── */
function FloorSection({ label, children, flex, ceo }) {
  return (
    <div className={[styles.section, flex && styles.sectionFlex, ceo && styles.sectionCeo].filter(Boolean).join(' ')}>
      <div className={styles.sectionLabel}>{label}</div>
      {children}
    </div>
  )
}

/* ── Individual workstation ───────────────────────────────────── */
function Workstation({ agent, data, isSelected, onClick, compact, ceo }) {
  const status   = data?.status || 'idle'
  const isActive = status === 'running'
  const isDone   = status === 'done'
  const activity = ACTIVITY[agent.id]
  const actText  = isActive ? activity?.working : isDone ? activity?.done : 'On standby'

  return (
    <div
      className={[
        styles.desk,
        compact && styles.deskCompact,
        ceo     && styles.deskCeo,
        isActive && styles.deskActive,
        isDone   && styles.deskDone,
        isSelected && styles.deskSelected,
        isDone   && styles.deskClickable,
      ].filter(Boolean).join(' ')}
      style={{ '--agent-color': agent.color, '--agent-bg': agent.bg }}
      onClick={isDone ? onClick : undefined}
    >
      {/* Animated character sprite */}
      <SpriteAnimation codename={agent.codename} state={status} />

      {/* Desk info */}
      <div className={styles.deskInfo}>
        <div className={styles.deskName}>{agent.name}</div>
        <div className={styles.deskRole}>{agent.role}</div>
        <div className={[styles.deskActivity, isActive && styles.deskActivityLive].filter(Boolean).join(' ')}>
          {isActive && <span className={styles.activityDot} />}
          {isDone   && <span className={styles.checkmark}>✓</span>}
          <span>{actText}</span>
        </div>
      </div>

      {/* Active: scan line */}
      {isActive && <div className={styles.deskScanBar}><div className={styles.deskScanFill} /></div>}

      {/* Done: snippet */}
      {isDone && data?.snippet && (
        <p className={styles.deskSnippet}>{data.snippet}</p>
      )}

      {isDone && <span className={styles.deskViewHint}>View report ↗</span>}
    </div>
  )
}

/* ── Conference table (Bull vs Bear) ─────────────────────────── */
function ConferenceTable({ bullAgent, bullData, bearAgent, bearData,
  isDebateActive, onSelectBull, onSelectBear, bullSelected, bearSelected }) {

  const bullStatus = bullData?.status || 'idle'
  const bearStatus = bearData?.status || 'idle'
  const bullActive = bullStatus === 'running'
  const bearActive = bearStatus === 'running'
  const bullDone   = bullStatus === 'done'
  const bearDone   = bearStatus === 'done'

  return (
    <div className={[styles.confTable, isDebateActive && styles.confTableActive].join(' ')}>
      <div className={styles.confLabel}>
        {isDebateActive
          ? (bullActive || bearActive) ? '🔴 Live Debate' : '✅ Debate Complete'
          : 'Awaiting Analysts'}
      </div>

      <div className={styles.tableLayout}>
        {/* Bull side */}
        <div
          className={[styles.debater, styles.debaterBull, bullDone && styles.debaterClickable, bullSelected && styles.debaterSelected].filter(Boolean).join(' ')}
          onClick={bullDone ? onSelectBull : undefined}
        >
          <SpriteAnimation codename="bull" state={bullStatus} large />
          <div className={styles.debaterName}>{bullAgent.name}</div>
          <div className={styles.debaterRole}>Bull Researcher</div>
          {bullActive && <div className={styles.speakingBubble}>Building the case…</div>}
          {bullDone && bullData?.snippet && (
            <div className={[styles.speechBubble, styles.speechBubbleBull].join(' ')}>
              {bullData.snippet}
            </div>
          )}
        </div>

        {/* Conference table graphic */}
        <div className={styles.tableCenter}>
          <div className={styles.tableTop} />
          <div className={styles.tableVs}>VS</div>
          <div className={styles.tableBottom} />
        </div>

        {/* Bear side */}
        <div
          className={[styles.debater, styles.debaterBear, bearDone && styles.debaterClickable, bearSelected && styles.debaterSelected].filter(Boolean).join(' ')}
          onClick={bearDone ? onSelectBear : undefined}
        >
          <SpriteAnimation codename="bear" state={bearStatus} large />
          <div className={styles.debaterName}>{bearAgent.name}</div>
          <div className={styles.debaterRole}>Bear Researcher</div>
          {bearActive && <div className={styles.speakingBubble}>Building the case…</div>}
          {bearDone && bearData?.snippet && (
            <div className={[styles.speechBubble, styles.speechBubbleBear].join(' ')}>
              {bearData.snippet}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Animated sprite component ────────────────────────────────────
   Cycles through PNG frame sequences at ~10 fps.
   state: 'idle' | 'running' | 'done'
   large: boolean (conference room debater = larger size)
────────────────────────────────────────────────────────────────── */
function SpriteAnimation({ codename, state, large }) {
  const config   = SPRITE_CONFIGS[codename]
  const animKey  = state === 'running' ? 'working' : state === 'done' ? 'done' : 'idle'
  const anim     = config?.[animKey] || config?.idle

  const [frame, setFrame] = useState(0)
  const frameRef = useRef(0)
  const prevKey  = useRef(`${codename}_${animKey}`)

  // Reset frame counter when the character or animation changes
  useEffect(() => {
    const key = `${codename}_${animKey}`
    if (prevKey.current !== key) {
      prevKey.current = key
      frameRef.current = 0
      setFrame(0)
    }
  }, [codename, animKey])

  // Advance frames at 10fps
  useEffect(() => {
    if (!anim) return
    const id = setInterval(() => {
      frameRef.current = (frameRef.current + 1) % anim.frames
      setFrame(frameRef.current)
    }, 100)
    return () => clearInterval(id)
  }, [anim])

  const size = large ? 64 : 48

  if (!anim) {
    // Fallback: emoji placeholder if config is missing
    return (
      <div style={{
        width: size, height: size, borderRadius: 6,
        background: '#f1f5f9', display: 'flex', alignItems: 'center',
        justifyContent: 'center', fontSize: large ? 28 : 22, flexShrink: 0,
      }}>❓</div>
    )
  }

  return (
    <img
      src={encodeURI(anim.url(frame))}
      width={size}
      height={size}
      className={styles.spriteImg}
      alt=""
      draggable={false}
    />
  )
}
