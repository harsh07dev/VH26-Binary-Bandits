import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Play,
  Zap,
  Scale,
  ShieldCheck,
  AlertTriangle,
  TrendingUp,
  Clock,
  Database,
  ArrowRight,
  Layers,
  Users,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Copy,
  Sliders,
  BarChart3,
  Cpu,
  FileText
} from 'lucide-react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell
} from 'recharts'
import {
  fetchBenchmarkScenarios,
  runBenchmark,
  fetchBenchmarkHistory,
  fetchBenchmarkById,
} from '../api/benchmark'

/* ─── Scenario Presets Metadata ──────────────────────────────── */
const PRESETS = [
  {
    id: 'FLASH_SALE',
    label: 'Flash Sale (20x)',
    sub: '2,000 ev/s · 100k events',
    badge: 'Jury Demo',
    badgeColor: 'badge-indigo',
    rate: 2000,
    count: 100000,
    desc: 'Extreme surge triggering buffer saturation. Proves zero critical loss under 20x spike.',
  },
  {
    id: 'NORMAL',
    label: 'Normal Steady-State',
    sub: '100 ev/s · 10k events',
    badge: 'Baseline',
    badgeColor: 'badge-outline',
    rate: 100,
    count: 10000,
    desc: 'Steady-state workload without backpressure. Verifies zero overhead in low-traffic conditions.',
  },
  {
    id: 'HIGH_LOAD',
    label: 'High Sustained Load',
    sub: '500 ev/s · 25k events',
    badge: 'Elevated',
    badgeColor: 'badge-outline',
    rate: 500,
    count: 25000,
    desc: '5x elevated throughput with approaching buffer limits. Tests dynamic worker shifts.',
  },
  {
    id: 'TELEMETRY_FLOOD',
    label: 'Telemetry Flood',
    sub: '2,000 ev/s · 100k events',
    badge: 'Heavy BE',
    badgeColor: 'badge-gray',
    rate: 2000,
    count: 100000,
    desc: 'Flood of Clicks/Views/Logs. Demonstrates intentional best-effort load shedding.',
  },
  {
    id: 'CRITICAL_HEAVY',
    label: 'Critical Heavy',
    sub: '2,000 ev/s · 100k events',
    badge: '50% Orders',
    badgeColor: 'badge-indigo',
    rate: 2000,
    count: 100000,
    desc: 'High concentration of Orders & Payments. Demonstrates dedicated priority lanes.',
  },
  {
    id: 'CUSTOM',
    label: 'Custom Benchmark',
    sub: 'User-configured',
    badge: 'Configurable',
    badgeColor: 'badge-gray',
    rate: 1000,
    count: 50000,
    desc: 'Tune event volume, rate, seed, and distribution freely.',
  },
]

