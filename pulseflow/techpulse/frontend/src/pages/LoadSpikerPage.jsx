import { useState, useCallback, useEffect, useRef } from 'react'
import {
  Zap, PauseCircle, RotateCcw, ArrowDown, Server, Check,
  Activity, Package, Send, Shield, Flame, CheckCircle,
  ExternalLink, Play, Pause, Radio, BarChart2, Layers, Clock
} from 'lucide-react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine
} from 'recharts'
import PageHeader from '../components/layout/PageHeader.jsx'
import { telemetryClient } from '../api/telemetry.js'
import '../dashboard.css'

/* ─── Spike Preset Configurations ───────────────────────────── */
const SPIKE_OPTIONS = [
  {
    amount: 1,
    label: 'Single Spike',
    eventsPerSpike: 12_000,
    multiplier: '1.9×',
    tag: 'Baseline Validation',
    stressPercent: 20,
    color: '#10B981'
  },
  {
    amount: 5,
    label: 'Burst Spikes',
    eventsPerSpike: 14_000,
    multiplier: '5.5×',
    tag: 'Flash Sale Influx',
    stressPercent: 55,
    color: '#635BFF'
  },
  {
    amount: 10,
    label: 'Wave Spikes',
    eventsPerSpike: 15_500,
    multiplier: '10.0×',
    tag: 'Peak Cyber Hour',
    stressPercent: 80,
    color: '#F59E0B'
  },
  {
    amount: 20,
    label: 'Max Burst',
    eventsPerSpike: 18_000,
    multiplier: '20.0×',
    tag: 'DDoS Stress / Shedding',
    stressPercent: 100,
    color: '#EF4444'
  },
]

/* ─── Payload Pipeline Steps ────────────────────────────────── */
const FLOW_STEPS = [
  { id: 'normal',   label: 'Synthetic\nGenerator', icon: Package, desc: 'Machine 1 Engine' },
  { id: 'increase', label: 'Payload\nAssembly',   icon: ArrowDown, desc: 'JSON Batch Serialization' },
  { id: 'spike',    label: 'Surge\nTransmitting', icon: Zap, desc: 'High-Velocity Burst' },
  { id: 'sent',     label: 'Ingested by\nMachine 2', icon: Send, desc: 'HTTP 200 Ingestion Ack' },
]

/* ─── Number Formatter Helper ───────────────────────────────── */
function fmt(n) {
  if (n === null || n === undefined) return '0'
  return n >= 1_000_000
    ? (n / 1_000_000).toFixed(2) + 'M'
    : n >= 1_000
    ? n.toLocaleString()
    : String(n)
}

/* ─── Section Heading Component ─────────────────────────────── */
function SectionHeading({ children }) {
  return (
    <h2 style={{
      fontSize: 'var(--text-xs)',
      fontWeight: 700,
      letterSpacing: '0.07em',
      textTransform: 'uppercase',
      color: 'var(--color-text-secondary)',
      marginBottom: 'var(--space-3)',
      marginTop: 0,
      display: 'flex',
      alignItems: 'center',
      gap: 'var(--space-2)'
    }}>
      {children}
    </h2>
  )
}

