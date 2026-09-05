import { useState, useCallback, useEffect, useRef } from 'react'
import {
  Zap, Square, PauseCircle, RotateCcw,
  ArrowDown, Server, ChevronRight, Check,
  Activity, Package, Send,
} from 'lucide-react'
import PageHeader from '../components/layout/PageHeader.jsx'
import { telemetryClient } from '../api/telemetry.js'
import '../dashboard.css'

/* ─── Spike options ──────────────────────────────────────────── */
const SPIKE_OPTIONS = [
  { amount: 1,  label: 'Single Spike',  eventsPerSpike: 12_000 },
  { amount: 5,  label: 'Burst Spikes',  eventsPerSpike: 14_000 },
  { amount: 10, label: 'Wave Spikes',   eventsPerSpike: 15_500 },
  { amount: 20, label: 'Max Burst',     eventsPerSpike: 18_000 },
]

/* ─── Payload flow steps ─────────────────────────────────────── */
const FLOW_STEPS = [
  { id: 'normal',   label: 'Normal\nPayload',   icon: Package },
  { id: 'increase', label: 'Increase\nPayload',  icon: ArrowDown },
  { id: 'spike',    label: 'Spike\nGenerated',   icon: Zap },
  { id: 'sent',     label: 'Sent to\nMachine 2', icon: Send },
]

/* ─── Helpers ────────────────────────────────────────────────── */
function fmt(n) {
  return n >= 1_000_000
    ? (n / 1_000_000).toFixed(2) + 'M'
    : n >= 1_000
    ? n.toLocaleString()
    : String(n)
}

