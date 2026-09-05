import { useState, useCallback, useEffect, useRef } from 'react'
import {
  Zap, RotateCcw, ArrowDown, Server, Check,
  Activity, Package, Send, Shield, Flame, CheckCircle,
  ExternalLink, Play, Pause, Radio, BarChart2, Layers, Clock, AlertTriangle, RefreshCw,
  Sliders
} from 'lucide-react'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine
} from 'recharts'
import PageHeader from '../components/layout/PageHeader.jsx'
import { telemetryClient } from '../api/telemetry.js'
import '../dashboard.css'

/* ─── Synthetic Event Mix Presets & Helpers ───────────────────── */
const MIX_PRESETS = [
  {
    id: 'standard',
    name: 'Standard Browsing',
    badge: 'Baseline Flow',
    desc: 'Normal consumer browsing with heavy click & log streams, moderate cart, low checkout.',
    crit: 10,
    norm: 20,
    best: 70,
    color: '#10B981',
  },
  {
    id: 'flash_sale',
    name: 'Flash Sale Rush',
    badge: 'High Cart & Orders',
    desc: 'High volume checkout rush; cart additions and instant orders surge.',
    crit: 35,
    norm: 40,
    best: 25,
    color: '#635BFF',
  },
  {
    id: 'payment_stress',
    name: 'Critical Checkout Surge',
    badge: 'Max SLA Stress',
    desc: 'Heavy order & payment traffic; strictly stress-tests zero-critical-loss guarantee.',
    crit: 60,
    norm: 25,
    best: 15,
    color: '#F59E0B',
  },
  {
    id: 'click_flood',
    name: 'Telemetry Flood / DDoS',
    badge: 'Best-Effort Surge',
    desc: 'Low-priority click and log tsunami; validates shed and deferral behavior under pressure.',
    crit: 5,
    norm: 10,
    best: 85,
    color: '#EF4444',
  },
]

function computeTierPcts(dist) {
  if (!dist) return { crit: 10, norm: 20, best: 70 }
  const total = Object.values(dist).reduce((a, b) => a + Number(b || 0), 0) || 1
  const critVal = (Number(dist.ORDER || 0) + Number(dist.PAYMENT || 0))
  const normVal = (Number(dist.CART_ADD || 0) + Number(dist.INVENTORY_UPDATE || 0))
  const bestVal = (Number(dist.CLICK || 0) + Number(dist.PAGE_VIEW || 0) + Number(dist.LOG || 0))

  const crit = Math.round((critVal / total) * 100)
  const norm = Math.round((normVal / total) * 100)
  const best = Math.max(0, 100 - crit - norm)
  return { crit, norm, best }
}

function tiersToDistribution(crit, norm, best) {
  const sum = (crit + norm + best) || 100
  const c = (crit / sum) * 100
  const n = (norm / sum) * 100
  const b = (best / sum) * 100

  return {
    ORDER: Number(((c * 0.5)).toFixed(1)),
    PAYMENT: Number(((c * 0.5)).toFixed(1)),
    CART_ADD: Number(((n * 0.6)).toFixed(1)),
    INVENTORY_UPDATE: Number(((n * 0.4)).toFixed(1)),
    PAGE_VIEW: Number(((b * 0.45)).toFixed(1)),
    CLICK: Number(((b * 0.40)).toFixed(1)),
    LOG: Number(((b * 0.15)).toFixed(1)),
  }
}

/* ─── Preset Spike Multiplier Profiles ────────────────────────── */
const PRESET_OPTIONS = [
  {
    amount: 1,
    label: '1× Normal Baseline',
    multiplier: '1×',
    targetRate: 100,
    tag: 'Baseline Continuous',
    stressPercent: 15,
    color: '#10B981',
  },
  {
    amount: 5,
    label: '5× Flash Sale Influx',
    multiplier: '5×',
    targetRate: 500,
    tag: 'Flash Sale Traffic',
    stressPercent: 45,
    color: '#635BFF',
  },
  {
    amount: 10,
    label: '10× Peak Cyber Hour',
    multiplier: '10×',
    targetRate: 1000,
    tag: 'Peak Cyber Load',
    stressPercent: 75,
    color: '#F59E0B',
  },
  {
    amount: 20,
    label: '20× Max Stress Surge',
    multiplier: '20×',
    targetRate: 2000,
    tag: 'DDoS / Extreme Stress',
    stressPercent: 100,
    color: '#EF4444',
  },
]

/* ─── Payload Pipeline Bridge Steps ─────────────────────────── */
const FLOW_STEPS = [
  { id: 'normal',   label: 'Synthetic\nProducer', icon: Package, desc: 'Machine 1 EventFactory' },
  { id: 'increase', label: 'Payload\nAssembly',   icon: ArrowDown, desc: 'EventBatch JSON' },
  { id: 'spike',    label: 'HTTP/REST\nEgress',    icon: Zap, desc: 'POST /events/batch' },
  { id: 'sent',     label: 'Ingested by\nMachine 2', icon: Send, desc: 'FastAPI :8000 Ack' },
]

/* ─── Number Formatter Helper ───────────────────────────────── */
function fmt(n) {
  if (n === null || n === undefined) return '0'
  return n >= 1_000_000
    ? (n / 1_000_000).toFixed(2) + 'M'
    : n >= 1_000
    ? n.toLocaleString()
    : String(Math.round(n))
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
      minWidth: 220,
      pointerEvents: 'none',
      zIndex: 100,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--color-text-tertiary)' }}>
          {pt.time}
        </span>
        <span className={`badge ${pt.isSurge ? 'badge-error' : 'badge-success'}`} style={{ fontSize: '10px', padding: '1px 6px' }}>
          {pt.isSurge ? 'SURGE BURST ACTIVE' : 'STEADY BASELINE'}
        </span>
      </div>
      <div style={{ height: 1, background: 'var(--color-border-subtle)', margin: '6px 0' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ color: 'var(--color-text-secondary)', fontWeight: 600 }}>Measured Egress:</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: 13, color: pt.isSurge ? 'var(--color-indigo-600)' : 'var(--color-text-primary)' }}>
          {pt.egress.toLocaleString()} ev/s
        </span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 4 }}>
        <span style={{ color: 'var(--color-text-tertiary)' }}>Target Rate:</span>
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-secondary)' }}>
          {pt.target.toLocaleString()} ev/s
        </span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 4 }}>
        <span style={{ color: 'var(--color-text-tertiary)' }}>Baseline Reference:</span>
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-success-text)' }}>
          100 ev/s
        </span>
      </div>
    </div>
  )
}

/* ─── Real-Time Egress Waveform Card ────────────────────────── */
function EgressWaveformCard({ data, currentRate, targetRate, peakRate, isSurging }) {
  const windowMax = Math.max(...data.map(d => d.egress || 0), 100)
  const isSurgeActive = isSurging || currentRate > 200 || windowMax > 200

  // Calculate dynamic Y-axis domain:
  // Steady baseline sits comfortably at 40% height [0, 250]
  // Surges scale up with headroom so peak velocity is clearly visible
  const yDomainMax = isSurgeActive
    ? Math.max(300, Math.ceil((windowMax * 1.25) / 100) * 100)
    : 250

  return (
    <div className="card" style={{ padding: 'var(--space-5)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <span style={{ fontSize: 'var(--text-base)', fontWeight: 800, color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}>
            Machine 1 Live Egress Waveform (Authoritative Stream)
          </span>
          <span className={`status-pill ${isSurgeActive ? 'status-pill-error' : 'status-pill-online'}`} style={{ fontSize: '11px', padding: '2px 8px' }}>
            <span className={`status-dot status-dot-sm ${isSurgeActive ? 'status-dot-live-red' : 'status-dot-live-green'}`} />
            {isSurgeActive ? 'SURGE BURST ACTIVE' : 'STEADY BASELINE'}
          </span>
          {isSurgeActive ? (
            <span className="badge badge-indigo" style={{ fontSize: '11px', padding: '2px 8px', fontWeight: 700 }}>
              Peak: {fmt(peakRate)} ev/s
            </span>
          ) : (
            <span className="badge" style={{ fontSize: '11px', padding: '2px 8px', fontWeight: 600, background: 'rgba(16, 185, 129, 0.1)', color: 'var(--color-success-text)' }}>
              Nominal Baseline: 100 ev/s
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <span style={{ fontSize: '12px', color: 'var(--color-text-tertiary)' }}>
            Resolution: 30s window • Sampling 1.0s • Target: {fmt(targetRate)} ev/s
          </span>
        </div>
      </div>

      {/* Waveform Canvas */}
      <div className="egress-waveform-container" style={{ minHeight: 220 }}>
        <div className="egress-waveform-grid" />
        <div className="egress-waveform-scanline" />

        <ResponsiveContainer width="100%" height={220}>
          <AreaChart
            data={data.length > 0 ? data : [{ time: '--', egress: 100, target: 100 }]}
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
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }}
              axisLine={false}
              tickLine={false}
              interval={4}
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }}
              axisLine={false}
              tickLine={false}
              domain={[0, yDomainMax]}
              allowDataOverflow={false}
            />

            <ReferenceLine
              y={100}
              stroke="rgba(16, 185, 129, 0.7)"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{ value: 'Baseline (100 ev/s)', fill: 'var(--color-success-text)', fontSize: 10, position: 'insideTopLeft' }}
            />

            <Tooltip content={<EgressTooltip />} />

            <Area
              type="monotone"
              dataKey="egress"
              name="Measured Egress (ev/s)"
              stroke="#635BFF"
              strokeWidth={2.5}
              fill="url(#colorEgress)"
              fillOpacity={1}
              isAnimationActive={false}
              activeDot={{ r: 5, fill: '#635BFF', stroke: '#ffffff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Legend & Summary Info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: 'var(--color-text-secondary)', paddingTop: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#635BFF', display: 'inline-block' }} />
          <span>Real Measured Transmission Rate (HTTP Batches to Machine 2 /events/batch)</span>
        </div>
        <div className="font-mono">
          Measured Velocity: <strong style={{ color: currentRate > 200 ? 'var(--color-indigo-600)' : 'var(--color-text-primary)' }}>{fmt(currentRate)} ev/s</strong> • Target: <strong>{fmt(targetRate)} ev/s</strong>
        </div>
      </div>
    </div>
  )
}