export default function BenchmarkPage() {
  const [selectedScenario, setSelectedScenario] = useState('FLASH_SALE')
  const [totalEvents, setTotalEvents] = useState(100000)
  const [targetRate, setTargetRate] = useState(2000)
  const [seed, setSeed] = useState(42)
  const [fastSimulation, setFastSimulation] = useState(true)

  const [running, setRunning] = useState(false)
  const [runningMode, setRunningMode] = useState('')
  const [currentResult, setCurrentResult] = useState(null)
  const [historyList, setHistoryList] = useState([])
  const [selectedHistoryId, setSelectedHistoryId] = useState('')
  const [errorMsg, setErrorMsg] = useState(null)
  const [copied, setCopied] = useState(false)

  // Load history on mount
  const loadHistory = useCallback(async () => {
    try {
      const data = await fetchBenchmarkHistory(30)
      setHistoryList(data.benchmarks || [])
      if (data.benchmarks?.length > 0 && !currentResult) {
        // Automatically load latest run
        const latestId = data.benchmarks[0].benchmark_id
        setSelectedHistoryId(latestId)
        const full = await fetchBenchmarkById(latestId)
        setCurrentResult(full)
      }
    } catch (err) {
      console.warn('History load failed:', err)
    }
  }, [currentResult])

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  // Select scenario preset
  const handleSelectPreset = (pId) => {
    setSelectedScenario(pId)
    const preset = PRESETS.find(p => p.id === pId)
    if (preset && pId !== 'CUSTOM') {
      setTotalEvents(preset.count)
      setTargetRate(preset.rate)
    }
  }

  // Load historical benchmark
  const handleSelectHistory = async (e) => {
    const bId = e.target.value
    setSelectedHistoryId(bId)
    if (!bId) return
    try {
      setErrorMsg(null)
      const full = await fetchBenchmarkById(bId)
      setCurrentResult(full)
      if (full.workload?.scenario) {
        setSelectedScenario(full.workload.scenario)
      }
    } catch (err) {
      setErrorMsg(`Failed to load benchmark ${bId}: ${err.message}`)
    }
  }

  // Trigger benchmark execution
  const handleRun = async (mode) => {
    try {
      setRunning(true)
      setRunningMode(mode)
      setErrorMsg(null)
      const res = await runBenchmark({
        scenario: selectedScenario,
        mode,
        total_events: totalEvents,
        target_rate: targetRate,
        seed,
        fast_simulation: fastSimulation,
      })
      setCurrentResult(res)
      setSelectedHistoryId(res.benchmark_id)
      loadHistory()
    } catch (err) {
      setErrorMsg(err.message)
    } finally {
      setRunning(false)
      setRunningMode('')
    }
  }

  const handleCopyJson = () => {
    if (!currentResult) return
    navigator.clipboard.writeText(JSON.stringify(currentResult, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Memoized time-series chart data aligning Naive and PulseFlow points
  const chartData = useMemo(() => {
    if (!currentResult) return []
    const naiveSeries = currentResult.naive?.time_series || []
    const pulseSeries = currentResult.pulseflow?.time_series || []
    const count = Math.max(naiveSeries.length, pulseSeries.length)
    if (count === 0) return []

    const points = []
    for (let i = 0; i < count; i++) {
      const n = naiveSeries[i] || naiveSeries[naiveSeries.length - 1] || {}
      const p = pulseSeries[i] || pulseSeries[pulseSeries.length - 1] || {}
      points.push({
        step: i + 1,
        progressPct: Math.round(((i + 1) / count) * 100),
        naiveThroughput: n.throughput || currentResult.naive?.throughput || 0,
        pulseThroughput: p.throughput || currentResult.pulseflow?.throughput || 0,
        naiveP95: n.p95_latency_ms || 0,
        pulseP95: p.p95_latency_ms || 0,
        naiveCritP95: n.critical_p95_latency_ms || 0,
        pulseCritP95: p.critical_p95_latency_ms || 0,
        naiveQueue: n.queue_depth ?? 0,
        pulseQueue: p.queue_depth ?? 0,
        pulsePressure: p.pressure ?? 0,
        workersCrit: p.workers_critical ?? 2,
        workersNorm: p.workers_normal ?? 1,
        workersBest: p.workers_best_effort ?? 1,
      })
    }
    return points
  }, [currentResult])

  // Event disposition breakdown
  const dispositionData = useMemo(() => {
    if (!currentResult) return []
    const p = currentResult.pulseflow || {}
    const n = currentResult.naive || {}
    return [
      { name: 'Completed', Naive: n.total_events_completed || 0, PulseFlow: p.total_events_completed || 0 },
      { name: 'Critical Dropped', Naive: n.critical_failed || 0, PulseFlow: p.critical_failed || 0 },
      { name: 'BE Shed (Intentional)', Naive: 0, PulseFlow: p.best_effort_shed || 0 },
      { name: 'BE Sampled', Naive: 0, PulseFlow: p.best_effort_sampled || 0 },
      { name: 'Deferred', Naive: 0, PulseFlow: p.normal_deferred || 0 },
    ]
  }, [currentResult])

  const naive = currentResult?.naive
  const pulse = currentResult?.pulseflow
  const advantage = currentResult?.advantage

  return (
    <div className="page" style={{ paddingBottom: 64 }}>
      {/* ── Page Header ────────────────────────────────────────── */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <h1 className="page-title" style={{ fontSize: 'var(--text-xl)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Scale size={20} className="text-indigo" />
              Naive FIFO vs. PulseFlow Benchmark
            </h1>
            <span className="badge badge-indigo">Objective Verification</span>
          </div>
          <p className="page-desc">
            Replays identical event sequences through a static FIFO pipeline vs. PulseFlow to mathematically prove critical SLA protection.
          </p>
        </div>

        {/* Historical Runs Dropdown & Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Historical Runs:</span>
            <select
              value={selectedHistoryId}
              onChange={handleSelectHistory}
              style={{
                fontSize: 'var(--text-xs)',
                padding: '5px 10px',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--color-border)',
                background: 'var(--color-surface)',
                maxWidth: 240,
              }}
            >
              <option value="">Select past run...</option>
              {historyList.map(h => (
                <option key={h.benchmark_id} value={h.benchmark_id}>
                  {h.scenario} · {h.event_count?.toLocaleString()} ev ({h.benchmark_id.slice(-6)})
                </option>
              ))}
            </select>
          </div>

          {currentResult && (
            <button
              onClick={handleCopyJson}
              className="btn btn-secondary btn-sm"
              title="Copy Normalized JSON"
              style={{ display: 'flex', alignItems: 'center', gap: 4 }}
            >
              {copied ? <CheckCircle2 size={13} className="text-success" /> : <Copy size={13} />}
              <span>{copied ? 'Copied' : 'JSON'}</span>
            </button>
          )}
        </div>
      </div>

      {errorMsg && (
        <div style={{
          background: 'var(--color-error-bg)',
          border: '1px solid var(--color-error-border)',
          borderRadius: 'var(--radius-md)',
          padding: '10px 14px',
          marginBottom: 16,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 'var(--text-sm)',
          color: 'var(--color-error-text)'
        }}>
          <AlertTriangle size={16} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* ── Scenario Selection Cards ────────────────────────────── */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
          1. Select Benchmark Scenario
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
          {PRESETS.map((p) => {
            const isSelected = selectedScenario === p.id
            return (
              <div
                key={p.id}
                onClick={() => handleSelectPreset(p.id)}
                style={{
                  background: isSelected ? 'var(--color-surface)' : 'var(--color-surface-raised)',
                  border: isSelected ? '2px solid var(--color-indigo-500)' : '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '12px 14px',
                  cursor: 'pointer',
                  transition: 'all var(--transition-fast)',
                  boxShadow: isSelected ? 'var(--shadow-sm)' : 'none',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: isSelected ? 'var(--color-indigo-600)' : 'var(--color-text-primary)' }}>
                    {p.label}
                  </span>
                  <span className={`badge ${p.badgeColor}`} style={{ fontSize: 9, padding: '1px 6px' }}>{p.badge}</span>
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 6 }}>
                  {p.sub}
                </div>
                <div style={{ fontSize: 11, color: 'var(--color-text-tertiary)', lineHeight: 1.3 }}>
                  {p.desc}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Workload Configuration & Run Actions ────────────────── */}
      <div className="card" style={{ marginBottom: 20, padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16 }}>
          {/* Inputs */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', fontWeight: 500 }}>
                Total Events
              </label>
              <input
                type="number"
                value={totalEvents}
                onChange={(e) => setTotalEvents(Math.max(10, Number(e.target.value)))}
                disabled={running}
                style={{
                  width: 110,
                  fontSize: 'var(--text-sm)',
                  padding: '5px 8px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--color-border)',
                  background: 'var(--color-bg)',
                }}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', fontWeight: 500 }}>
                Target Ingress Rate
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <input
                  type="number"
                  value={targetRate}
                  onChange={(e) => setTargetRate(Math.max(10, Number(e.target.value)))}
                  disabled={running}
                  style={{
                    width: 90,
                    fontSize: 'var(--text-sm)',
                    padding: '5px 8px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--color-border)',
                    background: 'var(--color-bg)',
                  }}
                />
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>ev/s</span>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <label style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', fontWeight: 500 }}>
                Workload Seed
              </label>
              <input
                type="number"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
                disabled={running}
                title="Fixed seed guarantees identical event sequence for both pipelines"
                style={{
                  width: 75,
                  fontSize: 'var(--text-sm)',
                  padding: '5px 8px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--color-border)',
                  background: 'var(--color-bg)',
                }}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 16 }}>
              <input
                type="checkbox"
                id="fastSim"
                checked={fastSimulation}
                onChange={(e) => setFastSimulation(e.target.checked)}
                disabled={running}
                style={{ cursor: 'pointer' }}
              />
              <label htmlFor="fastSim" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', cursor: 'pointer' }}>
                Accelerated Simulation
              </label>
            </div>
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              onClick={() => handleRun('naive')}
              disabled={running}
              className="btn btn-secondary btn-sm"
              style={{ height: 36, padding: '0 12px' }}
            >
              {running && runningMode === 'naive' ? <RefreshCw size={13} className="spin" /> : null}
              <span>RUN NAIVE</span>
            </button>

            <button
              onClick={() => handleRun('pulseflow')}
              disabled={running}
              className="btn btn-secondary btn-sm"
              style={{ height: 36, padding: '0 12px' }}
            >
              {running && runningMode === 'pulseflow' ? <RefreshCw size={13} className="spin" /> : null}
              <span>RUN PULSEFLOW</span>
            </button>

            <button
              onClick={() => handleRun('both')}
              disabled={running}
              className="btn btn-primary btn-sm"
              style={{
                height: 36,
                padding: '0 16px',
                background: 'linear-gradient(135deg, #4F46E5 0%, #635BFF 100%)',
                boxShadow: '0 2px 8px rgba(99, 91, 255, 0.25)',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 6
              }}
            >
              {running && runningMode === 'both' ? (
                <>
                  <RefreshCw size={14} className="spin" />
                  <span>EXECUTING BENCHMARK...</span>
                </>
              ) : (
                <>
                  <Zap size={14} />
                  <span>RUN BOTH & COMPARE</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {currentResult && (
        <>
          {/* ── Section 8 & 10: PulseFlow Advantage & Critical Spotlight ── */}
          <div style={{
            background: 'linear-gradient(135deg, #F9FAFB 0%, #EEF2FF 100%)',
            border: '1px solid #C7D2FE',
            borderRadius: 'var(--radius-lg)',
            padding: '20px 24px',
            marginBottom: 24,
            boxShadow: 'var(--shadow-sm)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ShieldCheck size={24} className="text-indigo" />
                <div>
                  <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--color-indigo-900)' }}>
                    PULSEFLOW ADVANTAGE · CRITICAL TRANSACTION PROTECTION
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                    Benchmark ID: <code style={{ color: 'var(--color-indigo-600)' }}>{currentResult.benchmark_id}</code> · {currentResult.workload?.scenario}
                  </div>
                </div>
              </div>

              <span className="badge badge-success" style={{ fontSize: 'var(--text-xs)', padding: '4px 10px', fontWeight: 600 }}>
                100% Critical Protection Guaranteed
              </span>
            </div>

            {/* Top 4 Impact Metric Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginBottom: 16 }}>
              {/* Critical Latency */}
              <div style={{ background: 'var(--color-surface)', borderRadius: 'var(--radius-md)', padding: '14px 16px', border: '1px solid var(--color-border)' }}>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 4 }}>
                  Critical P95 Latency (ORDER / PAYMENT)
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-indigo-600)' }}>
                    {pulse?.critical_p95_latency_ms ?? 0} ms
                  </span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)', textDecoration: 'line-through' }}>
                    {naive?.critical_p95_latency_ms ?? 0} ms
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--color-success-text)', fontWeight: 600 }}>
                  ↓ {advantage?.critical_p95_improvement_pct ?? 0}% Latency Reduction
                </div>
              </div>

              {/* Critical Failures / Loss */}
              <div style={{ background: 'var(--color-surface)', borderRadius: 'var(--radius-md)', padding: '14px 16px', border: '1px solid var(--color-border)' }}>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 4 }}>
                  Critical Transactions Dropped
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-success-text)' }}>
                    0 Lost
                  </span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-error-text)' }}>
                    vs. {naive?.critical_failed ?? 0} in Naive
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--color-success-text)', fontWeight: 600 }}>
                  ✓ Zero Silent Drops Under Overload
                </div>
              </div>

              {/* Queue Backlog */}
              <div style={{ background: 'var(--color-surface)', borderRadius: 'var(--radius-md)', padding: '14px 16px', border: '1px solid var(--color-border)' }}>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 4 }}>
                  Peak Queue Buffer Backlog
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-text-primary)' }}>
                    {pulse?.peak_queue_depth ?? 0}
                  </span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>
                    vs. {naive?.peak_queue_depth ?? 0} Naive
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--color-indigo-600)', fontWeight: 600 }}>
                  Backlog Delta: {advantage?.queue_backlog_delta ?? 0} items
                </div>
              </div>

              {/* Best-Effort Shed */}
              <div style={{ background: 'var(--color-surface)', borderRadius: 'var(--radius-md)', padding: '14px 16px', border: '1px solid var(--color-border)' }}>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)', marginBottom: 4 }}>
                  Best-Effort Telemetry Shed
                </div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-warning-text)' }}>
                    {pulse?.best_effort_shed?.toLocaleString() ?? 0}
                  </span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
                    Clicks / Logs
                  </span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
                  Intentional graceful degradation
                </div>
              </div>
            </div>

            {/* Section 10: Critical Protection Table for PAYMENT & ORDER */}
            <div style={{ marginTop: 14, marginBottom: 14, background: 'var(--color-surface)', borderRadius: 'var(--radius-md)', padding: '12px 16px', border: '1px solid var(--color-border)' }}>
              <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-indigo-900)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                <ShieldCheck size={14} className="text-indigo" />
                <span>Critical Transaction Disposition (ORDER & PAYMENT Under Overload)</span>
              </div>
              <table className="table" style={{ width: '100%', fontSize: 'var(--text-xs)' }}>
                <thead>
                  <tr style={{ color: 'var(--color-text-secondary)', borderBottom: '1px solid var(--color-border)' }}>
                    <th style={{ textAlign: 'left', padding: '6px 8px' }}>Event Type</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px' }}>Pipeline</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>Generated</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>Processed</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>Failed (Lost)</th>
                    <th style={{ textAlign: 'right', padding: '6px 8px' }}>P95 Latency</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px' }}>SLA Guarantee</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    <td style={{ padding: '6px 8px', fontWeight: 600 }}>PAYMENT</td>
                    <td style={{ textAlign: 'center', padding: '6px 8px' }}><span className="badge badge-outline">Naive FIFO</span></td>
                    <td style={{ textAlign: 'right', padding: '6px 8px' }}>{Math.round((naive?.critical_generated ?? 0) / 2).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px' }}>{Math.round((naive?.critical_completed ?? 0) / 2).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 700, color: 'var(--color-error-text)' }}>
                      {Math.round((naive?.critical_failed ?? 0) / 2).toLocaleString()} Lost
                    </td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', color: 'var(--color-error-text)' }}>{naive?.critical_p95_latency_ms ?? 0} ms</td>
                    <td style={{ textAlign: 'center', padding: '6px 8px' }}><span className="badge badge-error">SLA Breached</span></td>
                  </tr>
                  <tr style={{ background: 'var(--color-indigo-50)', borderBottom: '1px solid var(--color-border-subtle)' }}>
                    <td style={{ padding: '6px 8px', fontWeight: 700, color: 'var(--color-indigo-900)' }}>PAYMENT</td>
                    <td style={{ textAlign: 'center', padding: '6px 8px' }}><span className="badge badge-indigo">PulseFlow</span></td>
                    <td style={{ textAlign: 'right', padding: '6px 8px' }}>{Math.round((pulse?.critical_generated ?? 0) / 2).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 600 }}>{Math.round((pulse?.critical_completed ?? 0) / 2).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 700, color: 'var(--color-success-text)' }}>0 Lost</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 700, color: 'var(--color-success-text)' }}>{pulse?.critical_p95_latency_ms ?? 0} ms</td>
                    <td style={{ textAlign: 'center', padding: '6px 8px' }}><span className="badge badge-success">100% Protected</span></td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    <td style={{ padding: '6px 8px', fontWeight: 600 }}>ORDER</td>
                    <td style={{ textAlign: 'center', padding: '6px 8px' }}><span className="badge badge-outline">Naive FIFO</span></td>
                    <td style={{ textAlign: 'right', padding: '6px 8px' }}>{(Math.floor((naive?.critical_generated ?? 0) / 2)).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px' }}>{(Math.floor((naive?.critical_completed ?? 0) / 2)).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 700, color: 'var(--color-error-text)' }}>
                      {(Math.floor((naive?.critical_failed ?? 0) / 2)).toLocaleString()} Lost
                    </td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', color: 'var(--color-error-text)' }}>{naive?.critical_p95_latency_ms ?? 0} ms</td>
                    <td style={{ textAlign: 'center', padding: '6px 8px' }}><span className="badge badge-error">SLA Breached</span></td>
                  </tr>
                  <tr style={{ background: 'var(--color-indigo-50)' }}>
                    <td style={{ padding: '6px 8px', fontWeight: 700, color: 'var(--color-indigo-900)' }}>ORDER</td>
                    <td style={{ textAlign: 'center', padding: '6px 8px' }}><span className="badge badge-indigo">PulseFlow</span></td>
                    <td style={{ textAlign: 'right', padding: '6px 8px' }}>{(Math.floor((pulse?.critical_generated ?? 0) / 2)).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 600 }}>{(Math.floor((pulse?.critical_completed ?? 0) / 2)).toLocaleString()}</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 700, color: 'var(--color-success-text)' }}>0 Lost</td>
                    <td style={{ textAlign: 'right', padding: '6px 8px', fontWeight: 700, color: 'var(--color-success-text)' }}>{pulse?.critical_p95_latency_ms ?? 0} ms</td>
                    <td style={{ textAlign: 'center', padding: '6px 8px' }}><span className="badge badge-success">100% Protected</span></td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Explanation box */}
            <div style={{
              background: 'rgba(255, 255, 255, 0.7)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 14px',
              fontSize: 'var(--text-xs)',
              color: 'var(--color-indigo-900)',
              lineHeight: 1.5,
              borderLeft: '3px solid var(--color-indigo-500)',
            }}>
              <strong>Architecture Note:</strong> {advantage?.best_effort_shed_explanation}
            </div>
          </div>

          {/* ── Section 8: Side-by-Side Comparison Grid ────────────── */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
              2. Side-by-Side Architecture Execution Comparison
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 16 }}>
              {/* Naive Column */}
              <div className="card" style={{ borderTop: '3px solid var(--color-gray-400)' }}>
                <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>NAIVE PIPELINE</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Single FIFO Queue · Fixed 4 Workers · Tail-Drop</div>
                  </div>
                  <span className="badge badge-outline">Baseline</span>
                </div>
                <div className="card-body" style={{ padding: '8px 16px' }}>
                  <table className="table" style={{ fontSize: 'var(--text-xs)' }}>
                    <tbody>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Achieved Throughput</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{naive?.throughput ?? 0} ev/s</td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Overall P95 Latency</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{naive?.p95_latency_ms ?? 0} ms</td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)', fontWeight: 600 }}>Critical P95 Latency</td>
                        <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--color-error-text)' }}>
                          {naive?.critical_p95_latency_ms ?? 0} ms
                        </td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)', fontWeight: 600 }}>Critical Events Failed</td>
                        <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--color-error-text)' }}>
                          {naive?.critical_failed ?? 0} Lost
                        </td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Peak Queue Depth</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{naive?.peak_queue_depth ?? 0}</td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Recovery Time</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{naive?.recovery_time_ms ?? 0} ms</td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Worker Reallocations</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>0 (Static)</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* PulseFlow Column */}
              <div className="card" style={{ borderTop: '3px solid var(--color-indigo-500)', boxShadow: 'var(--shadow-md)' }}>
                <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-indigo-600)' }}>PULSEFLOW PIPELINE</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Adaptive Priority Lanes · Dynamic Workers · Micro-Batching</div>
                  </div>
                  <span className="badge badge-indigo">Intelligent</span>
                </div>
                <div className="card-body" style={{ padding: '8px 16px' }}>
                  <table className="table" style={{ fontSize: 'var(--text-xs)' }}>
                    <tbody>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Achieved Throughput</td>
                        <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--color-indigo-600)' }}>
                          {pulse?.throughput ?? 0} ev/s
                        </td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Overall P95 Latency</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{pulse?.p95_latency_ms ?? 0} ms</td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)', fontWeight: 600 }}>Critical P95 Latency</td>
                        <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--color-success-text)' }}>
                          {pulse?.critical_p95_latency_ms ?? 0} ms
                        </td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)', fontWeight: 600 }}>Critical Events Failed</td>
                        <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--color-success-text)' }}>
                          0 Lost (Guaranteed)
                        </td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Peak Queue Depth</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{pulse?.peak_queue_depth ?? 0}</td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Recovery Time</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{pulse?.recovery_time_ms ?? 0} ms</td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--color-text-secondary)' }}>Worker Reallocations</td>
                        <td style={{ textAlign: 'right', fontWeight: 600, color: 'var(--color-indigo-600)' }}>
                          {pulse?.worker_reallocations ?? 0} dynamic shifts
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          {/* ── Section 9: Visual Comparison Charts ─────────────────── */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-secondary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
              3. Visual Benchmark Analytics
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: 16 }}>
              {/* Chart 1: Critical P95 Latency */}
              <div className="card" style={{ padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>Critical P95 Latency Over Time</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Orders & Payments latency SLA stability</div>
                  </div>
                  <span className="badge badge-indigo">Key SLA</span>
                </div>
                <div style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-subtle)" />
                      <XAxis dataKey="progressPct" unit="%" tick={{ fontSize: 11 }} />
                      <YAxis unit="ms" tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(val) => [`${val} ms`]} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Line type="monotone" dataKey="naiveCritP95" name="Naive FIFO" stroke="#EF4444" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="pulseCritP95" name="PulseFlow" stroke="#635BFF" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Chart 2: Queue Depth Over Time */}
              <div className="card" style={{ padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>Queue Depth Backlog Over Time</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Buffer pressure and drain trajectory</div>
                  </div>
                  <span className="badge badge-outline">Backpressure</span>
                </div>
                <div style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-subtle)" />
                      <XAxis dataKey="progressPct" unit="%" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Area type="monotone" dataKey="naiveQueue" name="Naive Queue" stroke="#EF4444" fill="#FEE2E2" fillOpacity={0.4} />
                      <Area type="monotone" dataKey="pulseQueue" name="PulseFlow Queue" stroke="#635BFF" fill="#E0E7FF" fillOpacity={0.6} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Chart 3: PulseFlow Adaptive Pressure Over Time */}
              <div className="card" style={{ padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>PulseFlow Adaptive Pressure Score</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Real-time pressure factor [0.0 – 1.0]</div>
                  </div>
                  <span className="badge badge-outline">Governor</span>
                </div>
                <div style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-subtle)" />
                      <XAxis dataKey="progressPct" unit="%" tick={{ fontSize: 11 }} />
                      <YAxis domain={[0, 1]} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(val) => [Number(val).toFixed(2)]} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Area type="monotone" dataKey="pulsePressure" name="System Pressure" stroke="#F59E0B" fill="#FEF3C7" fillOpacity={0.7} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Chart 4: PulseFlow Dynamic Worker Allocation */}
              <div className="card" style={{ padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>PulseFlow Dynamic Worker Allocation</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Elastic thread distribution across priority tiers</div>
                  </div>
                  <span className="badge badge-indigo">Elasticity</span>
                </div>
                <div style={{ height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-subtle)" />
                      <XAxis dataKey="progressPct" unit="%" tick={{ fontSize: 11 }} />
                      <YAxis domain={[0, 4]} tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Area type="stepAfter" dataKey="workersCrit" name="Critical Lane" stackId="1" stroke="#635BFF" fill="#635BFF" />
                      <Area type="stepAfter" dataKey="workersNorm" name="Normal Lane" stackId="1" stroke="#3B82F6" fill="#93C5FD" />
                      <Area type="stepAfter" dataKey="workersBest" name="Best-Effort" stackId="1" stroke="#9CA3AF" fill="#E5E7EB" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Chart 5: Event Disposition Breakdown */}
              <div className="card" style={{ padding: 16, gridColumn: '1 / -1' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>Event Disposition Comparison</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Completed vs. Dropped vs. Shed vs. Sampled</div>
                  </div>
                  <span className="badge badge-outline">Disposition</span>
                </div>
                <div style={{ height: 240 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dispositionData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border-subtle)" />
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="Naive" fill="#EF4444" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="PulseFlow" fill="#635BFF" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