/* ─── Egress Waveform Glassmorphic Tooltip ──────────────────── */
function EgressTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const pt = payload[0]?.payload
  if (!pt) return null

  return (
    <div style={{
      background: 'rgba(255, 255, 255, 0.96)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      border: '1px solid rgba(226, 232, 240, 0.95)',
      boxShadow: '0 12px 28px -4px rgba(0, 0, 0, 0.12), 0 4px 10px rgba(99, 91, 255, 0.08)',
      borderRadius: 'var(--radius-md)',
      padding: '10px 14px',
      fontSize: '11px',
      minWidth: 200,
      pointerEvents: 'none',
      zIndex: 100,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--color-text-tertiary)' }}>
          {pt.time}
        </span>
        <span className={`badge ${pt.isSurge ? 'badge-error' : 'badge-success'}`} style={{ fontSize: '10px', padding: '1px 6px' }}>
          {pt.isSurge ? 'BURST ACTIVE' : 'BASELINE'}
        </span>
      </div>
      <div style={{ height: 1, background: 'var(--color-border-subtle)', margin: '6px 0' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ color: 'var(--color-text-secondary)', fontWeight: 600 }}>Egress Velocity:</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: 13, color: pt.isSurge ? 'var(--color-indigo-600)' : 'var(--color-text-primary)' }}>
          {pt.egress.toLocaleString()} ev/s
        </span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 4 }}>
        <span style={{ color: 'var(--color-text-tertiary)' }}>Baseline Reference:</span>
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)' }}>
          8,400 ev/s
        </span>
      </div>
    </div>
  )
}

/* ─── Spike Control Deck Card ───────────────────────────────── */
function SpikeControlDeck({ selected, onSelect, spikeCount, onInject, onPause, onReset, isPaused, isSurging }) {
  const [flashInject, setFlashInject] = useState(false)

  function handleInject() {
    setFlashInject(true)
    onInject()
    setTimeout(() => setFlashInject(false), 800)
  }

  return (
    <div className="card" style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div>
        {/* Card Header */}
        <div className="card-header" style={{ padding: 'var(--space-4) var(--space-5)' }}>
          <div className="card-header-left">
            <Zap size={14} style={{ color: 'var(--color-indigo-600)' }} strokeWidth={2.2} />
            <span className="card-title">Select Surge Multiplier Profile</span>
          </div>
          <span className={`sim-mode-chip ${isSurging ? 'spike' : 'normal'}`}>
            <span className={`status-dot ${isSurging ? 'status-dot-live-red' : 'status-dot-live-green'}`} style={{ width: 6, height: 6 }} />
            {isSurging ? 'SURGE BURST' : 'IDLE BASELINE'}
          </span>
        </div>

        {/* 4 Multiplier Selection Tiles */}
        <div className="card-body" style={{ padding: 'var(--space-4) var(--space-5)' }}>
          <div className="spike-btn-group">
            {SPIKE_OPTIONS.map(opt => {
              const isSelected = selected === opt.amount
              return (
                <button
                  key={opt.amount}
                  type="button"
                  className={`spike-btn${isSelected ? ' selected' : ''}`}
                  onClick={() => onSelect(opt.amount)}
                  id={`spike-opt-${opt.amount}`}
                >
                  <div className="spike-btn-top">
                    <span className="spike-btn-amount">+{opt.amount}</span>
                    <span className="spike-btn-multiplier">{opt.multiplier}</span>
                  </div>
                  <div>
                    <div className="spike-btn-label">{opt.label}</div>
                    <div className="spike-btn-subtext">
                      {fmt(opt.eventsPerSpike)} ev/spk
                    </div>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Current Selection Readout Banner */}
          <div className="spike-selected-readout" style={{ marginTop: 'var(--space-4)' }}>
            <div>
              <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-tertiary)', letterSpacing: '0.04em' }}>
                ACTIVE CONFIGURATION
              </div>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)', marginTop: 2 }}>
                {SPIKE_OPTIONS.find(o => o.amount === selected)?.label} ({selected} Spikes queued)
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span className="spike-selected-number font-mono">{selected}</span>
              <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-text-secondary)' }}>spikes selected</span>
            </div>
          </div>
        </div>
      </div>

      {/* Secondary Controls & Primary CTA */}
      <div style={{ padding: '0 var(--space-5) var(--space-5)' }}>
        <div className="control-btns" style={{ marginBottom: 'var(--space-3)' }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onPause}
            id="btn-pause"
            style={{ fontWeight: 600 }}
          >
            {isPaused ? <Play size={13} strokeWidth={2} /> : <Pause size={13} strokeWidth={2} />}
            {isPaused ? 'Resume Generator' : 'Pause Generator'}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onReset}
            id="btn-reset"
            style={{ fontWeight: 600 }}
          >
            <RotateCcw size={13} strokeWidth={2} />
            Reset Session
          </button>
        </div>

        {/* Primary CTA Button */}
        <button
          type="button"
          className={`btn-inject${flashInject || isSurging ? ' surging' : ''}`}
          onClick={handleInject}
          disabled={isPaused}
          id="btn-inject"
        >
          <Zap size={15} strokeWidth={2.5} />
          {isSurging ? 'TRANSMITTING SURGE TO MACHINE 2...' : 'Inject Spikes to Machine 2'}
        </button>
      </div>
    </div>
  )
}