/* ─── Spike Control Card ─────────────────────────────────────── */
function SpikeControlCard({ selected, onSelect, spikeCount, onInject, onPause, onReset, isPaused, isSurging }) {
  const [flashInject, setFlashInject] = useState(false)

  function handleInject() {
    setFlashInject(true)
    onInject()
    setTimeout(() => setFlashInject(false), 600)
  }

  return (
    <div className="card" style={{ flex: '1 1 0', minWidth: 0 }}>
      {/* Card header */}
      <div className="card-header">
        <div className="card-header-left">
          <Zap size={13} style={{ color: 'var(--color-indigo-500)' }} strokeWidth={2} />
          <span className="card-title">Select Number of Spikes</span>
        </div>
        <span className={`sim-mode-chip ${isSurging ? 'spike' : 'normal'}`}>
          <span className={`status-dot ${isSurging ? 'status-dot-live' : 'status-dot-live-green'}`}
            style={{ width: 5, height: 5 }} />
          {isSurging ? 'SPIKE' : 'NORMAL'}
        </span>
      </div>

      {/* Spike option buttons */}
      <div className="card-body" style={{ paddingBottom: 'var(--space-4)' }}>
        <div className="spike-btn-group">
          {SPIKE_OPTIONS.map(opt => (
            <button
              key={opt.amount}
              className={`spike-btn${selected === opt.amount ? ' selected' : ''}`}
              onClick={() => onSelect(opt.amount)}
              id={`spike-opt-${opt.amount}`}
            >
              <span className="spike-btn-amount">+{opt.amount}</span>
              <span className="spike-btn-label">{opt.label}</span>
            </button>
          ))}
        </div>

        {/* Current selection readout */}
        <div className="spike-selected-readout" style={{ marginTop: 'var(--space-3)' }}>
          <span className="spike-selected-number">{spikeCount}</span>
          <span className="spike-selected-unit">spikes selected</span>
        </div>
      </div>

      {/* Secondary controls */}
      <div style={{ padding: '0 var(--space-5) var(--space-4)' }}>
        <div className="control-btns" style={{ marginBottom: 'var(--space-3)' }}>
          <button
            className="btn btn-secondary"
            onClick={onPause}
            id="btn-pause"
          >
            <PauseCircle size={13} strokeWidth={1.8} />
            {isPaused ? 'Resume' : 'Pause Simulation'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={onReset}
            id="btn-reset"
          >
            <RotateCcw size={13} strokeWidth={1.8} />
            Reset / Stop
          </button>
        </div>

        {/* Primary CTA */}
        <button
          className={`btn-inject${flashInject ? ' surging' : ''}`}
          onClick={handleInject}
          disabled={isPaused}
          id="btn-inject"
        >
          <Zap size={14} strokeWidth={2.5} />
          Inject Spikes Now
        </button>
      </div>
    </div>
  )
}

/* ─── Calculated / Baseline Card ─────────────────────────────── */
function CalculatedCard({ baseline, projected, selectedSpikes, eventsPerSpike }) {
  const multiplier = selectedSpikes > 1 ? (projected / baseline).toFixed(1) : '1.0'
  return (
    <div className="card" style={{ width: 220, flexShrink: 0 }}>
      <div className="card-header">
        <div className="card-header-left">
          <Activity size={13} style={{ color: 'var(--color-text-tertiary)' }} strokeWidth={1.8} />
          <span className="card-title">Calculated</span>
        </div>
      </div>

      <div className="calc-block">
        <div className="calc-row">
          <span className="calc-label">Current Baseline</span>
          <span className="calc-value">{fmt(baseline)}</span>
          <span className="calc-delta" style={{ color: 'var(--color-text-tertiary)' }}>events / sec</span>
        </div>

        <div className="calc-row">
          <span className="calc-label">After Injection</span>
          <span className="calc-value" style={{ color: 'var(--color-indigo-600)' }}>
            {fmt(projected)}
          </span>
          <span className="calc-delta up">
            ↑ {multiplier}× multiplier
          </span>
        </div>

        <div className="calc-row">
          <span className="calc-label">Events / Spike</span>
          <span className="calc-value" style={{ fontSize: 15 }}>
            {fmt(eventsPerSpike)}
          </span>
          <span className="calc-delta" style={{ color: 'var(--color-text-tertiary)' }}>
            synthetic events
          </span>
        </div>

        <div className="calc-row">
          <span className="calc-label">Surge Factor</span>
          <span className="calc-value" style={{ fontSize: 22, color: 'var(--color-indigo-600)' }}>
            ×{Math.min(20, selectedSpikes + 1)}
          </span>
          <span className="calc-delta" style={{ color: 'var(--color-text-tertiary)' }}>
            pipeline stress
          </span>
        </div>
      </div>
    </div>
  )
}

/* ─── Payload Flow Panel ─────────────────────────────────────── */
function PayloadFlowPanel({ activeStep }) {
  return (
    <div className="card">
      <div className="card-header">
        <div className="card-header-left">
          <Server size={13} style={{ color: 'var(--color-text-tertiary)' }} strokeWidth={1.8} />
          <span className="card-title">Payload Pipeline</span>
        </div>
        <span className="text-xs text-tertiary">Machine 1 → Machine 2</span>
      </div>

      <div className="payload-flow">
        {FLOW_STEPS.map((step, i) => {
          const stepIdx = FLOW_STEPS.findIndex(s => s.id === activeStep)
          const isActive = i === stepIdx
          const isCompleted = i < stepIdx
          const Icon = step.icon

          return (
            <div key={step.id} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
              <div className={`flow-step${isActive ? ' active' : ''}${isCompleted ? ' completed' : ''}`}
                style={{ flex: 1 }}>
                <div className="flow-step-icon">
                  {isCompleted
                    ? <Check size={13} strokeWidth={2.5} style={{ color: 'var(--color-success-text)' }} />
                    : <Icon size={13} strokeWidth={1.8}
                        style={{ color: isActive ? 'var(--color-indigo-500)' : 'var(--color-text-tertiary)' }} />
                  }
                </div>
                <span className="flow-step-label">
                  {step.label}
                </span>
              </div>

              {i < FLOW_STEPS.length - 1 && (
                <div className={`flow-connector${i < stepIdx ? ' active' : ''}`}>
                  <div className="flow-connector-arrow" />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ─── Payload Activity Panel ─────────────────────────────────── */
function PayloadActivityPanel({ events, payloadRate, injectedCount, totalSpikes, isSurging, isPaused }) {
  const activityLog = [
    {
      label: 'Synthetic Events Generated',
      value: fmt(events),
      dot: 'var(--color-indigo-500)',
      sub: 'total this session',
    },
    {
      label: 'Current Payload Rate',
      value: fmt(payloadRate) + ' /s',
      dot: isSurging ? 'var(--color-indigo-500)' : 'var(--color-success)',
      sub: isSurging ? 'surge active' : 'baseline',
    },
    {
      label: 'Spikes Injected',
      value: `${injectedCount} / ${totalSpikes}`,
      dot: injectedCount > 0 ? 'var(--color-indigo-400)' : 'var(--color-gray-300)',
      sub: 'this run',
    },
    {
      label: 'Simulation Status',
      value: isPaused ? 'PAUSED' : isSurging ? 'SURGING' : 'RUNNING',
      dot: isPaused ? 'var(--color-gray-400)' : isSurging ? 'var(--color-indigo-500)' : 'var(--color-success)',
      sub: 'Machine 1',
    },
  ]

  return (
    <div className="card">
      <div className="card-header">
        <div className="card-header-left">
          <span className={`status-dot ${isPaused ? 'status-dot-idle' : isSurging ? 'status-dot-live' : 'status-dot-live-green'}`} />
          <span className="card-title">Payload Activity</span>
        </div>
        <span className={`badge ${isSurging && !isPaused ? 'badge-indigo' : 'badge-gray'}`}>
          {isPaused ? 'Paused' : isSurging ? 'Generating' : 'Idle'}
        </span>
      </div>

      <div style={{ padding: 'var(--space-2) 0' }}>
        {activityLog.map(row => (
          <div className="activity-row" key={row.label}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', minWidth: 0 }}>
              <span className="activity-dot" style={{ background: row.dot, flexShrink: 0 }} />
              <div style={{ minWidth: 0 }}>
                <div className="text-sm text-secondary" style={{ lineHeight: 1.3 }}>{row.label}</div>
                <div className="text-xs text-tertiary">{row.sub}</div>
              </div>
            </div>
            <span className="text-sm font-semibold tabular-nums" style={{
              color: row.label === 'Simulation Status' && isSurging && !isPaused
                ? 'var(--color-indigo-600)'
                : 'var(--color-text-primary)',
              flexShrink: 0,
              marginLeft: 'var(--space-4)',
            }}>
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ─── Compact KPI Row ─────────────────────────────────────────── */
function KPIRow({ payloadRate, totalEvents, surgeMultiplier, isSurging }) {
  return (
    <div className="metrics-row">
      <div className="metric-tile">
        <div className="metric-tile-label">Payload Rate</div>
        <div className={`metric-tile-value ${isSurging ? 'accent' : ''} tabular-nums`}>
          {fmt(payloadRate)}
          <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-secondary)', marginLeft: 4 }}>/s</span>
        </div>
        <div className="metric-tile-sub">{isSurging ? '↑ surge active' : 'baseline'}</div>
      </div>

      <div className="metric-tile">
        <div className="metric-tile-label">Total Synthetic Events</div>
        <div className="metric-tile-value tabular-nums">{fmt(totalEvents)}</div>
        <div className="metric-tile-sub">generated this session</div>
      </div>

      <div className="metric-tile">
        <div className="metric-tile-label">Surge Multiplier</div>
        <div className={`metric-tile-value tabular-nums ${isSurging ? 'accent' : ''}`}>
          {surgeMultiplier}×
        </div>
        <div className="metric-tile-sub">pipeline stress factor</div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   LoadSpikerPage — Main Page with all state
═══════════════════════════════════════════════════════════════ */
const BASELINE_RATE = 8_400      // events/sec at rest
const TOTAL_SPIKE_BUDGET = 50
const INITIAL_INJECTED = 44
const INITIAL_EVENTS   = 720_000

export default function LoadSpikerPage() {
  /* ── State ──────────────────────────────────────────────────── */
  const [selectedAmount, setSelectedAmount] = useState(5)
  const [spikesInjected, setSpikesInjected] = useState(INITIAL_INJECTED)
  const [totalEvents, setTotalEvents]       = useState(INITIAL_EVENTS)
  const [payloadRate, setPayloadRate]       = useState(BASELINE_RATE)
  const [isSurging, setIsSurging]           = useState(false)
  const [isPaused, setIsPaused]             = useState(false)
  const [flowStep, setFlowStep]             = useState('normal')

  const surgeTimer = useRef(null)
  const tickTimer  = useRef(null)

  /* ── Derived values ─────────────────────────────────────────── */
  const selectedOption   = SPIKE_OPTIONS.find(o => o.amount === selectedAmount) ?? SPIKE_OPTIONS[1]
  const projectedRate    = Math.round(BASELINE_RATE * (1 + selectedAmount * 0.9))
  const surgeMultiplier  = isSurging ? Math.min(20, selectedAmount + 1) : 1
  const spikesRemaining  = TOTAL_SPIKE_BUDGET - spikesInjected

  /* ── Background tick (simulate live rate growth while surging) */
  useEffect(() => {
    if (isPaused) return
    if (isSurging) {
      tickTimer.current = setInterval(() => {
        setTotalEvents(n => n + Math.round(payloadRate / 10))
      }, 100)
    }
    return () => clearInterval(tickTimer.current)
  }, [isSurging, isPaused, payloadRate])

  /* ── Inject handler ─────────────────────────────────────────── */
  const handleInject = useCallback(() => {
    if (isPaused || spikesRemaining <= 0) return

    const addedSpikes = Math.min(selectedAmount, spikesRemaining)
    const addedEvents = addedSpikes * selectedOption.eventsPerSpike

    setSpikesInjected(n => Math.min(TOTAL_SPIKE_BUDGET, n + addedSpikes))
    setTotalEvents(n => n + addedEvents)
    setPayloadRate(projectedRate)
    setIsSurging(true)

    // Conceptual API link to Machine 2
    telemetryClient.triggerSpike(selectedAmount, addedEvents)

    /* Animate through flow steps */
    setFlowStep('increase')
    setTimeout(() => setFlowStep('spike'),    400)
    setTimeout(() => setFlowStep('sent'),     900)

    /* Ramp back to baseline after 3s */
    clearTimeout(surgeTimer.current)
    surgeTimer.current = setTimeout(() => {
      setIsSurging(false)
      setPayloadRate(BASELINE_RATE)
      setFlowStep('normal')
      telemetryClient.resetSpike()
    }, 3_000)
  }, [isPaused, spikesRemaining, selectedAmount, selectedOption, projectedRate])

  /* ── Pause/Resume ───────────────────────────────────────────── */
  const handlePause = useCallback(() => {
    setIsPaused(p => !p)
    if (!isPaused) {
      clearTimeout(surgeTimer.current)
    }
  }, [isPaused])

  /* ── Reset ──────────────────────────────────────────────────── */
  const handleReset = useCallback(() => {
    clearTimeout(surgeTimer.current)
    clearInterval(tickTimer.current)
    setSpikesInjected(0)
    setTotalEvents(0)
    setPayloadRate(BASELINE_RATE)
    setIsSurging(false)
    setIsPaused(false)
    setFlowStep('normal')
    setSelectedAmount(5)
    telemetryClient.resetSpike()
  }, [])

  /* ── Cleanup ────────────────────────────────────────────────── */
  useEffect(() => () => {
    clearTimeout(surgeTimer.current)
    clearInterval(tickTimer.current)
  }, [])

  /* ── Render ─────────────────────────────────────────────────── */
  return (
    <>
      {/* Page header with live counters */}
      <PageHeader
        spikesInjected={spikesInjected}
        spikesTotal={TOTAL_SPIKE_BUDGET}
        boostedEvents={totalEvents.toLocaleString()}
      />

      <div className="page" id="load-spiker-content" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>

        {/* ── KPI row ────────────────────────────────────────────── */}
        <KPIRow
          payloadRate={payloadRate}
          totalEvents={totalEvents}
          surgeMultiplier={surgeMultiplier}
          isSurging={isSurging}
        />

        {/* ── Main control area: control card + calculated card ─── */}
        <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'flex-start' }}>
          <SpikeControlCard
            selected={selectedAmount}
            onSelect={setSelectedAmount}
            spikeCount={selectedAmount}
            onInject={handleInject}
            onPause={handlePause}
            onReset={handleReset}
            isPaused={isPaused}
            isSurging={isSurging}
          />

          <CalculatedCard
            baseline={BASELINE_RATE}
            projected={projectedRate}
            selectedSpikes={selectedAmount}
            eventsPerSpike={selectedOption.eventsPerSpike}
          />
        </div>

        {/* ── Payload flow pipeline ─────────────────────────────── */}
        <PayloadFlowPanel activeStep={flowStep} />

        {/* ── Activity panel ───────────────────────────────────── */}
        <PayloadActivityPanel
          events={totalEvents}
          payloadRate={payloadRate}
          injectedCount={spikesInjected}
          totalSpikes={TOTAL_SPIKE_BUDGET}
          isSurging={isSurging}
          isPaused={isPaused}
        />

      </div>
    </>
  )
}