/* ─── Payload Flow Panel ────────────────────────────────────── */
function PayloadFlowPanel({ activeStep, isSurging, latencyMs }) {
  return (
    <div className="card">
      <div className="card-header" style={{ padding: 'var(--space-4) var(--space-5)' }}>
        <div className="card-header-left">
          <Server size={14} style={{ color: 'var(--color-text-tertiary)' }} strokeWidth={1.8} />
          <span className="card-title">Inter-Machine Ingestion Pipeline Bridge</span>
        </div>
        <span className="badge badge-indigo" style={{ fontSize: '11px', padding: '2px 8px' }}>
          Machine 1 (Generator) → HTTP REST → Machine 2 (PulseFlow :8000) • RTT {latencyMs}ms
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
          HTTP/1.1 Batch Delivery Log
        </span>
      </div>

      <div className="audit-table-wrapper">
        <table className="audit-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Operation / Profile</th>
              <th>Target Rate</th>
              <th>Workload Volume</th>
              <th>Target Pipeline</th>
              <th>Status</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {history.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 'var(--space-6)', color: 'var(--color-text-tertiary)' }}>
                  Continuous baseline traffic active (~100 ev/s). Select a preset or custom spike above to stress the pipeline.
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
                  </td>
                  <td className="font-mono" style={{ color: 'var(--color-indigo-600)', fontWeight: 700 }}>
                    {typeof item.targetRate === 'number' ? `${item.targetRate.toLocaleString()} ev/s` : item.targetRate}
                  </td>
                  <td className="font-mono" style={{ color: 'var(--color-text-primary)' }}>
                    {typeof item.events === 'number' ? `+${fmt(item.events)} ev` : item.events}
                  </td>
                  <td className="font-mono" style={{ color: 'var(--color-text-tertiary)', fontSize: 11 }}>
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
export default function LoadSpikerPage() {
  /* ── Authoritative State from Python Generator ──────────────── */
  const [telemetry, setTelemetry] = useState({
    running: true,
    state: 'BASELINE',
    baselineRate: 100,
    currentTargetRate: 100,
    measuredRate: 100,
    multiplier: 1.0,
    spikeMode: 'NONE',
    spikeLabel: 'Steady Baseline',
    remainingSeconds: null,
    eventsTarget: null,
    eventsSpiked: 0,
    eventsGenerated: 0,
    eventsAttempted: 0,
    eventsDelivered: 0,
    eventsFailed: 0,
    batchesGenerated: 0,
    batchesDelivered: 0,
    errors: 0,
    pulseflowConnected: true,
    generatorConnected: true,
    latencyMs: 1.2,
    history: [],
    distribution: {
      CLICK: 30,
      PAGE_VIEW: 25,
      LOG: 15,
      CART_ADD: 10,
      INVENTORY_UPDATE: 10,
      ORDER: 5,
      PAYMENT: 5,
    },
  })

  /* ── Local Form Inputs ───────────────────────────────────────── */
  const [selectedPreset, setSelectedPreset] = useState(5)
  const [customRate, setCustomRate] = useState(5000)
  const [customDuration, setCustomDuration] = useState(15)
  const [runEvents, setRunEvents] = useState(10000)
  const [runMaxRate, setRunMaxRate] = useState(2500)
  const [activeTab, setActiveTab] = useState('preset') // 'preset' | 'custom' | 'count' | 'mix'
  const [flowStep, setFlowStep] = useState('normal')
  const [waveformBuffer, setWaveformBuffer] = useState(() => {
    const pts = []
    const now = Date.now()
    for (let i = 29; i >= 0; i--) {
      const d = new Date(now - i * 1000)
      pts.push({
        time: d.toLocaleTimeString([], { hour12: false }),
        egress: 100,
        target: 100,
        isSurge: false,
      })
    }
    return pts
  })
  const [isPaused, setIsPaused] = useState(false)
  const [validationMsg, setValidationMsg] = useState('')

  const latestTelemetryRef = useRef(telemetry)
  const lastTickTimeRef = useRef(Date.now())

  /* ── Synthetic Event Mix State ───────────────────────────────── */
  const [customCrit, setCustomCrit] = useState(10)
  const [customNorm, setCustomNorm] = useState(20)
  const [customBest, setCustomBest] = useState(70)
  const [selectedMixPreset, setSelectedMixPreset] = useState('standard')
  const [mixStatusMsg, setMixStatusMsg] = useState('')
  const [isApplyingMix, setIsApplyingMix] = useState(false)
  const [mixSpikeRate, setMixSpikeRate] = useState('2500')
  const [mixSpikeDuration, setMixSpikeDuration] = useState('20')
  const [isFiringMixSpike, setIsFiringMixSpike] = useState(false)
  const hasInitializedMixRef = useRef(false)
  const debounceApplyTimerRef = useRef(null)

  /* ── Compute Current Live Tier Percentages ────────────────────── */
  const currentTierPcts = computeTierPcts(telemetry.distribution)

  /* ── Sync slider state from authoritative distribution on startup ONLY ── */
  useEffect(() => {
    if (telemetry.distribution && !hasInitializedMixRef.current) {
      hasInitializedMixRef.current = true
      const p = computeTierPcts(telemetry.distribution)
      setCustomCrit(p.crit)
      setCustomNorm(p.norm)
      setCustomBest(p.best)
      if (telemetry.distributionPreset && telemetry.distributionPreset !== 'custom') {
        setSelectedMixPreset(telemetry.distributionPreset)
      } else {
        const matched = MIX_PRESETS.find(m => m.crit === p.crit && m.norm === p.norm && m.best === p.best)
        setSelectedMixPreset(matched ? matched.id : 'custom')
      }
    }
  }, [telemetry.distribution, telemetry.distributionPreset])

  /* ── Auto-Balancing Slider Handlers (Sum Always 100%) ─────────── */
  const handleCritChange = useCallback((newVal) => {
    const val = Math.max(0, Math.min(100, Number(newVal) || 0))
    setSelectedMixPreset('custom')
    const rem = 100 - val
    const curOther = (customNorm + customBest) || 1
    const newNorm = Math.round(rem * (customNorm / curOther))
    const newBest = rem - newNorm
    setCustomCrit(val)
    setCustomNorm(newNorm)
    setCustomBest(newBest)

    // Debounced live sync to backend generator
    clearTimeout(debounceApplyTimerRef.current)
    debounceApplyTimerRef.current = setTimeout(async () => {
      const dist = tiersToDistribution(val, newNorm, newBest)
      await telemetryClient.updateDistribution(dist, 'custom', 'Custom Workload Mix')
    }, 450)
  }, [customNorm, customBest])

  const handleNormChange = useCallback((newVal) => {
    const val = Math.max(0, Math.min(100, Number(newVal) || 0))
    setSelectedMixPreset('custom')
    const rem = 100 - val
    const curOther = (customCrit + customBest) || 1
    const newCrit = Math.round(rem * (customCrit / curOther))
    const newBest = rem - newCrit
    setCustomCrit(newCrit)
    setCustomNorm(val)
    setCustomBest(newBest)

    // Debounced live sync to backend generator
    clearTimeout(debounceApplyTimerRef.current)
    debounceApplyTimerRef.current = setTimeout(async () => {
      const dist = tiersToDistribution(newCrit, val, newBest)
      await telemetryClient.updateDistribution(dist, 'custom', 'Custom Workload Mix')
    }, 450)
  }, [customCrit, customBest])

  const handleBestChange = useCallback((newVal) => {
    const val = Math.max(0, Math.min(100, Number(newVal) || 0))
    setSelectedMixPreset('custom')
    const rem = 100 - val
    const curOther = (customCrit + customNorm) || 1
    const newCrit = Math.round(rem * (customCrit / curOther))
    const newNorm = rem - newCrit
    setCustomCrit(newCrit)
    setCustomNorm(newNorm)
    setCustomBest(val)

    // Debounced live sync to backend generator
    clearTimeout(debounceApplyTimerRef.current)
    debounceApplyTimerRef.current = setTimeout(async () => {
      const dist = tiersToDistribution(newCrit, newNorm, val)
      await telemetryClient.updateDistribution(dist, 'custom', 'Custom Workload Mix')
    }, 450)
  }, [customCrit, customNorm])

  const applyMixPreset = useCallback(async (presetId) => {
    clearTimeout(debounceApplyTimerRef.current)
    const p = MIX_PRESETS.find(x => x.id === presetId)
    if (!p) return
    setSelectedMixPreset(p.id)
    setCustomCrit(p.crit)
    setCustomNorm(p.norm)
    setCustomBest(p.best)
    setIsApplyingMix(true)
    const dist = tiersToDistribution(p.crit, p.norm, p.best)
    const res = await telemetryClient.updateDistribution(dist, p.id, p.name)
    setIsApplyingMix(false)
    if (res.ok) {
      setMixStatusMsg(`Applied "${p.name}" (${p.crit}% Critical, ${p.norm}% Normal, ${p.best}% Best Effort)`)
      setTimeout(() => setMixStatusMsg(''), 4000)
    } else {
      setValidationMsg(res.error || 'Failed to update synthetic mix.')
    }
  }, [])

  const applyCustomMix = useCallback(async () => {
    clearTimeout(debounceApplyTimerRef.current)
    setIsApplyingMix(true)
    setSelectedMixPreset('custom')
    const dist = tiersToDistribution(customCrit, customNorm, customBest)
    const res = await telemetryClient.updateDistribution(dist, 'custom', 'Custom User-Tuned Mix')
    setIsApplyingMix(false)
    if (res.ok) {
      setMixStatusMsg(`Custom mix active: ${customCrit}% Critical, ${customNorm}% Normal, ${customBest}% Best Effort`)
      setTimeout(() => setMixStatusMsg(''), 4000)
    } else {
      setValidationMsg(res.error || 'Failed to update synthetic mix.')
    }
  }, [customCrit, customNorm, customBest])

  const handleFireMixSpike = useCallback(async (e) => {
    if (e) e.preventDefault()
    clearTimeout(debounceApplyTimerRef.current)
    const rate = Number(mixSpikeRate)
    const dur = Number(mixSpikeDuration)
    if (!rate || rate <= 0 || isNaN(rate)) {
      setValidationMsg('Please enter a valid target rate (ev/s)')
      return
    }
    if (!dur || dur <= 0 || isNaN(dur)) {
      setValidationMsg('Please enter a valid surge duration (seconds)')
      return
    }
    setValidationMsg('')
    setIsFiringMixSpike(true)
    const dist = tiersToDistribution(customCrit, customNorm, customBest)
    const label = selectedMixPreset !== 'custom'
      ? (MIX_PRESETS.find(p => p.id === selectedMixPreset)?.name || 'Custom Workload Mix')
      : 'Custom Workload Mix'
    const res = await telemetryClient.triggerMixSpike(rate, dur, dist, selectedMixPreset, label)
    setIsFiringMixSpike(false)
    if (res.ok) {
      setMixStatusMsg(`🚀 Surge active: ${Number(rate).toLocaleString()} ev/s for ${dur}s with ${customCrit}% Crit, ${customNorm}% Norm, ${customBest}% Best!`)
      setTimeout(() => setMixStatusMsg(''), 5000)
    } else {
      setValidationMsg(res.error || 'Failed to trigger mix surge.')
    }
  }, [mixSpikeRate, mixSpikeDuration, customCrit, customNorm, customBest, selectedMixPreset])

  /* ── Subscribe to Telemetry Client ──────────────────────────── */
  useEffect(() => {
    const unsub = telemetryClient.subscribe(state => {
      setTelemetry(state)
      latestTelemetryRef.current = state
      setIsPaused(!state.running)
    })
    return unsub
  }, [])

  /* ── Live Waveform Rolling Buffer (Strict 30s Window, Continuous 1.0s Cadence) ── */
  useEffect(() => {
    if (isPaused) return

    const interval = setInterval(() => {
      const t = latestTelemetryRef.current
      const now = Date.now()
      const isSurge = t.state === 'SPIKE_ACTIVE' || (t.multiplier && t.multiplier > 1.05)
      const measured = t.measuredRate !== undefined ? t.measuredRate : (t.currentTargetRate || 100)

      // Handle background tab throttling: backfill up to elapsed seconds
      const elapsedSec = Math.min(30, Math.max(1, Math.round((now - lastTickTimeRef.current) / 1000)))
      lastTickTimeRef.current = now

      setWaveformBuffer(prev => {
        const next = [...prev]
        for (let s = elapsedSec - 1; s >= 0; s--) {
          const tickTime = new Date(now - s * 1000).toLocaleTimeString([], { hour12: false })
          next.push({
            time: tickTime,
            egress: Math.max(0, Math.round(measured)),
            target: Math.round(t.currentTargetRate || 100),
            isSurge: isSurge,
          })
        }
        return next.slice(-30)
      })
    }, 1000)

    return () => clearInterval(interval)
  }, [isPaused])

  /* ── Derived Status ─────────────────────────────────────────── */
  const isSurging = telemetry.state === 'SPIKE_ACTIVE' || (telemetry.multiplier && telemetry.multiplier > 1.05)
  const windowMax = Math.max(...waveformBuffer.map(d => d.egress || 0), 100)
  const peakEgressRate = isSurging ? Math.max(windowMax, telemetry.measuredRate || 100) : windowMax

  /* ── Step Animation on Active Spikes ────────────────────────── */
  useEffect(() => {
    if (isSurging) {
      setFlowStep('increase')
      const t1 = setTimeout(() => setFlowStep('spike'), 400)
      const t2 = setTimeout(() => setFlowStep('sent'), 900)
      return () => {
        clearTimeout(t1)
        clearTimeout(t2)
      }
    } else {
      setFlowStep('normal')
    }
  }, [isSurging])

  /* ── Control Actions ────────────────────────────────────────── */
  const handleApplyPreset = useCallback(async (amount) => {
    setValidationMsg('')
    setSelectedPreset(amount)
    await telemetryClient.triggerPreset(amount, 20)
  }, [])

  const handleStartCustomSpike = useCallback(async (e) => {
    e?.preventDefault()
    setValidationMsg('')
    const rate = Number(customRate)
    const dur = Number(customDuration)

    if (isNaN(rate) || rate <= 0) {
      setValidationMsg('Target Rate must be greater than 0.')
      return
    }
    if (rate > 500000) {
      setValidationMsg('Target Rate cannot exceed 500,000 ev/s.')
      return
    }
    if (isNaN(dur) || dur <= 0) {
      setValidationMsg('Duration must be greater than 0 seconds.')
      return
    }
    if (dur > 86400) {
      setValidationMsg('Duration cannot exceed 86,400 seconds (24 hours).')
      return
    }

    const res = await telemetryClient.triggerCustomSpike(rate, dur)
    if (!res.ok) {
      setValidationMsg(res.error || 'Failed to start custom spike.')
    }
  }, [customRate, customDuration])

  const handleExecuteCustomRun = useCallback(async (e) => {
    e?.preventDefault()
    setValidationMsg('')
    const events = Number(runEvents)
    const maxRate = Number(runMaxRate)

    if (isNaN(events) || events <= 0) {
      setValidationMsg('Total Events must be greater than 0.')
      return
    }
    if (events > 50000000) {
      setValidationMsg('Total Events cannot exceed 50,000,000.')
      return
    }
    if (isNaN(maxRate) || maxRate <= 0) {
      setValidationMsg('Max Rate must be greater than 0.')
      return
    }
    if (maxRate > 500000) {
      setValidationMsg('Max Rate cannot exceed 500,000 ev/s.')
      return
    }

    const res = await telemetryClient.triggerCustomRun(events, maxRate)
    if (!res.ok) {
      setValidationMsg(res.error || 'Failed to execute custom run.')
    }
  }, [runEvents, runMaxRate])

  const handleRecover = useCallback(async () => {
    setValidationMsg('')
    await telemetryClient.recoverToBaseline()
  }, [])

  const handleReset = useCallback(async () => {
    setValidationMsg('')
    setSelectedPreset(1)
    await telemetryClient.resetSession()
  }, [])

  const handleTogglePause = useCallback(async () => {
    const res = await telemetryClient.togglePause(isPaused)
    if (res.ok) {
      setIsPaused(!res.isRunning)
    }
  }, [isPaused])

  /* ── Render ─────────────────────────────────────────────────── */
  return (
    <>
      {/* Clean Page Header */}
      <PageHeader
        spikesInjected={telemetry.history?.length > 0 ? telemetry.history.length : (isSurging ? 1 : 0)}
        spikesTotal={PRESET_OPTIONS.length}
        boostedEvents={fmt(telemetry.eventsGenerated)}
        egressRate={fmt(telemetry.measuredRate)}
        isSurging={isSurging}
        isPaused={isPaused}
      />

      <div className="page" id="load-spiker-content" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', overflowY: 'auto' }}>

        {/* ── WORKLOAD & INGESTION OVERVIEW (4-TILES) ───────── */}
        <section>
          <SectionHeading>Authoritative Workload Telemetry Overview (Machine 1)</SectionHeading>
          <div className="metrics-row">
            {/* Tile 1: Egress Velocity */}
            <div className="metric-tile">
              <div className="metric-tile-label">Measured Egress Velocity</div>
              <div className={`metric-tile-value ${isSurging ? 'accent' : ''} tabular-nums font-mono`}>
                {fmt(telemetry.measuredRate)}
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-secondary)', marginLeft: 4 }}>/s</span>
              </div>
              <div className="metric-tile-sub">
                <span className={`status-dot status-dot-sm ${isSurging ? 'status-dot-live-red' : 'status-dot-live-green'}`} />
                Target: <strong>{fmt(telemetry.currentTargetRate)} ev/s</strong> • Base: 100 ev/s
              </div>
            </div>

            {/* Tile 2: Three-Tier Event Accounting */}
            <div className="metric-tile">
              <div className="metric-tile-label">Three-Tier Event Accounting</div>
              <div className="metric-tile-value tabular-nums font-mono" style={{ fontSize: 18 }}>
                {fmt(Math.min(telemetry.eventsDelivered, telemetry.eventsGenerated || telemetry.eventsDelivered))}
                <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-tertiary)', marginLeft: 4 }}>delivered</span>
              </div>
              <div className="metric-tile-sub" style={{ fontSize: 11 }}>
                Gen: <strong>{fmt(telemetry.eventsGenerated)}</strong> • Sent: <strong>{fmt(Math.min(telemetry.eventsAttempted, telemetry.eventsGenerated || telemetry.eventsAttempted))}</strong>
                {telemetry.eventsFailed > 0 ? (
                  <span style={{ color: 'var(--color-error)', marginLeft: 4 }}>({telemetry.eventsFailed} failed)</span>
                ) : (
                  <span style={{ color: 'var(--color-success-text)', marginLeft: 4 }}>• 0 failed</span>
                )}
              </div>
            </div>

            {/* Tile 3: Surge Multiplier / Operational Mode */}
            <div className="metric-tile">
              <div className="metric-tile-label">Operational Workload State</div>
              <div className={`metric-tile-value tabular-nums font-mono ${isSurging ? 'accent' : ''}`}>
                {telemetry.multiplier}×
                <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--color-text-secondary)', marginLeft: 4 }}>surge factor</span>
              </div>
              <div className="metric-tile-sub">
                {isSurging ? (
                  <span style={{ color: 'var(--color-error)' }}>
                    ● {telemetry.spikeLabel}
                    {telemetry.remainingSeconds !== null && ` (${Math.ceil(telemetry.remainingSeconds)}s left)`}
                    {telemetry.eventsTarget && ` (${fmt(telemetry.eventsSpiked)}/${fmt(telemetry.eventsTarget)})`}
                  </span>
                ) : (
                  <span style={{ color: 'var(--color-success-text)' }}>
                    ● Steady Baseline Continuous (100 ev/s)
                  </span>
                )}
              </div>
            </div>

            {/* Tile 4: Machine 2 PulseFlow Status */}
            <div className="metric-tile">
              <div className="metric-tile-label">Target Pipeline Protection</div>
              <div className="metric-tile-value success font-mono" style={{ fontSize: 17 }}>
                Zero Critical Loss
              </div>
              <div className="metric-tile-sub" style={{ color: telemetry.pulseflowConnected ? 'var(--color-success-text)' : 'var(--color-error)' }}>
                {telemetry.pulseflowConnected ? 'Machine 2 Adaptive Engine Active' : 'PulseFlow Ingestion Offline (Retrying)'}
              </div>
            </div>
          </div>
        </section>

        {/* ── WORKLOAD ORCHESTRATION & SPIKER CONTROLS ─────── */}
        <section>
          <SectionHeading>Workload Orchestration &amp; Surge Engine</SectionHeading>
          <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'stretch' }}>
            
            {/* Left Card: Spiker Controls & Custom Modes */}
            <div className="card" style={{ flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <div>
                {/* Header */}
                <div className="card-header" style={{ padding: 'var(--space-4) var(--space-5)' }}>
                  <div className="card-header-left">
                    <Zap size={14} style={{ color: 'var(--color-indigo-600)' }} strokeWidth={2.2} />
                    <span className="card-title">Workload Control Console (Machine 1)</span>
                  </div>
                  <span className={`sim-mode-chip ${isSurging ? 'spike' : 'normal'}`}>
                    <span className={`status-dot ${isSurging ? 'status-dot-live-red' : 'status-dot-live-green'}`} style={{ width: 6, height: 6 }} />
                    {isSurging ? 'SURGE BURST ACTIVE' : 'STEADY BASELINE'}
                  </span>
                </div>

                <div className="card-body" style={{ padding: 'var(--space-4) var(--space-5)' }}>
                  {/* Mode Tabs */}
                  <div style={{ display: 'flex', gap: 8, marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-3)' }}>
                    <button
                      type="button"
                      className={`btn btn-sm ${activeTab === 'preset' ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => setActiveTab('preset')}
                      style={{ fontWeight: 600 }}
                    >
                      Preset Spikes (1× - 20×)
                    </button>
                    <button
                      type="button"
                      className={`btn btn-sm ${activeTab === 'custom' ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => setActiveTab('custom')}
                      style={{ fontWeight: 600 }}
                    >
                      Custom Spike (Rate &amp; Duration)
                    </button>
                    <button
                      type="button"
                      className={`btn btn-sm ${activeTab === 'count' ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => setActiveTab('count')}
                      style={{ fontWeight: 600 }}
                    >
                      Custom Event Run (Benchmark Count)
                    </button>
                    <button
                      type="button"
                      className={`btn btn-sm ${activeTab === 'mix' ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => setActiveTab('mix')}
                      style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}
                    >
                      <Layers size={13} />
                      Synthetic Event Mix ({currentTierPcts.crit}% / {currentTierPcts.norm}% / {currentTierPcts.best}%)
                    </button>
                  </div>

                  {validationMsg && (
                    <div style={{ background: 'rgba(239, 68, 68, 0.08)', color: 'var(--color-error)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', fontSize: 12, marginBottom: 'var(--space-3)', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <AlertTriangle size={14} />
                      <span>{validationMsg}</span>
                    </div>
                  )}

                  {/* TAB 1: PRESET SPIKES */}
                  {activeTab === 'preset' && (
                    <div>
                      <div className="spike-btn-group">
                        {PRESET_OPTIONS.map(opt => {
                          const isSelected = selectedPreset === opt.amount
                          return (
                            <button
                              key={opt.amount}
                              type="button"
                              className={`spike-btn${isSelected ? ' selected' : ''}`}
                              onClick={() => handleApplyPreset(opt.amount)}
                              id={`spike-opt-${opt.amount}`}
                            >
                              <div className="spike-btn-top">
                                <span className="spike-btn-amount">{opt.multiplier}</span>
                                <span className="spike-btn-multiplier">{opt.targetRate} ev/s</span>
                              </div>
                              <div>
                                <div className="spike-btn-label">{opt.label}</div>
                                <div className="spike-btn-subtext">{opt.tag}</div>
                              </div>
                            </button>
                          )
                        })}
                      </div>

                      <div className="spike-selected-readout" style={{ marginTop: 'var(--space-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
                        <div>
                          <div style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-tertiary)', letterSpacing: '0.04em' }}>
                            ACTIVE PRESET CONFIGURATION
                          </div>
                          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)', marginTop: 2 }}>
                            {PRESET_OPTIONS.find(o => o.amount === selectedPreset)?.label}
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                            <span className="spike-selected-number font-mono">{selectedPreset}×</span>
                            <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-text-secondary)' }}>
                              ({PRESET_OPTIONS.find(o => o.amount === selectedPreset)?.targetRate} ev/s)
                            </span>
                          </div>

                          <button
                            type="button"
                            onClick={() => handleApplyPreset(selectedPreset)}
                            className="btn btn-primary"
                            style={{
                              padding: '7px 14px',
                              fontWeight: 700,
                              fontSize: '12px',
                              background: isSurging ? 'var(--color-error)' : 'linear-gradient(135deg, #4F46E5 0%, #635BFF 100%)',
                              boxShadow: '0 2px 6px rgba(99, 91, 255, 0.25)',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 6,
                            }}
                          >
                            <Zap size={13} />
                            <span>
                              {isSurging && telemetry.remainingSeconds !== null
                                ? `SURGE ACTIVE (${Math.ceil(telemetry.remainingSeconds)}s)`
                                : `FIRE ${selectedPreset}× SURGE (20s)`}
                            </span>
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* TAB 2: CUSTOM SPIKE */}
                  {activeTab === 'custom' && (
                    <form onSubmit={handleStartCustomSpike} noValidate style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
                        <div>
                          <label style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-secondary)', display: 'block', marginBottom: 4 }}>
                            Target Rate (events/sec)
                          </label>
                          <div style={{ display: 'flex', alignItems: 'center', background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '6px 10px' }}>
                            <input
                              type="number"
                              min="1"
                              max="500000"
                              step="any"
                              value={customRate}
                              onChange={e => setCustomRate(e.target.value)}
                              style={{ width: '100%', background: 'transparent', border: 'none', outline: 'none', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}
                            />
                            <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginLeft: 4 }}>ev/s</span>
                          </div>
                          <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>Supports up to 500,000 ev/s</span>
                        </div>

                        <div>
                          <label style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-secondary)', display: 'block', marginBottom: 4 }}>
                            Surge Duration (seconds)
                          </label>
                          <div style={{ display: 'flex', alignItems: 'center', background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '6px 10px' }}>
                            <input
                              type="number"
                              min="1"
                              max="86400"
                              step="any"
                              value={customDuration}
                              onChange={e => setCustomDuration(e.target.value)}
                              style={{ width: '100%', background: 'transparent', border: 'none', outline: 'none', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}
                            />
                            <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginLeft: 4 }}>sec</span>
                          </div>
                          <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>Auto-returns to 100 ev/s baseline afterward</span>
                        </div>
                      </div>

                      <button
                        type="submit"
                        className="btn btn-primary"
                        style={{ padding: '10px 16px', fontWeight: 700, marginTop: 'var(--space-1)' }}
                      >
                        <Zap size={14} />
                        Start Custom Spike ({Number(customRate || 0).toLocaleString()} ev/s for {customDuration || 0}s)
                      </button>

                      {/* Quick Target Rates & Durations */}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4 }}>
                          <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-tertiary)', letterSpacing: '0.04em' }}>
                            Quick Rates:
                          </span>
                          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {[500, 1000, 2500, 5000, 10000, 20000, 50000].map(r => (
                              <button
                                key={r}
                                type="button"
                                className="btn btn-secondary btn-xs"
                                onClick={() => setCustomRate(r)}
                                style={{ fontSize: 10, padding: '2px 7px', fontWeight: Number(customRate) === r ? 700 : 500, borderColor: Number(customRate) === r ? 'var(--color-indigo-500)' : undefined }}
                              >
                                {r >= 1000 ? `${r / 1000}k` : r} ev/s
                              </button>
                            ))}
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4 }}>
                          <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-tertiary)', letterSpacing: '0.04em' }}>
                            Quick Durations:
                          </span>
                          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {[10, 15, 30, 60, 120, 300].map(d => (
                              <button
                                key={d}
                                type="button"
                                className="btn btn-secondary btn-xs"
                                onClick={() => setCustomDuration(d)}
                                style={{ fontSize: 10, padding: '2px 7px', fontWeight: Number(customDuration) === d ? 700 : 500, borderColor: Number(customDuration) === d ? 'var(--color-indigo-500)' : undefined }}
                              >
                                {d}s
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Projected Surge Impact Telemetry Matrix */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginTop: 4, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '10px 12px' }}>
                        <div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700 }}>
                            Projected Payload
                          </div>
                          <div className="font-mono" style={{ fontSize: 14, fontWeight: 800, color: 'var(--color-text-primary)', marginTop: 2 }}>
                            ~{fmt(Number(customRate || 0) * Number(customDuration || 0))}
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 1 }}>
                            Total burst delivery
                          </div>
                        </div>

                        <div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700 }}>
                            Pipeline Stress
                          </div>
                          <div className="font-mono" style={{ fontSize: 14, fontWeight: 800, color: Number(customRate) > 1000 ? '#EF4444' : Number(customRate) > 300 ? '#F59E0B' : '#10B981', marginTop: 2 }}>
                            {Math.min(100, Math.round((Number(customRate || 0) / 2000) * 100))}%
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 1 }}>
                            {Number(customRate) >= 1500 ? 'Adaptive shedding' : Number(customRate) >= 400 ? 'Micro-batching' : 'Stream processing'}
                          </div>
                        </div>

                        <div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700 }}>
                            SLA Invariant
                          </div>
                          <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--color-success-text)', marginTop: 2 }}>
                            Zero Loss
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 1 }}>
                            Critical orders protected
                          </div>
                        </div>
                      </div>
                    </form>
                  )}

                  {/* TAB 3: CUSTOM EVENT RUN */}
                  {activeTab === 'count' && (
                    <form onSubmit={handleExecuteCustomRun} noValidate style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
                        <div>
                          <label style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-secondary)', display: 'block', marginBottom: 4 }}>
                            Exact Event Count
                          </label>
                          <div style={{ display: 'flex', alignItems: 'center', background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '6px 10px' }}>
                            <input
                              type="number"
                              min="1"
                              max="50000000"
                              step="any"
                              value={runEvents}
                              onChange={e => setRunEvents(e.target.value)}
                              style={{ width: '100%', background: 'transparent', border: 'none', outline: 'none', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}
                            />
                            <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginLeft: 4 }}>events</span>
                          </div>
                          <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>Supports up to 50,000,000 events</span>
                        </div>

                        <div>
                          <label style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-secondary)', display: 'block', marginBottom: 4 }}>
                            Maximum Rate Cap
                          </label>
                          <div style={{ display: 'flex', alignItems: 'center', background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '6px 10px' }}>
                            <input
                              type="number"
                              min="1"
                              max="500000"
                              step="any"
                              value={runMaxRate}
                              onChange={e => setRunMaxRate(e.target.value)}
                              style={{ width: '100%', background: 'transparent', border: 'none', outline: 'none', fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 700, color: 'var(--color-text-primary)' }}
                            />
                            <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginLeft: 4 }}>ev/s</span>
                          </div>
                          <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>Throughput cap (up to 500,000 ev/s)</span>
                        </div>
                      </div>

                      {telemetry.eventsTarget && (
                        <div style={{ background: 'var(--color-bg-secondary)', padding: '8px 12px', borderRadius: 'var(--radius-sm)', marginTop: 4 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                            <span>Benchmark Run Progress:</span>
                            <span className="font-mono"><strong>{fmt(telemetry.eventsSpiked)}</strong> / {fmt(telemetry.eventsTarget)}</span>
                          </div>
                          <div className="stress-gauge-track">
                            <div
                              className="stress-gauge-fill"
                              style={{ width: `${Math.min(100, Math.round((telemetry.eventsSpiked / telemetry.eventsTarget) * 100))}%`, background: 'var(--color-indigo-600)' }}
                            />
                          </div>
                        </div>
                      )}

                      <button
                        type="submit"
                        className="btn btn-primary"
                        style={{ padding: '10px 16px', fontWeight: 700, marginTop: 'var(--space-1)' }}
                      >
                        <BarChart2 size={14} />
                        Execute Benchmark Run ({Number(runEvents || 0).toLocaleString()} events @ max {runMaxRate || 0} ev/s)
                      </button>

                      {/* Quick Event Count Chips */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-tertiary)', letterSpacing: '0.04em' }}>
                          Quick Counts:
                        </span>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {[10000, 50000, 100000, 250000, 500000, 1000000].map(c => (
                            <button
                              key={c}
                              type="button"
                              className="btn btn-secondary btn-xs"
                              onClick={() => setRunEvents(c)}
                              style={{ fontSize: 10, padding: '2px 7px', fontWeight: Number(runEvents) === c ? 700 : 500, borderColor: Number(runEvents) === c ? 'var(--color-indigo-500)' : undefined }}
                            >
                              {fmt(c)} ev
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Projected Run Metrics */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginTop: 4, background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '10px 12px' }}>
                        <div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700 }}>
                            Target Volume
                          </div>
                          <div className="font-mono" style={{ fontSize: 14, fontWeight: 800, color: 'var(--color-text-primary)', marginTop: 2 }}>
                            {fmt(runEvents)}
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 1 }}>
                            Fixed event quota
                          </div>
                        </div>

                        <div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700 }}>
                            Estimated Time
                          </div>
                          <div className="font-mono" style={{ fontSize: 14, fontWeight: 800, color: 'var(--color-indigo-600)', marginTop: 2 }}>
                            ~{((Number(runEvents || 0)) / Math.max(1, Number(runMaxRate || 100))).toFixed(1)}s
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 1 }}>
                            At {fmt(runMaxRate)} ev/s cap
                          </div>
                        </div>

                        <div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', fontWeight: 700 }}>
                            Completion Rule
                          </div>
                          <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--color-success-text)', marginTop: 2 }}>
                            Auto-Recover
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 1 }}>
                            Resumes 100 ev/s floor
                          </div>
                        </div>
                      </div>
                    </form>
                  )}

                  {/* TAB 4: SYNTHETIC EVENT MIX */}
                  {activeTab === 'mix' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                      {/* Header banner */}
                      <div style={{ background: 'rgba(99, 91, 255, 0.05)', border: '1px solid rgba(99, 91, 255, 0.2)', borderRadius: 'var(--radius-md)', padding: '12px 16px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Sliders size={16} style={{ color: 'var(--color-indigo-600)' }} />
                            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--color-text-primary)' }}>
                              Dynamic Traffic Mix Partitioning (Machine 1)
                            </span>
                          </div>
                          <span className="badge badge-indigo" style={{ fontSize: 11, fontWeight: 600 }}>
                            Zero Restart • Instant Egress Update
                          </span>
                        </div>
                        <p style={{ margin: '6px 0 0 0', fontSize: 12, color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
                          Tune priority distribution percentages. Machine 1 generates this proportion on the fly, directly exercising Machine 2 priority queues and adaptive backpressure shedding.
                        </p>
                      </div>

                      {mixStatusMsg && (
                        <div className="mix-toast">
                          <CheckCircle size={14} />
                          <span>{mixStatusMsg}</span>
                        </div>
                      )}

                      {/* 1. Quick Preset Archetypes */}
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 6 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-secondary)', letterSpacing: '0.04em' }}>
                            Choose Workload Archetype Preset
                          </div>
                          {selectedMixPreset === 'custom' ? (
                            <span className="badge badge-indigo" style={{ fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6, padding: '3px 9px' }}>
                              <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#635BFF' }} />
                              Custom Manual Configuration Active (No Preset Selected)
                            </span>
                          ) : (
                            <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                              Click any preset below or drag sliders to configure custom mix
                            </span>
                          )}
                        </div>
                        <div className="mix-preset-grid">
                          {MIX_PRESETS.map(p => {
                            const isSelected = selectedMixPreset === p.id
                            return (
                              <div
                                key={p.id}
                                className={`mix-preset-card${isSelected ? ' selected' : ''}`}
                                onClick={() => applyMixPreset(p.id)}
                              >
                                <div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                    <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--color-text-primary)' }}>{p.name}</span>
                                    <span className="badge" style={{ fontSize: 10, background: isSelected ? 'var(--color-indigo-600)' : 'var(--color-bg-secondary)', color: isSelected ? '#fff' : 'var(--color-text-secondary)' }}>
                                      {p.badge}
                                    </span>
                                  </div>
                                  <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)', margin: '0 0 10px 0', lineHeight: 1.35 }}>
                                    {p.desc}
                                  </p>
                                </div>
                                <div>
                                  <div className="mix-stacked-bar" style={{ height: 6, marginBottom: 6 }}>
                                    <div className="mix-stacked-seg" style={{ width: `${p.crit}%`, background: '#635BFF' }} title={`Critical: ${p.crit}%`} />
                                    <div className="mix-stacked-seg" style={{ width: `${p.norm}%`, background: '#0284c7' }} title={`Normal: ${p.norm}%`} />
                                    <div className="mix-stacked-seg" style={{ width: `${p.best}%`, background: '#94a3b8' }} title={`Best-Effort: ${p.best}%`} />
                                  </div>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontWeight: 600, color: 'var(--color-text-secondary)' }}>
                                    <span style={{ color: '#635BFF' }}>Crit: {p.crit}%</span>
                                    <span style={{ color: '#0284c7' }}>Norm: {p.norm}%</span>
                                    <span style={{ color: '#64748b' }}>Best: {p.best}%</span>
                                  </div>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>

                      {/* 2. Interactive Sliders & Live Preview */}
                      <div style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 6 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-secondary)', letterSpacing: '0.04em' }}>
                              Interactive Ratio Adjuster (Sum: {customCrit + customNorm + customBest}%)
                            </span>
                            {selectedMixPreset === 'custom' && (
                              <span className="badge" style={{ fontSize: 10, fontWeight: 700, background: 'rgba(99, 91, 255, 0.15)', color: '#635BFF' }}>
                                Custom Manual Mode
                              </span>
                            )}
                          </div>
                          <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                            {selectedMixPreset === 'custom' ? 'Direct user tuning • Live synced to Machine 1 generator' : 'Move any slider to switch to Custom mode'}
                          </span>
                        </div>

                        {/* Combined Stacked Preview Bar */}
                        <div className="mix-stacked-bar" style={{ height: 12, marginBottom: 16 }}>
                          <div className="mix-stacked-seg" style={{ width: `${customCrit}%`, background: '#635BFF' }} />
                          <div className="mix-stacked-seg" style={{ width: `${customNorm}%`, background: '#0284c7' }} />
                          <div className="mix-stacked-seg" style={{ width: `${customBest}%`, background: '#94a3b8' }} />
                        </div>

                        {/* Slider 1: Critical */}
                        <div className="mix-slider-row">
                          <div className="mix-slider-header">
                            <span style={{ color: 'var(--color-indigo-700)', display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#635BFF' }} />
                              Critical Priority (ORDER / PAYMENT)
                            </span>
                            <span className="font-mono" style={{ fontSize: 14, fontWeight: 700, color: '#635BFF' }}>
                              {customCrit}%
                            </span>
                          </div>
                          <input
                            type="range"
                            min="1"
                            max="90"
                            value={customCrit}
                            onChange={e => handleCritChange(e.target.value)}
                            className="mix-range-input crit"
                          />
                        </div>

                        {/* Slider 2: Normal */}
                        <div className="mix-slider-row">
                          <div className="mix-slider-header">
                            <span style={{ color: '#0369a1', display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#0284c7' }} />
                              Normal Priority (CART_ADD / INVENTORY_UPDATE)
                            </span>
                            <span className="font-mono" style={{ fontSize: 14, fontWeight: 700, color: '#0284c7' }}>
                              {customNorm}%
                            </span>
                          </div>
                          <input
                            type="range"
                            min="1"
                            max="90"
                            value={customNorm}
                            onChange={e => handleNormChange(e.target.value)}
                            className="mix-range-input norm"
                          />
                        </div>

                        {/* Slider 3: Best-Effort */}
                        <div className="mix-slider-row" style={{ marginBottom: 0 }}>
                          <div className="mix-slider-header">
                            <span style={{ color: '#475569', display: 'flex', alignItems: 'center', gap: 6 }}>
                              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#94a3b8' }} />
                              Best-Effort Priority (CLICK / PAGE_VIEW / LOG)
                            </span>
                            <span className="font-mono" style={{ fontSize: 14, fontWeight: 700, color: '#475569' }}>
                              {customBest}%
                            </span>
                          </div>
                          <input
                            type="range"
                            min="1"
                            max="90"
                            value={customBest}
                            onChange={e => handleBestChange(e.target.value)}
                            className="mix-range-input best"
                          />
                        </div>
                      </div>

                      {/* 3. Seven Event Type Breakdown Table */}
                      <div style={{ background: '#fff', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '10px 14px' }}>
                        <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-secondary)', marginBottom: 8 }}>
                          Resolved 7-Event Type Distribution (Sent to Machine 2 Pipeline)
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 8, fontSize: 11 }}>
                          {(() => {
                            const d = tiersToDistribution(customCrit, customNorm, customBest)
                            return [
                              { type: 'ORDER', tier: 'Critical', weight: d.ORDER, color: '#635BFF' },
                              { type: 'PAYMENT', tier: 'Critical', weight: d.PAYMENT, color: '#635BFF' },
                              { type: 'CART_ADD', tier: 'Normal', weight: d.CART_ADD, color: '#0284c7' },
                              { type: 'INVENTORY_UPDATE', tier: 'Normal', weight: d.INVENTORY_UPDATE, color: '#0284c7' },
                              { type: 'PAGE_VIEW', tier: 'Best-Effort', weight: d.PAGE_VIEW, color: '#64748b' },
                              { type: 'CLICK', tier: 'Best-Effort', weight: d.CLICK, color: '#64748b' },
                              { type: 'LOG', tier: 'Best-Effort', weight: d.LOG, color: '#64748b' },
                            ].map(item => (
                              <div key={item.type} style={{ background: 'var(--color-bg-secondary)', padding: '6px 8px', borderRadius: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div>
                                  <div style={{ fontWeight: 600, fontSize: 10, color: item.color }}>{item.type}</div>
                                  <div style={{ fontSize: 9, color: 'var(--color-text-tertiary)' }}>{item.tier}</div>
                                </div>
                                <span className="font-mono" style={{ fontWeight: 700, fontSize: 12 }}>
                                  {item.weight}%
                                </span>
                              </div>
                            ))
                          })()}
                        </div>
                      </div>

                      {/* 4. Spike Control & Surge Velocity Deck */}
                      <div style={{ background: '#f8fafc', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: '16px', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Zap size={16} style={{ color: 'var(--color-indigo-600)' }} />
                            <span style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-primary)', letterSpacing: '0.04em' }}>
                              Surge Spike Controller (Events / Sec for this Mix)
                            </span>
                          </div>
                          <span className="badge" style={{ fontSize: 10, fontWeight: 600, background: 'rgba(99, 91, 255, 0.1)', color: 'var(--color-indigo-700)' }}>
                            Executes with {selectedMixPreset === 'custom' ? 'Custom Tuned Mix' : `Preset: ${selectedMixPreset}`}
                          </span>
                        </div>

                        {/* Two Columns: Rate (ev/s) & Duration (s) */}
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
                          <div>
                            <label style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-secondary)', display: 'block', marginBottom: 4 }}>
                              Spike Target Rate (ev/s)
                            </label>
                            <div style={{ display: 'flex', alignItems: 'center', background: '#fff', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '6px 10px' }}>
                              <input
                                type="number"
                                min="1"
                                max="500000"
                                step="any"
                                value={mixSpikeRate}
                                onChange={e => setMixSpikeRate(e.target.value)}
                                style={{ width: '100%', background: 'transparent', border: 'none', outline: 'none', fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 700, color: 'var(--color-text-primary)' }}
                              />
                              <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginLeft: 4 }}>ev/s</span>
                            </div>
                            {/* Quick Rate Pills */}
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                              {[500, 1000, 2500, 5000, 10000, 20000].map(r => (
                                <button
                                  key={r}
                                  type="button"
                                  className="btn btn-secondary btn-xs"
                                  onClick={() => setMixSpikeRate(r)}
                                  style={{ fontSize: 10, padding: '2px 6px', fontWeight: Number(mixSpikeRate) === r ? 700 : 500, borderColor: Number(mixSpikeRate) === r ? 'var(--color-indigo-500)' : undefined }}
                                >
                                  {fmt(r)}
                                </button>
                              ))}
                            </div>
                          </div>

                          <div>
                            <label style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: 'var(--color-text-secondary)', display: 'block', marginBottom: 4 }}>
                              Surge Duration (seconds)
                            </label>
                            <div style={{ display: 'flex', alignItems: 'center', background: '#fff', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '6px 10px' }}>
                              <input
                                type="number"
                                min="1"
                                max="86400"
                                step="any"
                                value={mixSpikeDuration}
                                onChange={e => setMixSpikeDuration(e.target.value)}
                                style={{ width: '100%', background: 'transparent', border: 'none', outline: 'none', fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 700, color: 'var(--color-text-primary)' }}
                              />
                              <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)', marginLeft: 4 }}>sec</span>
                            </div>
                            {/* Quick Duration Pills */}
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 6 }}>
                              {[10, 15, 20, 30, 60, 120].map(s => (
                                <button
                                  key={s}
                                  type="button"
                                  className="btn btn-secondary btn-xs"
                                  onClick={() => setMixSpikeDuration(s)}
                                  style={{ fontSize: 10, padding: '2px 6px', fontWeight: Number(mixSpikeDuration) === s ? 700 : 500, borderColor: Number(mixSpikeDuration) === s ? 'var(--color-indigo-500)' : undefined }}
                                >
                                  {s}s
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>

                        {/* Live Priority Velocity Partitioning Preview */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, background: '#fff', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', padding: '10px 12px' }}>
                          <div>
                            <div style={{ fontSize: 10, color: '#635BFF', textTransform: 'uppercase', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}>
                              <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#635BFF' }} />
                              Critical Velocity
                            </div>
                            <div className="font-mono" style={{ fontSize: 14, fontWeight: 800, color: '#635BFF', marginTop: 2 }}>
                              {fmt(Math.round((Number(mixSpikeRate) || 0) * (customCrit / 100)))} ev/s
                            </div>
                            <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 1 }}>
                              {customCrit}% • ORDER + PAYMENT
                            </div>
                          </div>

                          <div>
                            <div style={{ fontSize: 10, color: '#0284c7', textTransform: 'uppercase', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}>
                              <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#0284c7' }} />
                              Normal Velocity
                            </div>
                            <div className="font-mono" style={{ fontSize: 14, fontWeight: 800, color: '#0284c7', marginTop: 2 }}>
                              {fmt(Math.round((Number(mixSpikeRate) || 0) * (customNorm / 100)))} ev/s
                            </div>
                            <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 1 }}>
                              {customNorm}% • CART + INVENTORY
                            </div>
                          </div>

                          <div>
                            <div style={{ fontSize: 10, color: '#64748b', textTransform: 'uppercase', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 5 }}>
                              <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: '#64748b' }} />
                              Best-Effort Velocity
                            </div>
                            <div className="font-mono" style={{ fontSize: 14, fontWeight: 800, color: '#64748b', marginTop: 2 }}>
                              {fmt(Math.round((Number(mixSpikeRate) || 0) * (customBest / 100)))} ev/s
                            </div>
                            <div style={{ fontSize: 10, color: 'var(--color-text-tertiary)', marginTop: 1 }}>
                              {customBest}% • CLICK + VIEW + LOG
                            </div>
                          </div>
                        </div>

                        {/* Projected Total Burst Size */}
                        <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span>
                            Projected Burst Delivery: <strong className="font-mono" style={{ color: 'var(--color-text-primary)' }}>~{fmt(Math.round((Number(mixSpikeRate) || 0) * (Number(mixSpikeDuration) || 0)))} total events</strong>
                          </span>
                          <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>
                            Auto-reverts to ~100 ev/s baseline on completion
                          </span>
                        </div>

                        {/* Active Surge Live Indicator if currently running */}
                        {telemetry.spikeMode !== 'NONE' && (
                          <div style={{ background: 'rgba(99, 91, 255, 0.08)', border: '1px solid rgba(99, 91, 255, 0.25)', borderRadius: 'var(--radius-sm)', padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span className="live-dot pulse" style={{ background: '#635BFF' }} />
                              <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-indigo-700)' }}>
                                {telemetry.spikeLabel} Active ({fmt(Math.round(telemetry.measuredRate))} ev/s)
                              </span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              {telemetry.remainingSeconds && (
                                <span className="font-mono" style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-indigo-600)' }}>
                                  {Math.ceil(telemetry.remainingSeconds)}s remaining
                                </span>
                              )}
                              <button
                                type="button"
                                className="btn btn-danger btn-xs"
                                onClick={handleRecover}
                                style={{ fontSize: 11, padding: '3px 8px' }}
                              >
                                Abort Surge & Recover
                              </button>
                            </div>
                          </div>
                        )}

                        {/* Surge Execution & Action Buttons */}
                        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginTop: 4 }}>
                          <button
                            type="button"
                            className="btn btn-primary"
                            onClick={handleFireMixSpike}
                            disabled={isFiringMixSpike}
                            style={{ padding: '10px 22px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 260 }}
                          >
                            <Zap size={16} />
                            {isFiringMixSpike ? 'Launching Surge...' : `Fire Surge with this Mix (${fmt(mixSpikeRate)} ev/s for ${mixSpikeDuration}s)`}
                          </button>

                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={applyCustomMix}
                            disabled={isApplyingMix}
                            style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}
                          >
                            <Check size={14} />
                            Apply Mix to Baseline Flow (~100 ev/s)
                          </button>

                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => applyMixPreset('standard')}
                            style={{ fontWeight: 600 }}
                          >
                            Reset to Standard (10/20/70)
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Safety & Recovery Deck */}
              <div style={{ padding: 'var(--space-4) var(--space-5)', borderTop: '1px solid var(--color-border-subtle)', background: 'rgba(248, 250, 252, 0.6)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                  <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleTogglePause}
                      id="btn-pause"
                      style={{ fontWeight: 600 }}
                    >
                      {isPaused ? <Play size={13} strokeWidth={2} /> : <Pause size={13} strokeWidth={2} />}
                      {isPaused ? 'Resume Generator' : 'Pause Generator'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleReset}
                      id="btn-reset"
                      style={{ fontWeight: 600 }}
                    >
                      <RotateCcw size={13} strokeWidth={2} />
                      Reset Session
                    </button>
                  </div>

                  {/* Prominent Recovery Button (Returns to 100 ev/s baseline, never 0) */}
                  <button
                    type="button"
                    className="btn btn-success"
                    onClick={handleRecover}
                    id="btn-recover"
                    style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px' }}
                    title="Cancel active spike and immediately return to steady 100 ev/s baseline"
                  >
                    <RefreshCw size={13} strokeWidth={2.5} />
                    RECOVER TO BASELINE (100 ev/s)
                  </button>
                </div>
              </div>
            </div>

            {/* Right Card: Stress Projection & Event Mix */}
            <div className="card" style={{ width: 320, flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
              <div className="card-header" style={{ padding: 'var(--space-4) var(--space-5)' }}>
                <div className="card-header-left">
                  <Activity size={14} style={{ color: 'var(--color-indigo-600)' }} strokeWidth={2} />
                  <span className="card-title">Stress Projection &amp; Mix</span>
                </div>
                <span className="badge badge-indigo" style={{ fontSize: '10px', padding: '2px 7px' }}>
                  Adaptive Bridge
                </span>
              </div>

              <div className="calc-block">
                <div className="calc-row">
                  <span className="calc-label">Steady Baseline Velocity</span>
                  <span className="calc-value font-mono">100</span>
                  <span className="calc-delta" style={{ color: 'var(--color-text-tertiary)' }}>
                    events / sec continuous floor
                  </span>
                </div>

                <div className="calc-row">
                  <span className="calc-label">Active Target Velocity</span>
                  <span className="calc-value font-mono" style={{ color: isSurging ? 'var(--color-indigo-600)' : 'var(--color-text-primary)' }}>
                    {fmt(telemetry.currentTargetRate)}
                  </span>
                  <span className="calc-delta up font-mono">
                    {telemetry.multiplier}× workload factor
                  </span>
                </div>

                {/* Pipeline Stress Gauge */}
                <div className="calc-row">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className="calc-label">Pipeline Stress Rating</span>
                    <span className="font-mono" style={{ fontSize: '11px', fontWeight: 700, color: telemetry.currentTargetRate > 1000 ? '#EF4444' : telemetry.currentTargetRate > 300 ? '#F59E0B' : '#10B981' }}>
                      {Math.min(100, Math.round((telemetry.currentTargetRate / 2000) * 100))}%
                    </span>
                  </div>
                  <div className="stress-gauge-track">
                    <div
                      className="stress-gauge-fill"
                      style={{
                        width: `${Math.min(100, Math.round((telemetry.currentTargetRate / 2000) * 100))}%`,
                        background: telemetry.currentTargetRate > 1000 ? 'var(--color-error)' : telemetry.currentTargetRate > 300 ? 'var(--color-warning)' : 'var(--color-success)'
                      }}
                    />
                  </div>
                  <span className="calc-delta" style={{ color: 'var(--color-text-tertiary)' }}>
                    {telemetry.currentTargetRate >= 1500 ? 'Forces Adaptive Shedding' : telemetry.currentTargetRate >= 400 ? 'Triggers Normal Micro-Batching' : 'Linear Stream Processing'}
                  </span>
                </div>

                {/* Event Mix Breakdown */}
                <div className="calc-row" style={{ borderBottom: 'none', paddingBottom: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span className="calc-label" style={{ margin: 0 }}>Synthetic Event Mix</span>
                    <button
                      type="button"
                      onClick={() => setActiveTab('mix')}
                      style={{ background: 'none', border: 'none', color: 'var(--color-indigo-600)', fontSize: 11, fontWeight: 600, cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center', gap: 3 }}
                    >
                      <Sliders size={11} />
                      Adjust Mix
                    </button>
                  </div>

                  {/* Multi-segment mini stacked bar */}
                  <div className="mix-stacked-bar" style={{ height: 6, marginBottom: 8 }}>
                    <div className="mix-stacked-seg" style={{ width: `${currentTierPcts.crit}%`, background: '#635BFF' }} title={`Critical: ${currentTierPcts.crit}%`} />
                    <div className="mix-stacked-seg" style={{ width: `${currentTierPcts.norm}%`, background: '#0284c7' }} title={`Normal: ${currentTierPcts.norm}%`} />
                    <div className="mix-stacked-seg" style={{ width: `${currentTierPcts.best}%`, background: '#94a3b8' }} title={`Best-Effort: ${currentTierPcts.best}%`} />
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5, fontSize: '11px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--color-indigo-700)', fontWeight: 600 }}>• Critical (ORDER / PAYMENT)</span>
                      <span className="font-mono" style={{ fontWeight: 700 }}>{currentTierPcts.crit}%</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: '#0369a1', fontWeight: 600 }}>• Normal (CART / INVENTORY)</span>
                      <span className="font-mono" style={{ fontWeight: 700 }}>{currentTierPcts.norm}%</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--color-text-secondary)' }}>• Best Effort (CLICK / PAGE / LOG)</span>
                      <span className="font-mono" style={{ fontWeight: 700 }}>{currentTierPcts.best}%</span>
                    </div>
                  </div>

                  {/* Quick Preset 1-Click Buttons */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginTop: 10 }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={() => applyMixPreset('standard')}
                      title="Standard: 10% Crit / 20% Norm / 70% Best"
                      style={{ fontSize: 10, padding: '3px 6px', fontWeight: currentTierPcts.crit === 10 ? 700 : 500, borderColor: currentTierPcts.crit === 10 ? 'var(--color-indigo-500)' : undefined }}
                    >
                      10/20/70 (Std)
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={() => applyMixPreset('flash_sale')}
                      title="Flash Sale: 35% Crit / 40% Norm / 25% Best"
                      style={{ fontSize: 10, padding: '3px 6px', fontWeight: currentTierPcts.crit === 35 ? 700 : 500, borderColor: currentTierPcts.crit === 35 ? 'var(--color-indigo-500)' : undefined }}
                    >
                      35/40/25 (Sale)
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={() => applyMixPreset('payment_stress')}
                      title="Checkout Surge: 60% Crit / 25% Norm / 15% Best"
                      style={{ fontSize: 10, padding: '3px 6px', fontWeight: currentTierPcts.crit === 60 ? 700 : 500, borderColor: currentTierPcts.crit === 60 ? 'var(--color-indigo-500)' : undefined }}
                    >
                      60/25/15 (Pay)
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={() => applyMixPreset('click_flood')}
                      title="DDoS / Flood: 5% Crit / 10% Norm / 85% Best"
                      style={{ fontSize: 10, padding: '3px 6px', fontWeight: currentTierPcts.crit === 5 ? 700 : 500, borderColor: currentTierPcts.crit === 5 ? 'var(--color-indigo-500)' : undefined }}
                    >
                      5/10/85 (Flood)
                    </button>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </section>

        {/* ── REAL-TIME EGRESS TRAFFIC WAVEFORM ────────────── */}
        <section>
          <SectionHeading>Real-Time Egress Velocity Waveform</SectionHeading>
          <EgressWaveformCard
            data={waveformBuffer}
            currentRate={telemetry.measuredRate}
            targetRate={telemetry.currentTargetRate}
            peakRate={peakEgressRate}
            isSurging={isSurging}
          />
        </section>

        {/* ── PIPELINE TRANSMISSION BRIDGE ─────────────────── */}
        <section>
          <SectionHeading>Pipeline Transmission Bridge (Machine 1 → Machine 2)</SectionHeading>
          <PayloadFlowPanel
            activeStep={flowStep}
            isSurging={isSurging}
            latencyMs={telemetry.latencyMs}
          />
        </section>

        {/* ── TRANSMISSION AUDIT LOG ───────────────────────── */}
        <section>
          <SectionHeading>Transmission Audit &amp; Bridge History</SectionHeading>
          <TransmissionAuditLog history={telemetry.history || []} />
        </section>

      </div>
    </>
  )
}