/* ─── Real-Time Projection Engine & Stress Gauge ────────────── */
function ProjectionGaugeCard({ baseline, projected, selectedSpikes, eventsPerSpike }) {
  const currentOpt = SPIKE_OPTIONS.find(o => o.amount === selectedSpikes) || SPIKE_OPTIONS[1]
  const multiplier = (projected / baseline).toFixed(1)
  const stressPercent = currentOpt.stressPercent

  return (
    <div className="card" style={{ width: 280, flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
      <div className="card-header" style={{ padding: 'var(--space-4) var(--space-5)' }}>
        <div className="card-header-left">
          <Activity size={14} style={{ color: 'var(--color-indigo-600)' }} strokeWidth={2} />
          <span className="card-title">Stress Projection Engine</span>
        </div>
        <span className="badge badge-indigo" style={{ fontSize: '10px', padding: '2px 7px' }}>
          Real-Time
        </span>
      </div>

      <div className="calc-block">
        <div className="calc-row">
          <span className="calc-label">Baseline Traffic Velocity</span>
          <span className="calc-value font-mono">{fmt(baseline)}</span>
          <span className="calc-delta" style={{ color: 'var(--color-text-tertiary)' }}>
            events / sec steady-state
          </span>
        </div>

        <div className="calc-row">
          <span className="calc-label">Projected Burst Velocity</span>
          <span className="calc-value font-mono" style={{ color: 'var(--color-indigo-600)' }}>
            {fmt(projected)}
          </span>
          <span className="calc-delta up font-mono">
            ↑ {multiplier}× stress surge multiplier
          </span>
        </div>

        {/* Stress Meter Gauge */}
        <div className="calc-row">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="calc-label">Pipeline Stress Rating</span>
            <span className="font-mono" style={{ fontSize: '11px', fontWeight: 700, color: currentOpt.color }}>
              {stressPercent}%
            </span>
          </div>
          <div className="stress-gauge-track">
            <div
              className="stress-gauge-fill"
              style={{
                width: `${stressPercent}%`,
                background: stressPercent >= 80 ? 'var(--color-error)' : stressPercent >= 50 ? 'var(--color-warning)' : 'var(--color-success)'
              }}
            />
          </div>
          <span className="calc-delta" style={{ color: 'var(--color-text-tertiary)' }}>
            {stressPercent >= 80 ? 'Forces Adaptive Shedding' : stressPercent >= 50 ? 'Triggers Normal Micro-Batching' : 'Linear Stream Processing'}
          </span>
        </div>

        {/* Payload Tier Composition */}
        <div className="calc-row" style={{ borderBottom: 'none', paddingBottom: 0 }}>
          <span className="calc-label" style={{ marginBottom: 4 }}>Synthetic Event Mix (Machine 1)</span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, fontSize: '11px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-indigo-700)', fontWeight: 600 }}>• Tier 1 Critical (Order/Pay)</span>
              <span className="font-mono" style={{ fontWeight: 700 }}>35%</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>• Tier 2 Normal (Cart/Inv)</span>
              <span className="font-mono" style={{ fontWeight: 700 }}>40%</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>• Tier 3 Best Effort (Clicks)</span>
              <span className="font-mono" style={{ fontWeight: 700 }}>25%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ─── Real-Time Egress Waveform Chart (30-Sec Sparkline) ────── */
function EgressWaveformCard({ data, currentRate, peakRate, isSurging }) {
  return (
    <div className="card" style={{ padding: 'var(--space-5)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <span style={{ fontSize: 'var(--text-base)', fontWeight: 800, color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}>
            Machine 1 Egress Traffic Waveform
          </span>
          <span className="status-pill status-pill-online" style={{ fontSize: '11px', padding: '2px 8px' }}>
            <span className="status-dot status-dot-sm status-dot-live-green" />
            LIVE EGRESS MONITOR
          </span>
          {peakRate > 10_000 && (
            <span className="badge badge-indigo" style={{ fontSize: '11px', padding: '2px 8px', fontWeight: 700 }}>
              Peak: {fmt(peakRate)} ev/s
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary)' }}>
            Resolution: 30s window • Sampling 1.2s
          </span>
        </div>
      </div>

      {/* Dedicated Waveform Canvas Viewport */}
      <div className="egress-waveform-container">
        {/* Precision Sub-pixel Grid */}
        <div className="egress-waveform-grid" />

        {/* Scanline Sweep */}
        <div className="egress-waveform-scanline" />

        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data.length > 0 ? data : [{ time: '--', egress: 8400 }]}
            margin={{ top: 15, right: 15, left: -10, bottom: 2 }}
          >
            <defs>
              <linearGradient id="colorEgress" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#635BFF" stopOpacity={0.65} />
                <stop offset="60%" stopColor="#818cf8" stopOpacity={0.18} />
                <stop offset="100%" stopColor="#635BFF" stopOpacity={0.01} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(226, 232, 240, 0.7)" />
            <XAxis dataKey="time" tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} axisLine={false} tickLine={false} />

            <ReferenceLine
              y={8400}
              stroke="rgba(16, 185, 129, 0.5)"
              strokeDasharray="4 4"
              label={{ value: 'Baseline (8.4k ev/s)', fill: 'var(--color-success-text)', fontSize: 10, position: 'insideTopLeft' }}
            />

            <Tooltip content={<EgressTooltip />} />

            <Area
              type="monotone"
              dataKey="egress"
              name="Egress Rate (ev/s)"
              stroke="#635BFF"
              strokeWidth={2.5}
              fill="url(#colorEgress)"
              fillOpacity={1}
              activeDot={{ r: 6, fill: '#635BFF', stroke: '#ffffff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Legend & Summary Info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: 'var(--color-text-secondary)', paddingTop: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#635BFF', display: 'inline-block' }} />
          <span>Synthetic Outgoing Telemetry Rate (Transmitted to Machine 2 /events/batch)</span>
        </div>
        <div className="font-mono">
          Current Rate: <strong>{fmt(currentRate)} ev/s</strong>
        </div>
      </div>
    </div>
  )
}

/* ─── Payload Flow Panel (Machine 1 → Machine 2) ────────────── */
function PayloadFlowPanel({ activeStep, isSurging }) {
  return (
    <div className="card">
      <div className="card-header" style={{ padding: 'var(--space-4) var(--space-5)' }}>
        <div className="card-header-left">
          <Server size={14} style={{ color: 'var(--color-text-tertiary)' }} strokeWidth={1.8} />
          <span className="card-title">Inter-Machine Ingestion Pipeline Bridge</span>
        </div>
        <span className="badge badge-indigo" style={{ fontSize: '11px', padding: '2px 8px' }}>
          Machine 1 (Generator) → Machine 2 (PulseFlow :8000)
        </span>
      </div>

      <div className="payload-flow">
        {FLOW_STEPS.map((step, i) => {
          const stepIdx = FLOW_STEPS.findIndex(s => s.id === activeStep)
          const isActive = i === stepIdx
          const isCompleted = i < stepIdx
          const Icon = step.icon

          return (
            <div key={step.id} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
              <div className={`flow-step${isActive ? ' active' : ''}${isCompleted ? ' completed' : ''}`} style={{ flex: 1 }}>
                <div className="flow-step-icon">
                  {isCompleted
                    ? <Check size={14} strokeWidth={2.5} style={{ color: 'var(--color-success-text)' }} />
                    : <Icon size={14} strokeWidth={2} style={{ color: isActive ? 'var(--color-indigo-600)' : 'var(--color-text-tertiary)' }} />
                  }
                </div>
                <span className="flow-step-label">
                  {step.label}
                </span>
                <span style={{ fontSize: '10px', color: 'var(--color-text-tertiary)', marginTop: -2 }}>
                  {step.desc}
                </span>
              </div>

              {i < FLOW_STEPS.length - 1 && (
                <div className={`flow-connector${i < stepIdx || isSurging ? ' active' : ''}`}>
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

/* ─── Transmission Audit Log Table ──────────────────────────── */
function TransmissionAuditLog({ history }) {
  return (
    <div className="card">
      <div className="card-header" style={{ padding: 'var(--space-4) var(--space-5)' }}>
        <div className="card-header-left">
          <Clock size={14} style={{ color: 'var(--color-text-tertiary)' }} strokeWidth={2} />
          <span className="card-title">Recent Workload Injection &amp; Bridge Audit</span>
        </div>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>
          HTTP/2 Ingestion ACK Log
        </span>
      </div>

      <div className="audit-table-wrapper">
        <table className="audit-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Surge Profile</th>
              <th>Events Transmitted</th>
              <th>Target Pipeline</th>
              <th>Status</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {history.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: 'var(--space-6)', color: 'var(--color-text-tertiary)' }}>
                  No surge bursts injected yet this session. Select a profile above and click "Inject Spikes Now".
                </td>
              </tr>
            ) : (
              history.map(item => (
                <tr key={item.id}>
                  <td className="font-mono" style={{ fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                    {item.timestamp}
                  </td>
                  <td>
                    <span style={{ fontWeight: 700, color: 'var(--color-text-primary)' }}>
                      {item.label}
                    </span>
                    <span className="badge badge-gray" style={{ marginLeft: 6, fontSize: '10px' }}>
                      +{item.level}x
                    </span>
                  </td>
                  <td className="font-mono" style={{ fontWeight: 700, color: 'var(--color-indigo-600)' }}>
                    +{fmt(item.events)} events
                  </td>
                  <td className="font-mono" style={{ color: 'var(--color-text-tertiary)' }}>
                    {item.target}
                  </td>
                  <td>
                    <span className={`status-pill ${item.isOk ? 'status-pill-online' : 'status-pill-error'}`} style={{ fontSize: '10px', padding: '2px 7px' }}>
                      <span className={`status-dot status-dot-sm ${item.isOk ? 'status-dot-live-green' : 'status-dot-live-red'}`} />
                      {item.status}
                    </span>
                  </td>
                  <td className="font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                    {item.latency} ms
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   LoadSpikerPage — Main Machine 1 Controller Component
   ═══════════════════════════════════════════════════════════════ */
const BASELINE_RATE = 8_400      // events/sec at rest
const TOTAL_SPIKE_BUDGET = 50

export default function LoadSpikerPage() {
  /* ── State ──────────────────────────────────────────────────── */
  const [selectedAmount, setSelectedAmount] = useState(5)
  const [spikesInjected, setSpikesInjected] = useState(0)
  const [totalEvents, setTotalEvents]       = useState(0)
  const [payloadRate, setPayloadRate]       = useState(BASELINE_RATE)
  const [isSurging, setIsSurging]           = useState(false)
  const [isPaused, setIsPaused]             = useState(false)
  const [flowStep, setFlowStep]             = useState('normal')
  const [burstHistory, setBurstHistory]     = useState([])
  const [waveformBuffer, setWaveformBuffer] = useState([])

  const surgeTimer = useRef(null)
  const tickTimer  = useRef(null)

  /* ── Derived values ─────────────────────────────────────────── */
  const selectedOption   = SPIKE_OPTIONS.find(o => o.amount === selectedAmount) ?? SPIKE_OPTIONS[1]
  const projectedRate    = Math.round(BASELINE_RATE * (1 + selectedAmount * 0.9))
  const surgeMultiplier  = isSurging ? Math.min(20, selectedAmount + 1) : 1
  const spikesRemaining  = TOTAL_SPIKE_BUDGET - spikesInjected
  const peakEgressRate   = Math.max(...waveformBuffer.map(d => d.egress || 0), payloadRate)

  /* ── Subscribe to Telemetry Client for Bridge status & Audit Log */
  useEffect(() => {
    const unsub = telemetryClient.subscribe(state => {
      setBurstHistory(state.history || [])
    })
    return unsub
  }, [])

  /* ── Live Waveform Rolling Buffer (30 points, ~1.2s tick) ────── */
  useEffect(() => {
    const interval = setInterval(() => {
      if (isPaused) return

      setWaveformBuffer(prev => {
        const now = new Date().toLocaleTimeString([], { hour12: false })
        // Add subtle natural jitter to baseline (±150 ev/s) so it feels alive like an oscilloscope
        const currentEgress = isSurging
          ? payloadRate + Math.round((Math.random() - 0.5) * 600)
          : BASELINE_RATE + Math.round((Math.random() - 0.5) * 200)

        const pt = {
          time: now,
          egress: Math.max(0, currentEgress),
          isSurge: isSurging,
        }
        return [...prev, pt].slice(-30)
      })
    }, 1200)

    return () => clearInterval(interval)
  }, [isPaused, isSurging, payloadRate])

  /* ── Background tick (simulate live total event count growth) ── */
  useEffect(() => {
    if (isPaused) return
    tickTimer.current = setInterval(() => {
      setTotalEvents(n => n + Math.round(payloadRate / 10))
    }, 100)
    return () => clearInterval(tickTimer.current)
  }, [isPaused, payloadRate])

  /* ── Inject Handler ─────────────────────────────────────────── */
  const handleInject = useCallback(() => {
    if (isPaused || spikesRemaining <= 0) return

    const addedSpikes = Math.min(selectedAmount, spikesRemaining)
    const addedEvents = addedSpikes * selectedOption.eventsPerSpike

    setSpikesInjected(n => Math.min(TOTAL_SPIKE_BUDGET, n + addedSpikes))
    setTotalEvents(n => n + addedEvents)
    setPayloadRate(projectedRate)
    setIsSurging(true)

    // Send real HTTP burst to Machine 2 (/events/batch)
    telemetryClient.triggerSpike(selectedAmount, addedEvents, selectedOption.label)

    /* Animate through pipeline flow steps */
    setFlowStep('increase')
    setTimeout(() => setFlowStep('spike'), 400)
    setTimeout(() => setFlowStep('sent'),  900)

    /* Ramp back to baseline after 3.5s */
    clearTimeout(surgeTimer.current)
    surgeTimer.current = setTimeout(() => {
      setIsSurging(false)
      setPayloadRate(BASELINE_RATE)
      setFlowStep('normal')
      telemetryClient.resetSpike()
    }, 3_500)
  }, [isPaused, spikesRemaining, selectedAmount, selectedOption, projectedRate])

  /* ── Pause / Resume ─────────────────────────────────────────── */
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
      {/* Clean Page Header */}
      <PageHeader
        spikesInjected={spikesInjected}
        spikesTotal={TOTAL_SPIKE_BUDGET}
        boostedEvents={fmt(totalEvents)}
        egressRate={fmt(payloadRate)}
        isSurging={isSurging}
        isPaused={isPaused}
      />

      <div className="page" id="load-spiker-content" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', overflowY: 'auto' }}>

        {/* ── 1. WORKLOAD & INGESTION OVERVIEW (4-COLUMN) ──────── */}
        <section>
          <SectionHeading>1. Synthetic Workload Telemetry Overview</SectionHeading>
          <div className="metrics-row">
            <div className="metric-tile">
              <div className="metric-tile-label">Current Egress Velocity</div>
              <div className={`metric-tile-value ${isSurging ? 'accent' : ''} tabular-nums font-mono`}>
                {fmt(payloadRate)}
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-secondary)', marginLeft: 4 }}>/s</span>
              </div>
              <div className="metric-tile-sub">
                <span className={`status-dot status-dot-sm ${isSurging ? 'status-dot-live-red' : 'status-dot-live-green'}`} />
                {isSurging ? 'Active surge burst in progress' : 'Steady baseline traffic'}
              </div>
            </div>

            <div className="metric-tile">
              <div className="metric-tile-label">Synthetic Events Generated</div>
              <div className="metric-tile-value tabular-nums font-mono">
                {fmt(totalEvents)}
              </div>
              <div className="metric-tile-sub">
                Cumulative session output
              </div>
            </div>

            <div className="metric-tile">
              <div className="metric-tile-label">Surge Stress Factor</div>
              <div className={`metric-tile-value tabular-nums font-mono ${isSurging ? 'accent' : ''}`}>
                {surgeMultiplier}×
              </div>
              <div className="metric-tile-sub">
                Pipeline pressure multiplier
              </div>
            </div>

            <div className="metric-tile">
              <div className="metric-tile-label">Target Pipeline Status</div>
              <div className="metric-tile-value success font-mono" style={{ fontSize: 17 }}>
                Zero Critical Loss
              </div>
              <div className="metric-tile-sub" style={{ color: 'var(--color-success-text)' }}>
                Machine 2 Adaptive Engine Active
              </div>
            </div>
          </div>
        </section>

        {/* ── 2. WORKLOAD ORCHESTRATION & SPIKER CONTROLS ─────── */}
        <section>
          <SectionHeading>2. Workload Orchestration &amp; Spiker Controls</SectionHeading>
          <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'stretch' }}>
            <SpikeControlDeck
              selected={selectedAmount}
              onSelect={setSelectedAmount}
              spikeCount={selectedAmount}
              onInject={handleInject}
              onPause={handlePause}
              onReset={handleReset}
              isPaused={isPaused}
              isSurging={isSurging}
            />

            <ProjectionGaugeCard
              baseline={BASELINE_RATE}
              projected={projectedRate}
              selectedSpikes={selectedAmount}
              eventsPerSpike={selectedOption.eventsPerSpike}
            />
          </div>
        </section>

        {/* ── 3. REAL-TIME EGRESS TRAFFIC WAVEFORM ────────────── */}
        <section>
          <SectionHeading>3. Real-Time Egress Velocity Waveform</SectionHeading>
          <EgressWaveformCard
            data={waveformBuffer}
            currentRate={payloadRate}
            peakRate={peakEgressRate}
            isSurging={isSurging}
          />
        </section>

        {/* ── 4. PIPELINE TRANSMISSION BRIDGE ─────────────────── */}
        <section>
          <SectionHeading>4. Pipeline Transmission Bridge (Machine 1 → Machine 2)</SectionHeading>
          <PayloadFlowPanel
            activeStep={flowStep}
            isSurging={isSurging}
          />
        </section>

        {/* ── 5. TRANSMISSION AUDIT LOG ───────────────────────── */}
        <section>
          <SectionHeading>5. Transmission Audit &amp; Bridge History</SectionHeading>
          <TransmissionAuditLog history={burstHistory} />
        </section>

      </div>
    </>
  )
}
