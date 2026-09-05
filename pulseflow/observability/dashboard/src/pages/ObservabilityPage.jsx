import React, { useState, useEffect, useRef } from 'react'
import {
  Activity, Layers, Users, GitBranch, Clock,
  TrendingUp, AlertTriangle, CheckCircle, Zap, Shield, Target,
  Flame, RefreshCw, Filter, Sparkles, Pause, Play
} from 'lucide-react'
import {
  AreaChart, Area, ComposedChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'
import { telemetryService } from '../api/telemetry'

/* ─── Event Tier Metadata ─────────────────────────────────── */
const EVENT_TIER_META = {
  ORDER:             { tier: 'Critical',    color: 'var(--color-indigo-500)', isCritical: true  },
  PAYMENT:           { tier: 'Critical',    color: 'var(--color-indigo-600)', isCritical: true  },
  CART_ADD:          { tier: 'Normal',      color: '#3b82f6',                 isCritical: false },
  INVENTORY_UPDATE:  { tier: 'Normal',      color: '#60a5fa',                 isCritical: false },
  CLICK:             { tier: 'Best Effort', color: '#94a3b8',                 isCritical: false },
  PAGE_VIEW:         { tier: 'Best Effort', color: '#cbd5e1',                 isCritical: false },
  LOG:               { tier: 'Best Effort', color: '#e2e8f0',                 isCritical: false },
};

const TIER_FALLBACK = {
  CRITICAL:    { tier: 'Critical',    color: 'var(--color-indigo-500)', isCritical: true  },
  NORMAL:      { tier: 'Normal',      color: '#3b82f6',                 isCritical: false },
  BEST_EFFORT: { tier: 'Best Effort', color: '#94a3b8',                 isCritical: false },
};

function computeEventMix(recentEventTypes) {
  if (!recentEventTypes || recentEventTypes.length === 0) return [];
  const counts = {};
  recentEventTypes.forEach(({ type }) => {
    counts[type] = (counts[type] ?? 0) + 1;
  });
  const total = recentEventTypes.length;
  return Object.entries(counts)
    .map(([type, count]) => {
      const byType = EVENT_TIER_META[type];
      const byTier = TIER_FALLBACK[recentEventTypes.find(e => e.type === type)?.tier];
      const meta   = byType ?? byTier ?? { tier: 'Normal', color: 'var(--color-gray-400)', isCritical: false };
      return { type, tier: meta.tier, color: meta.color, isCritical: meta.isCritical, pct: Math.round((count / total) * 100), count };
    })
    .sort((a, b) => b.pct - a.pct || a.type.localeCompare(b.type));
}

/* ─── Compact Metric with Gesture Lift ────────────────────── */
function CompactMetric({ label, value, subValue, icon: Icon, valueColor, highlight = false }) {
  return (
    <div
      className={`metric-card ${highlight ? 'card-interactive' : ''}`}
      style={{
        padding: 'var(--space-3) var(--space-4)',
        cursor: 'default',
        transition: 'transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s ease, border-color 0.25s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div className="metric-label" style={{ margin: 0 }}>{label}</div>
        {Icon && <Icon size={12} style={{ color: 'var(--color-text-tertiary)', opacity: 0.8 }} />}
      </div>
      <div className="metric-value" style={{ fontSize: 'var(--text-xl)', color: valueColor || 'var(--color-text-primary)' }}>
        {value}
        {subValue && <span className="metric-unit" style={{ fontSize: 'var(--text-xs)' }}>{subValue}</span>}
      </div>
    </div>
  )
}

function SectionHeading({ children }) {
  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <h2 style={{
        fontSize: 'var(--text-md)',
        fontWeight: 700,
        letterSpacing: '-0.01em',
        color: 'var(--color-text-primary)',
        textTransform: 'uppercase',
      }}>
        {children}
      </h2>
    </div>
  )
}

function getStatusColor(status) {
  if (status === 'STREAM') return 'badge-success badge-pulse-green';
  if (status === 'MICRO-BATCH') return 'badge-indigo badge-pulse-indigo';
  if (status === 'DEFER') return 'badge-warning badge-pulse-amber';
  if (status === 'SAMPLE') return 'badge-gray';
  if (status === 'SHED') return 'badge-error badge-pulse-red';
  return 'badge-gray';
}

/* ─── Waveform Interactive Glassmorphism Tooltip ──────────── */
function WaveformTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;

  return (
    <div className="waveform-glass-tooltip">
      <div className="tooltip-top-row">
        <span className="tooltip-clock">{point.time}</span>
        <span className="tooltip-total-badge font-mono">
          Backlog: {(point.total ?? 0).toLocaleString()} items
        </span>
      </div>

      <div className="tooltip-divider" />

      {/* Tiers Breakdown */}
      <div className="tooltip-tiers-list">
        <div className="tooltip-tier-item">
          <div className="tier-name">
            <span className="dot dot-tier1" />
            <span>Tier 1 (Critical)</span>
          </div>
          <div className="tier-stat font-mono" style={{ color: 'var(--color-indigo-600)', fontWeight: 700 }}>
            {point.tier1 ?? 0}
            <span className="tier-tag tag-protected">Zero Shedding</span>
          </div>
        </div>

        <div className="tooltip-tier-item">
          <div className="tier-name">
            <span className="dot dot-tier2" />
            <span>Tier 2 (Normal)</span>
          </div>
          <div className="tier-stat font-mono" style={{ fontWeight: 600 }}>
            {point.tier2 ?? 0}
          </div>
        </div>

        <div className="tooltip-tier-item">
          <div className="tier-name">
            <span className="dot dot-tier3" />
            <span>Tier 3 (Best Effort)</span>
          </div>
          <div className="tier-stat font-mono" style={{ fontWeight: 600, color: 'var(--color-text-secondary)' }}>
            {point.tier3 ?? 0}
          </div>
        </div>
      </div>

      <div className="tooltip-divider" />

      {/* Ingress / Egress dynamics */}
      <div className="tooltip-metrics-grid">
        <div>
          <div className="metric-k">Ingress</div>
          <div className="metric-v font-mono" style={{ color: 'var(--color-success-text)' }}>{(point.ingress ?? 0).toLocaleString()} ev/s</div>
        </div>
        <div>
          <div className="metric-k">Drain</div>
          <div className="metric-v font-mono" style={{ color: '#8B5CF6' }}>{(point.throughput ?? 0).toLocaleString()} ev/s</div>
        </div>
        <div>
          <div className="metric-k">Latency</div>
          <div className="metric-v font-mono">{(point.latency ?? 0).toFixed(1)} ms</div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   ObservabilityPage — Machine 2 Main Telemetry & Gestures
═══════════════════════════════════════════════════════════ */
export default function ObservabilityPage() {
  const [streamData, setStreamData] = useState([])
  const [waveformData, setWaveformData] = useState([])
  const [connected, setConnected] = useState(false)
  const [eventMix, setEventMix] = useState([])

  const [metrics, setMetrics] = useState({
    queueSize: 0,
    latency: 0,
    workerLoad: 0,
    processingCost: 'LOW',
    isSpikeMode: false,
    ingress: 0,
    throughput: 0,
    pressureState: 'NORMAL',
    pressureScore: 0
  })

  const [infraMetrics, setInfraMetrics] = useState({
    queueT1: 0, latT1: 0,
    queueT2: 0, latT2: 0,
    queueT3: 0, latT3: 0,
    w1: 0, w2: 0, w3: 0, w4: 0,
    totalWorkers: 8
  })

  const [shedStats, setShedStats] = useState({
    shed: 0,
    deferred: 0,
    sampled: 0,
    sampled_kept: 0,
    sampled_dropped: 0,
    batched: 0,
    streamed: 0,
    critical_protected: 0,
  })

  const [selectedTierFilter, setSelectedTierFilter] = useState('ALL')
  const [waveformView, setWaveformView] = useState('TIERS') // 'TIERS' | 'FLOW' | 'TOTAL'
  const [waveformWindow, setWaveformWindow] = useState(60)  // 30 | 60 | 120
  const [tierVisibility, setTierVisibility] = useState({ tier1: true, tier2: true, tier3: true })
  const [isWaveformPaused, setIsWaveformPaused] = useState(false)
  const [pausedSnapshot, setPausedSnapshot] = useState(null)

  useEffect(() => {
    const unsubTelemetry = telemetryService.onTelemetryUpdate((data) => {
      setMetrics(data.metrics);
      setInfraMetrics(data.infraMetrics);
      setShedStats({ ...data.shedStats });

      setEventMix(computeEventMix(data.recentEventTypes ?? []));

      // Accumulate rich real-time waveform data points (up to 120 points for 2m buffer)
      setWaveformData(prev => {
        const point = {
          time: new Date().toISOString().substring(11, 19),
          total: data.metrics.queueSize ?? 0,
          events: data.metrics.queueSize ?? 0,
          tier1: data.infraMetrics?.queueT1 ?? 0,
          tier2: data.infraMetrics?.queueT2 ?? 0,
          tier3: data.infraMetrics?.queueT3 ?? 0,
          ingress: Math.round(data.metrics.ingress ?? 0),
          throughput: Math.round(data.metrics.throughput ?? 0),
          latency: Number(data.metrics.latency ?? 0),
          pressureScore: Number(data.metrics.pressureScore ?? 0),
        };
        return [...prev, point].slice(-120);
      });
    });

    const unsubEvents = telemetryService.onNewEvent((evt) => {
      setStreamData(prev => [{
        ...evt,
        statusColor: getStatusColor(evt.status),
        receivedKey: `${evt.id}-${Date.now()}`
      }, ...prev].slice(0, 12));
    });

    const unsubConnection = telemetryService.onConnectionChange((status) => {
      setConnected(status);
    });

    return () => {
      unsubTelemetry();
      unsubEvents();
      unsubConnection();
    }
  }, []);

  // Workload and active pressure detection
  // The governor should only highlight and enter extreme/high mode when there is an active spike or backlog
  const rawPressureState = metrics.pressureState ?? 'NORMAL';
  const hasActiveTraffic = (metrics.ingress > 1.0) || (metrics.queueSize > 0) || (metrics.workerLoad > 10) || (metrics.isSpikeMode && metrics.ingress > 0);
  
  // Real active pressure: if there's no active traffic and queue is clear, the system is in NORMAL standby
  const pressureState = (!hasActiveTraffic && metrics.queueSize === 0) ? 'NORMAL' : rawPressureState;
  const isHigh = pressureState === 'HIGH';
  const isExtreme = pressureState === 'EXTREME';

  // Filtered stream table data
  const filteredStream = streamData.filter(evt => {
    if (selectedTierFilter === 'ALL') return true;
    if (selectedTierFilter === 'CRITICAL') return evt.tier === 'Critical';
    if (selectedTierFilter === 'NORMAL') return evt.tier === 'Normal';
    if (selectedTierFilter === 'BEST_EFFORT') return evt.tier === 'Best Effort';
    return true;
  });

  // Calculations for Degradation & Protection counters
  const explicitShed = shedStats.shed ?? 0;
  const sampledDropped = shedStats.sampled_dropped ?? (shedStats.sampled ? Math.round(shedStats.sampled * 0.5) : 0);
  const totalShedEvents = explicitShed + sampledDropped;
  const shedSubtitle = totalShedEvents > 0
    ? (explicitShed > 0 && sampledDropped > 0
        ? `${explicitShed.toLocaleString()} policy shed • ${sampledDropped.toLocaleString()} sampled out`
        : (sampledDropped > 0 ? `${sampledDropped.toLocaleString()} best-effort dropped` : 'Best-effort shed under surge'))
    : 'Best-effort dropped (0 dropped)';

  const explicitDeferred = shedStats.deferred ?? 0;
  const batchedEvents = shedStats.batched ?? 0;
  const totalDeferredEvents = explicitDeferred + batchedEvents;
  const deferredSubtitle = totalDeferredEvents > 0
    ? (explicitDeferred > 0 && batchedEvents > 0
        ? `${explicitDeferred.toLocaleString()} held • ${batchedEvents.toLocaleString()} micro-batched`
        : (batchedEvents > 0 ? `${batchedEvents.toLocaleString()} normal batches delayed` : `${explicitDeferred.toLocaleString()} normal held back`))
    : 'Normal batches delayed (0 delayed)';

  const sampledKept = shedStats.sampled_kept ?? (shedStats.sampled ? (shedStats.sampled - sampledDropped) : 0);
  const sampledSubtitle = (shedStats.sampled ?? 0) > 0
    ? `${sampledKept.toLocaleString()} kept pass-through • ${sampledDropped.toLocaleString()} dropped`
    : 'Sampled pass-through';

  const protectedCount = (shedStats.critical_protected ?? 0) || (shedStats.streamed ?? 0);

  // Waveform derived metrics, live head & window slice
  const liveSlice = waveformData.slice(-waveformWindow);
  const visibleWaveform = (isWaveformPaused && pausedSnapshot) ? pausedSnapshot : liveSlice;
  const peakBacklog = Math.max(...visibleWaveform.map(d => d.total || 0), 0);
  const latestPoint = visibleWaveform.length > 0 ? visibleWaveform[visibleWaveform.length - 1] : null;
  const netVelocity = Math.round((metrics.ingress ?? 0) - (metrics.throughput ?? 0));
  const drainEta = metrics.queueSize === 0
    ? 'Clear'
    : (metrics.throughput > 0
        ? `~${(metrics.queueSize / metrics.throughput).toFixed(1)}s`
        : 'Holding');

  const toggleWaveformPause = () => {
    if (!isWaveformPaused) {
      setPausedSnapshot(waveformData.slice(-waveformWindow));
      setIsWaveformPaused(true);
    } else {
      setIsWaveformPaused(false);
      setPausedSnapshot(null);
    }
  };

  return (
    <>
      {/* ── Top Page Header ───────────────────────────────────── */}
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <h1 className="page-header-title" style={{ margin: 0 }}>PulseFlow Observability</h1>
          <span
            id="backend-connection-status"
            className={`status-pill ${connected ? 'status-pill-online' : 'status-pill-error'}`}
            title={connected ? 'Backend telemetry reachable' : 'Backend unreachable — polling'}
          >
            <span className={`status-dot status-dot-sm ${connected ? 'status-dot-live-green' : 'status-dot-live-red'}`} />
            {connected ? 'LIVE' : 'DISCONNECTED'}
          </span>

          {isExtreme && (
            <span className="badge badge-error badge-pulse-red" style={{ padding: '4px 10px' }}>
              <Flame size={12} strokeWidth={2.5} /> EXTREME PRESSURE SURGE
            </span>
          )}
          {!isExtreme && isHigh && (
            <span className="badge badge-warning" style={{ padding: '4px 10px' }}>
              <AlertTriangle size={12} strokeWidth={2.5} /> HIGH PRESSURE ACTIVE
            </span>
          )}
        </div>

        {/* Live Visual Telemetry Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <div className="stat-pill" title="Current Ingress Velocity">
            <span className="stat-pill-label">Ingress</span>
            <span className="stat-pill-divider" />
            <span className="stat-pill-value font-mono">
              {(metrics.ingress ?? 0).toFixed(1)} <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)', fontWeight: 400 }}>ev/s</span>
            </span>
          </div>

          <div className="stat-pill" title="Backlog Queue Depth">
            <span className="stat-pill-label">Backlog</span>
            <span className="stat-pill-divider" />
            <span className="stat-pill-value font-mono">
              {metrics.queueSize.toLocaleString()}
            </span>
          </div>

          <div className="stat-pill" title="Net Drain Velocity (Ingress vs Throughput)">
            <span className="stat-pill-label">Drain Flow</span>
            <span className="stat-pill-divider" />
            <span className="stat-pill-value font-mono" style={{ color: netVelocity > 0 ? 'var(--color-warning)' : 'var(--color-success-text)' }}>
              {netVelocity > 0 ? `+${netVelocity}` : netVelocity} <span style={{ fontSize: 10, fontWeight: 400 }}>ev/s</span>
            </span>
          </div>

          <div className="stat-pill" title="Zero Loss Guarantee Invariant">
            <span className="stat-pill-label">Critical SLA</span>
            <span className="stat-pill-divider" />
            <span className="stat-pill-value" style={{ color: 'var(--color-success-text)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <span className="status-dot status-dot-live-green" style={{ width: 6, height: 6 }} />
              0 Lost
            </span>
          </div>
        </div>
      </div>

      <div
        className="page"
        id="observability-content"
        style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)', overflowY: 'auto' }}
      >

        {/* ── 1. SYSTEM OVERVIEW ────────────────────────── */}
        <section>
          <SectionHeading>1. System Overview</SectionHeading>
          <div className="grid grid-cols-6" style={{ gap: 'var(--space-3)' }}>
            <CompactMetric
              label="Queue Depth"
              value={metrics.queueSize.toLocaleString()}
              icon={Layers}
              highlight
            />
            <CompactMetric
              label="Ingress Rate"
              value={(metrics.ingress ?? 0).toFixed(1)}
              subValue=" ev/s"
              icon={TrendingUp}
              highlight
            />
            <CompactMetric
              label="System Load"
              value={`${metrics.workerLoad}%`}
              icon={Activity}
              highlight
            />
            <CompactMetric
              label="Pressure"
              value={pressureState}
              icon={isExtreme ? Flame : AlertTriangle}
              valueColor={isExtreme ? 'var(--color-error)' : isHigh ? 'var(--color-warning)' : 'var(--color-success-text)'}
              highlight
            />
            <CompactMetric
              label="Governor"
              value={pressureState === 'NORMAL' ? 'STANDBY' : 'ADAPTIVE'}
              icon={Shield}
              valueColor={pressureState !== 'NORMAL' ? 'var(--color-indigo-600)' : 'var(--color-text-secondary)'}
              highlight
            />
            <CompactMetric
              label="Pressure Score"
              value={(metrics.pressureScore ?? 0).toFixed(3)}
              icon={Target}
              highlight
            />
          </div>
        </section>

        {/* ── 2. ADAPTIVE GOVERNOR ──────────────────────── */}
        <section>
          <SectionHeading>2. Adaptive Governor &amp; Strategies</SectionHeading>
          <div className="grid grid-cols-3" style={{ gap: 'var(--space-4)' }}>
            
            {/* Governor State Card with Dynamic Glow Aura */}
            <div
              className={`card ${isExtreme ? 'pressure-extreme-aura' : isHigh ? 'pressure-high-aura' : ''}`}
              style={{
                padding: 'var(--space-5)',
                transition: 'all 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
                <div className="card-title" style={{ margin: 0 }}>
                  {pressureState} LOAD GOVERNOR
                </div>
                <span className={`status-dot ${isExtreme ? 'status-dot-live-red' : isHigh ? 'status-dot-warning' : 'status-dot-live-green'}`} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>QUEUE PRESSURE</span>
                  <span style={{ fontWeight: 700, color: isExtreme ? 'var(--color-error)' : isHigh ? 'var(--color-warning)' : 'var(--color-success-text)' }}>
                    {pressureState}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>BACKLOG QUEUE</span>
                  <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{metrics.queueSize.toLocaleString()} items</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>ACTIVE WORKER LOAD</span>
                  <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{metrics.workerLoad}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>PROCESSING COST</span>
                  <span style={{ fontWeight: 600 }}>{metrics.processingCost}</span>
                </div>
                <div className="divider" style={{ margin: '4px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>GOVERNOR STATUS</span>
                  <span style={{ fontWeight: 700, color: pressureState !== 'NORMAL' ? 'var(--color-indigo-600)' : 'var(--color-success-text)' }}>
                    {pressureState === 'NORMAL' ? 'STANDBY' : 'ADAPTIVE SHIELD'}
                  </span>
                </div>
              </div>
            </div>

            {/* Current Processing Decisions with Pulsing Badges */}
            <div className="card col-span-2" style={{ padding: 'var(--space-5)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
                <div className="card-title">Active Priority Lane Policies</div>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>Zero critical degradation invariant enforced</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {/* Critical Lane */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 14px',
                  background: 'rgba(99, 91, 255, 0.04)',
                  border: '1px solid rgba(99, 91, 255, 0.15)',
                  borderRadius: 'var(--radius-sm)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                    <span className="dot dot-tier1" />
                    <div>
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-indigo-700)' }}>
                        Tier 1: Critical
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--color-indigo-600)', fontWeight: 600 }}>
                        Payments &amp; Orders • 0 Shedding Guarantee
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-indigo-600)' }}>W1 Dedicated</div>
                      <div style={{ fontSize: '10px', color: 'var(--color-text-tertiary)' }}>{(infraMetrics.queueT1 ?? 0).toLocaleString()} queued</div>
                    </div>
                    <span className="badge badge-success badge-pulse-green">
                      STREAM
                    </span>
                  </div>
                </div>

                {/* Normal Lane */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 14px',
                  background: 'var(--color-gray-50)',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 'var(--radius-sm)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                    <span className="dot dot-tier2" />
                    <div>
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                        Tier 2: Normal
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', fontWeight: 500 }}>
                        Cart Add &amp; Inventory • SLA &lt; 150ms
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: isExtreme ? 'var(--color-warning)' : 'var(--color-text-primary)' }}>
                        {isExtreme ? 'W2 Throttled' : 'W2 Vectorized'}
                      </div>
                      <div style={{ fontSize: '10px', color: 'var(--color-text-tertiary)' }}>{(infraMetrics.queueT2 ?? 0).toLocaleString()} queued</div>
                    </div>
                    <span className={`badge ${isExtreme ? 'badge-warning badge-pulse-amber' : isHigh ? 'badge-indigo badge-pulse-indigo' : 'badge-success badge-pulse-green'}`}>
                      {isExtreme ? 'DEFER' : isHigh ? 'MICRO-BATCH' : 'STREAM'}
                    </span>
                  </div>
                </div>

                {/* Best Effort Lane */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 14px',
                  background: 'var(--color-gray-50)',
                  border: '1px solid var(--color-border-subtle)',
                  borderRadius: 'var(--radius-sm)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                    <span className="dot dot-tier3" />
                    <div>
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                        Tier 3: Best Effort
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)', fontWeight: 500 }}>
                        Clicks &amp; Diagnostics • Surge Buffer
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: isExtreme ? 'var(--color-error)' : isHigh ? 'var(--color-warning)' : 'var(--color-text-primary)' }}>
                        {isExtreme ? 'W3 Shedding' : isHigh ? 'W3 50% Sample' : 'W3 Nominal'}
                      </div>
                      <div style={{ fontSize: '10px', color: 'var(--color-text-tertiary)' }}>{(infraMetrics.queueT3 ?? 0).toLocaleString()} queued</div>
                    </div>
                    <span className={`badge ${isExtreme ? 'badge-error badge-pulse-red' : isHigh ? 'badge-warning badge-pulse-amber' : 'badge-success badge-pulse-green'}`}>
                      {isExtreme ? 'SHED' : isHigh ? 'SAMPLE' : 'STREAM'}
                    </span>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </section>

        {/* ── 3. REAL-TIME QUEUE DEPTH WAVEFORM ─────────── */}
        <section>
          <SectionHeading>3. Real-Time Queue Depth Waveform</SectionHeading>
          <div className="card waveform-chart-wrapper" style={{ padding: 'var(--space-5)', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>

            {/* ── Top Bar: Title, Live Status & Advanced Controls ── */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 'var(--text-base)', fontWeight: 800, color: 'var(--color-text-primary)', letterSpacing: '-0.01em' }}>
                  Queue Backlog &amp; Flow Dynamics
                </span>
                <span className={`status-pill ${isWaveformPaused ? 'status-pill-warning' : 'status-pill-online'}`} style={{ fontSize: '11px', padding: '3px 9px' }}>
                  <span className={`status-dot status-dot-sm ${isWaveformPaused ? 'status-dot-warning' : 'status-dot-live-green'}`} />
                  {isWaveformPaused ? 'STREAM PAUSED' : 'LIVE OSCILLOSCOPE'}
                </span>
                {peakBacklog > 0 && (
                  <span className="badge badge-indigo" style={{ fontSize: '11px', padding: '3px 9px', fontWeight: 700 }}>
                    Peak: {peakBacklog.toLocaleString()} items
                  </span>
                )}
              </div>

              {/* Segmented Controls: Freeze Stream, View Mode & Window Resolution */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                {/* Pause / Live Scrub Action Button */}
                <button
                  type="button"
                  className={`waveform-pause-btn ${isWaveformPaused ? 'paused' : ''}`}
                  onClick={toggleWaveformPause}
                  title={isWaveformPaused ? 'Resume live streaming telemetry' : 'Freeze waveform for timeline inspection and scrubbing'}
                >
                  {isWaveformPaused ? <Play size={12} fill="currentColor" /> : <Pause size={12} fill="currentColor" />}
                  <span>{isWaveformPaused ? 'RESUME LIVE' : 'FREEZE / SCRUB'}</span>
                </button>

                {/* View Modes */}
                <div className="waveform-view-tabs">
                  <button
                    type="button"
                    className={`waveform-tab-btn ${waveformView === 'TIERS' ? 'active' : ''}`}
                    onClick={() => setWaveformView('TIERS')}
                    title="Stacked Partition view by Critical, Normal, and Best-Effort lanes"
                  >
                    Stacked Tiers
                  </button>
                  <button
                    type="button"
                    className={`waveform-tab-btn ${waveformView === 'FLOW' ? 'active' : ''}`}
                    onClick={() => setWaveformView('FLOW')}
                    title="Ingress arrival velocity vs worker drain rate"
                  >
                    Ingress vs Drain
                  </button>
                  <button
                    type="button"
                    className={`waveform-tab-btn ${waveformView === 'TOTAL' ? 'active' : ''}`}
                    onClick={() => setWaveformView('TOTAL')}
                    title="Single high-energy aggregate queue depth waveform"
                  >
                    Oscilloscope
                  </button>
                </div>

                {/* Window Resolutions */}
                <div className="waveform-view-tabs">
                  {[30, 60, 120].map(sec => (
                    <button
                      key={sec}
                      type="button"
                      className={`waveform-tab-btn ${waveformWindow === sec ? 'active' : ''}`}
                      onClick={() => setWaveformWindow(sec)}
                      title={`Display last ${sec} seconds of live telemetry`}
                    >
                      {sec}s
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* ── HUD Micro-Metrics Banner (5-Column) ───────────── */}
            <div className="grid grid-cols-5" style={{ gap: 'var(--space-3)' }}>
              <div className="waveform-hud-chip">
                <div className="hud-label">TOTAL QUEUE BACKLOG</div>
                <div className="hud-value font-mono" style={{ color: metrics.queueSize > 0 ? 'var(--color-indigo-600)' : 'var(--color-text-primary)' }}>
                  {metrics.queueSize.toLocaleString()} <span className="hud-unit">items</span>
                  {peakBacklog > 0 && <span className="hud-subtext">Peak: {peakBacklog.toLocaleString()}</span>}
                </div>
              </div>

              <div className="waveform-hud-chip">
                <div className="hud-label">TIER 1 (CRITICAL) QUEUE</div>
                <div className="hud-value font-mono" style={{ color: 'var(--color-success-text)' }}>
                  {(infraMetrics.queueT1 ?? 0).toLocaleString()} <span className="hud-unit">queued</span>
                  <span className="hud-badge-success">0 Lost Guarantee</span>
                </div>
              </div>

              <div className="waveform-hud-chip">
                <div className="hud-label">NET DRAIN VELOCITY</div>
                <div className="hud-value font-mono" style={{ color: netVelocity > 5 ? 'var(--color-warning)' : netVelocity < -5 ? 'var(--color-success-text)' : 'var(--color-text-secondary)' }}>
                  {netVelocity > 0 ? `+${netVelocity}` : netVelocity} <span className="hud-unit">ev/s</span>
                  <span className="hud-subtext" style={{ color: netVelocity > 5 ? 'var(--color-warning)' : netVelocity < -5 ? 'var(--color-success-text)' : 'inherit' }}>
                    {netVelocity > 5 ? 'Accumulating' : netVelocity < -5 ? 'Draining' : 'Balanced'}
                  </span>
                </div>
              </div>

              <div className="waveform-hud-chip">
                <div className="hud-label">ESTIMATED CLEAR TIME</div>
                <div className="hud-value font-mono" style={{ color: metrics.queueSize > 0 ? 'var(--color-warning)' : 'var(--color-text-primary)' }}>
                  {drainEta}
                  <span className="hud-subtext" style={{ color: metrics.queueSize === 0 ? 'var(--color-success-text)' : 'var(--color-warning)' }}>
                    {metrics.queueSize === 0 ? 'Synchronous' : 'Drain Active'}
                  </span>
                </div>
              </div>

              <div className="waveform-hud-chip">
                <div className="hud-label">AVERAGE LATENCY</div>
                <div className="hud-value font-mono">
                  {(metrics.latency ?? 0).toFixed(1)} <span className="hud-unit">ms</span>
                  <span className="hud-subtext" style={{ color: metrics.latency < 20 ? 'var(--color-success-text)' : 'var(--color-warning)' }}>
                    Target &lt; 20ms
                  </span>
                </div>
              </div>
            </div>

            {/* ── Dedicated Oscilloscope Canvas Viewport ─────────── */}
            <div className="waveform-canvas-container">
              {/* Precision Sub-pixel Grid */}
              <div className="waveform-canvas-grid" />

              {/* Bounded Laser Sweep Scanline */}
              <div className="waveform-scanline" />

              {/* Paused Mode Notice Banner */}
              {isWaveformPaused && (
                <div className="waveform-paused-banner">
                  <Pause size={12} fill="currentColor" />
                  <span>STREAM PAUSED FOR INSPECTION • Click RESUME to follow live head</span>
                </div>
              )}

              {/* Live Head Readout Chip */}
              {latestPoint && !isWaveformPaused && (
                <div className="waveform-live-tracer">
                  <span className="status-dot status-dot-sm status-dot-live-green" />
                  <span style={{ fontFamily: 'var(--font-mono)' }}>
                    HEAD: {latestPoint.total.toLocaleString()} items
                  </span>
                </div>
              )}

              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={visibleWaveform.length > 0 ? visibleWaveform : [{ time: '--', total: 0, tier1: 0, tier2: 0, tier3: 0, ingress: 0, throughput: 0 }]}
                  margin={{ top: 22, right: 18, left: -10, bottom: 4 }}
                >
                  <defs>
                    {/* SVG Laser Glow Filter */}
                    <filter id="neonBeamGlow" x="-20%" y="-20%" width="140%" height="140%">
                      <feGaussianBlur stdDeviation="2.5" result="blur" />
                      <feMerge>
                        <feMergeNode in="blur" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>

                    <linearGradient id="colorTier1" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#635BFF" stopOpacity={0.65} />
                      <stop offset="60%" stopColor="#818cf8" stopOpacity={0.20} />
                      <stop offset="100%" stopColor="#635BFF" stopOpacity={0.01} />
                    </linearGradient>

                    <linearGradient id="colorTier2" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#0284c7" stopOpacity={0.50} />
                      <stop offset="60%" stopColor="#38bdf8" stopOpacity={0.15} />
                      <stop offset="100%" stopColor="#0284c7" stopOpacity={0.01} />
                    </linearGradient>

                    <linearGradient id="colorTier3" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#64748b" stopOpacity={0.35} />
                      <stop offset="70%" stopColor="#94a3b8" stopOpacity={0.08} />
                      <stop offset="100%" stopColor="#64748b" stopOpacity={0.00} />
                    </linearGradient>

                    <linearGradient id="colorIngress" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10B981" stopOpacity={0.50} />
                      <stop offset="60%" stopColor="#34d399" stopOpacity={0.15} />
                      <stop offset="100%" stopColor="#10B981" stopOpacity={0.01} />
                    </linearGradient>

                    <linearGradient id="colorTotalGlow" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#635BFF" stopOpacity={0.60} />
                      <stop offset="40%" stopColor="#8B5CF6" stopOpacity={0.25} />
                      <stop offset="100%" stopColor="#635BFF" stopOpacity={0.01} />
                    </linearGradient>
                  </defs>

                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(226, 232, 240, 0.7)" />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} axisLine={false} tickLine={false} />

                  {peakBacklog > 20 && (
                    <ReferenceLine
                      y={Math.round(peakBacklog * 0.85)}
                      stroke="rgba(247, 144, 9, 0.5)"
                      strokeDasharray="4 4"
                      label={{ value: 'Capacity Threshold (85%)', fill: 'var(--color-warning)', fontSize: 10, position: 'insideTopRight' }}
                    />
                  )}

                  <Tooltip content={<WaveformTooltip />} />

                  {/* Mode 1: Stacked Partitioned Tiers View */}
                  {waveformView === 'TIERS' && (
                    <>
                      {tierVisibility.tier3 && (
                        <Area
                          type="monotone"
                          dataKey="tier3"
                          name="Tier 3 (Best Effort)"
                          stackId="tiers"
                          stroke="#64748b"
                          strokeWidth={1.5}
                          fill="url(#colorTier3)"
                          fillOpacity={1}
                        />
                      )}
                      {tierVisibility.tier2 && (
                        <Area
                          type="monotone"
                          dataKey="tier2"
                          name="Tier 2 (Normal)"
                          stackId="tiers"
                          stroke="#0284c7"
                          strokeWidth={2}
                          fill="url(#colorTier2)"
                          fillOpacity={1}
                        />
                      )}
                      {tierVisibility.tier1 && (
                        <Area
                          type="monotone"
                          dataKey="tier1"
                          name="Tier 1 (Critical)"
                          stackId="tiers"
                          stroke="#635BFF"
                          strokeWidth={2.5}
                          fill="url(#colorTier1)"
                          fillOpacity={1}
                          activeDot={{ r: 6, fill: '#635BFF', stroke: '#ffffff', strokeWidth: 2 }}
                        />
                      )}
                    </>
                  )}

                  {/* Mode 2: Ingress vs Drain Flow Dynamics */}
                  {waveformView === 'FLOW' && (
                    <>
                      <Area
                        type="monotone"
                        dataKey="total"
                        name="Total Backlog Silhouette"
                        stroke="#94a3b8"
                        strokeWidth={1}
                        strokeDasharray="2 2"
                        fill="rgba(148, 163, 184, 0.08)"
                        fillOpacity={1}
                      />
                      <Area
                        type="monotone"
                        dataKey="ingress"
                        name="Ingress Rate (ev/s)"
                        stroke="#10B981"
                        strokeWidth={2.5}
                        fill="url(#colorIngress)"
                        fillOpacity={1}
                        activeDot={{ r: 5, fill: '#10B981', stroke: '#ffffff', strokeWidth: 2 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="throughput"
                        name="Drain Throughput (ev/s)"
                        stroke="#8B5CF6"
                        strokeWidth={2.5}
                        strokeDasharray="4 4"
                        dot={false}
                        activeDot={{ r: 5, fill: '#8B5CF6', stroke: '#ffffff', strokeWidth: 2 }}
                      />
                    </>
                  )}

                  {/* Mode 3: High-Energy Oscilloscope Laser Waveform */}
                  {waveformView === 'TOTAL' && (
                    <Area
                      type="monotone"
                      dataKey="total"
                      name="Queue Backlog"
                      stroke="#635BFF"
                      strokeWidth={3}
                      filter="url(#neonBeamGlow)"
                      fill="url(#colorTotalGlow)"
                      fillOpacity={1}
                      activeDot={{ r: 7, fill: '#635BFF', stroke: '#ffffff', strokeWidth: 2.5 }}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* ── Interactive Legend & Toggles Bar with Live Counts ── */}
            <div className="waveform-legend-bar">
              {waveformView === 'TIERS' && (
                <>
                  <div
                    className={`waveform-legend-pill ${!tierVisibility.tier1 ? 'muted' : 'active-pill'}`}
                    onClick={() => setTierVisibility(v => ({ ...v, tier1: !v.tier1 }))}
                    title="Click to toggle Tier 1 Critical queue visibility"
                  >
                    <span className="dot dot-tier1" />
                    <span>Tier 1: Critical (Order, Payment)</span>
                    <span className="pill-count-chip">{(infraMetrics.queueT1 ?? 0).toLocaleString()} queued</span>
                    <span className="pill-guarantee">0 Shedding Guarantee</span>
                  </div>
                  <div
                    className={`waveform-legend-pill ${!tierVisibility.tier2 ? 'muted' : 'active-pill'}`}
                    onClick={() => setTierVisibility(v => ({ ...v, tier2: !v.tier2 }))}
                    title="Click to toggle Tier 2 Normal queue visibility"
                  >
                    <span className="dot dot-tier2" />
                    <span>Tier 2: Normal (Cart, Inventory)</span>
                    <span className="pill-count-chip">{(infraMetrics.queueT2 ?? 0).toLocaleString()} queued</span>
                  </div>
                  <div
                    className={`waveform-legend-pill ${!tierVisibility.tier3 ? 'muted' : 'active-pill'}`}
                    onClick={() => setTierVisibility(v => ({ ...v, tier3: !v.tier3 }))}
                    title="Click to toggle Tier 3 Best Effort queue visibility"
                  >
                    <span className="dot dot-tier3" />
                    <span>Tier 3: Best Effort (Click, View, Log)</span>
                    <span className="pill-count-chip">{(infraMetrics.queueT3 ?? 0).toLocaleString()} queued</span>
                  </div>
                </>
              )}

              {waveformView === 'FLOW' && (
                <>
                  <div className="waveform-legend-pill active-pill">
                    <span className="dot dot-ingress" />
                    <span>Ingress Rate:</span>
                    <span className="pill-count-chip font-mono">{Math.round(metrics.ingress ?? 0).toLocaleString()} ev/s</span>
                  </div>
                  <div className="waveform-legend-pill active-pill">
                    <span className="dot dot-throughput" />
                    <span>Drain Rate:</span>
                    <span className="pill-count-chip font-mono">{Math.round(metrics.throughput ?? 0).toLocaleString()} ev/s</span>
                  </div>
                  <div className="waveform-legend-pill">
                    <span className="dot dot-tier1" />
                    <span>Total Backlog:</span>
                    <span className="pill-count-chip font-mono">{metrics.queueSize.toLocaleString()} items</span>
                  </div>
                  <div className="waveform-legend-pill">
                    <span>Net Velocity:</span>
                    <span className="pill-count-chip font-mono" style={{ color: netVelocity > 0 ? 'var(--color-warning)' : 'var(--color-success-text)' }}>
                      {netVelocity > 0 ? `+${netVelocity}` : netVelocity} ev/s
                    </span>
                  </div>
                </>
              )}

              {waveformView === 'TOTAL' && (
                <div className="waveform-legend-pill active-pill">
                  <span className="dot dot-tier1" />
                  <span>Real-Time Total Queue Backlog:</span>
                  <span className="pill-count-chip font-mono">{metrics.queueSize.toLocaleString()} items</span>
                  <span className="hud-subtext">Precision Sweep • Sampling ~1.2s</span>
                </div>
              )}
            </div>

          </div>
        </section>

        {/* ── 4. EVENT MIX & 5. LIVE INGESTION STREAM ───── */}
        <div className="grid grid-cols-2" style={{ gap: 'var(--space-6)' }}>
          
          {/* Priority Composition with Shimmer Bars */}
          <section>
            <SectionHeading>4. Priority / Payload Partitioning</SectionHeading>
            <div className="card" style={{ height: 350, padding: 'var(--space-5)', display: 'flex', flexDirection: 'column' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-4)' }}>Event Mix Composition</div>
              {eventMix.length === 0 ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, flexDirection: 'column', gap: 'var(--space-2)' }}>
                  <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>Awaiting incoming event stream...</span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>Click "+5x Quick Surge" above to inject test traffic</span>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', overflowY: 'auto', flex: 1 }}>
                  {eventMix.map((mix) => (
                    <div key={mix.type} style={{ transition: 'transform 0.2s ease' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 'var(--text-xs)' }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <span style={{ fontWeight: mix.isCritical ? 700 : 600, color: mix.isCritical ? 'var(--color-indigo-700)' : 'var(--color-text-primary)' }}>
                            {mix.type}
                          </span>
                          <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>({mix.tier})</span>
                        </div>
                        <span style={{ fontWeight: 700, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>{mix.pct}%</span>
                      </div>
                      <div className="progress-bar-track">
                        <div className="progress-bar-fill" style={{ width: `${mix.pct}%`, background: mix.color }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {/* Live Ingestion Stream with Entry Animation */}
          <section>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
              <h2 style={{
                fontSize: 'var(--text-md)',
                fontWeight: 700,
                letterSpacing: '-0.01em',
                color: 'var(--color-text-primary)',
                textTransform: 'uppercase',
                margin: 0
              }}>
                5. Live Ingestion Stream
              </h2>

              {/* Tier Filter Buttons */}
              <div style={{ display: 'flex', gap: 4 }}>
                {['ALL', 'CRITICAL', 'NORMAL', 'BEST_EFFORT'].map(tier => (
                  <button
                    key={tier}
                    onClick={() => setSelectedTierFilter(tier)}
                    style={{
                      border: 'none',
                      background: selectedTierFilter === tier ? 'var(--color-indigo-50)' : 'transparent',
                      color: selectedTierFilter === tier ? 'var(--color-indigo-600)' : 'var(--color-text-tertiary)',
                      fontSize: 10,
                      fontWeight: 600,
                      padding: '2px 6px',
                      borderRadius: varRadius(tier),
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {tier.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </div>

            <div className="card" style={{ height: 350, display: 'flex', flexDirection: 'column' }}>
              <div className="card-header" style={{ padding: '10px 16px' }}>
                <div className="card-header-left">
                  <span className="status-dot status-dot-live-green" />
                  <div className="card-title" style={{ fontSize: 12 }}>Low-Latency Ring Buffer</div>
                </div>
                <span className="text-xs text-tertiary">{filteredStream.length} items</span>
              </div>

              <div style={{ overflowY: 'auto', flex: 1, padding: 'var(--space-1) 0' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--color-border-subtle)', color: 'var(--color-text-tertiary)' }}>
                      <th style={{ padding: '6px 14px', fontWeight: 600 }}>TIMESTAMP</th>
                      <th style={{ padding: '6px 8px', fontWeight: 600 }}>TRACK ID</th>
                      <th style={{ padding: '6px 8px', fontWeight: 600 }}>EVENT TYPE</th>
                      <th style={{ padding: '6px 8px', fontWeight: 600 }}>SLA TIER</th>
                      <th style={{ padding: '6px 14px', fontWeight: 600 }}>ROUTING STATUS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStream.map((evt) => (
                      <tr key={evt.receivedKey || evt.id} className="event-row-animated" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                        <td style={{ padding: '7px 14px', color: 'var(--color-text-secondary)', fontVariantNumeric: 'tabular-nums' }}>{evt.time}</td>
                        <td style={{ padding: '7px 8px', fontFamily: 'monospace', color: 'var(--color-text-tertiary)' }}>{evt.id.substring(0, 10)}…</td>
                        <td style={{ padding: '7px 8px', fontWeight: evt.tier === 'Critical' ? 700 : 500 }}>{evt.type}</td>
                        <td style={{ padding: '7px 8px', color: 'var(--color-text-secondary)' }}>{evt.tier}</td>
                        <td style={{ padding: '7px 14px' }}>
                          <span className={`badge ${evt.statusColor}`}>{evt.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

        </div>

        {/* ── 6. INFRASTRUCTURE OBSERVABILITY ────────────── */}
        <section>
          <SectionHeading>6. Infrastructure Health &amp; Dynamic Worker Distribution</SectionHeading>
          <div className="grid grid-cols-3" style={{ gap: 'var(--space-6)' }}>
            
            {/* Queue Health */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-5)' }}>Queue Depths &amp; Processing Lag</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-indigo-700)' }}>Tier 1 — Critical</div>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)' }}>Depth: {infraMetrics.queueT1.toLocaleString()}</div>
                  </div>
                  <div style={{ fontWeight: 700, color: 'var(--color-indigo-600)', fontVariantNumeric: 'tabular-nums' }}>{infraMetrics.latT1}ms</div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Tier 2 — Normal</div>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)' }}>Depth: {infraMetrics.queueT2.toLocaleString()}</div>
                  </div>
                  <div style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>{infraMetrics.latT2}ms</div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Tier 3 — Best Effort</div>
                    <div style={{ fontSize: '11px', color: 'var(--color-text-tertiary)' }}>Depth: {infraMetrics.queueT3.toLocaleString()}</div>
                  </div>
                  <div style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>{infraMetrics.latT3}ms</div>
                </div>
              </div>
            </div>

            {/* Dynamic Worker Allocation with Shimmer Sweeps */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 'var(--space-5)' }}>
                <div className="card-title">Dynamic Worker Allocation</div>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>{metrics.workerLoad}% total pool utilization</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                {[
                  { label: 'Critical lane (W1)',    key: 'w1', countKey: 'w1Count', cls: 'progress-bar-fill-indigo' },
                  { label: 'Normal lane (W2)',      key: 'w2', countKey: 'w2Count', cls: 'progress-bar-fill-success' },
                  { label: 'Best-effort lane (W3)', key: 'w3', countKey: 'w3Count', cls: 'progress-bar-fill-warning' },
                ].map(({ label, key, countKey, cls }) => {
                  const totalWorkers = (infraMetrics.totalWorkers && infraMetrics.totalWorkers > 0)
                    ? infraMetrics.totalWorkers
                    : 8;
                  const pct   = infraMetrics[key] ?? 0;
                  const count = infraMetrics[countKey] !== undefined
                    ? infraMetrics[countKey]
                    : Math.round((pct / 100) * totalWorkers);

                  return (
                    <div key={key}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 'var(--text-xs)' }}>
                        <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{label}</span>
                        <span style={{ fontWeight: 700, color: 'var(--color-indigo-600)', fontVariantNumeric: 'tabular-nums' }}>
                          {count} / {totalWorkers} threads
                        </span>
                      </div>
                      <div className="progress-bar-track">
                        <div className={`progress-bar-fill ${cls}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Latency by Priority */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-5)' }}>Target SLA Response Tiers</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {/* Tier 1 SLA */}
                <div style={{ padding: 'var(--space-3)', background: 'rgba(99, 91, 255, 0.05)', border: '1px solid rgba(99, 91, 255, 0.15)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-indigo-600)' }}>TIER 1 (SLA &lt; 20ms)</span>
                    <span style={{ fontWeight: 700, color: 'var(--color-indigo-600)', fontVariantNumeric: 'tabular-nums' }}>~{infraMetrics.latT1}ms</span>
                  </div>
                  <div className="progress-bar-track" style={{ height: 5 }}>
                    <div
                      className="progress-bar-fill progress-bar-fill-indigo"
                      style={{ width: `${Math.min(100, Math.max(6, ((infraMetrics.latT1 || 1.2) / 20) * 100))}%` }}
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--color-indigo-500)', fontWeight: 600 }}>
                    <span>Budget: {Math.min(100, Math.round(((infraMetrics.latT1 || 1.2) / 20) * 100))}% consumed</span>
                    <span>Zero Loss Invariant</span>
                  </div>
                </div>
                
                {/* Tier 2 SLA */}
                <div style={{ padding: 'var(--space-3)', background: 'var(--color-gray-50)', border: '1px solid var(--color-border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>TIER 2 (SLA &lt; 150ms)</span>
                    <span style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>~{infraMetrics.latT2}ms</span>
                  </div>
                  <div className="progress-bar-track" style={{ height: 5 }}>
                    <div
                      className="progress-bar-fill progress-bar-fill-success"
                      style={{ width: `${Math.min(100, Math.max(6, ((infraMetrics.latT2 || 12) / 150) * 100))}%` }}
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--color-text-secondary)', fontWeight: 600 }}>
                    <span>Budget: {Math.min(100, Math.round(((infraMetrics.latT2 || 12) / 150) * 100))}% consumed</span>
                    <span>Micro-Batch / Stream</span>
                  </div>
                </div>

                {/* Tier 3 SLA */}
                <div style={{ padding: 'var(--space-3)', background: 'var(--color-gray-50)', border: '1px solid var(--color-border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>TIER 3 (Best Effort)</span>
                    <span style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>~{infraMetrics.latT3}ms</span>
                  </div>
                  <div className="progress-bar-track" style={{ height: 5 }}>
                    <div
                      className="progress-bar-fill progress-bar-fill-warning"
                      style={{ width: `${Math.min(100, Math.max(6, ((infraMetrics.latT3 || 45) / 500) * 100))}%` }}
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--color-text-secondary)', fontWeight: 600 }}>
                    <span>Latency: ~{infraMetrics.latT3}ms</span>
                    <span>Surge Resilient</span>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </section>

        {/* ── 7. BACKPRESSURE & SHEDDING ────────────────── */}
        <section style={{ paddingBottom: 'var(--space-8)' }}>
          <SectionHeading>7. Backpressure Actions &amp; Resilience Metrics</SectionHeading>
          <div className="grid grid-cols-2" style={{ gap: 'var(--space-6)' }}>
            
            {/* Policy Summary */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-4)' }}>Adaptive State &amp; Safeguards</div>
              
              <div className="grid grid-cols-3" style={{ gap: 'var(--space-4)', marginBottom: 'var(--space-5)' }}>
                <CompactMetric
                  label="Queue Pressure"
                  value={pressureState}
                  valueColor={isExtreme ? 'var(--color-error)' : isHigh ? 'var(--color-warning)' : 'var(--color-success-text)'}
                />
                <CompactMetric label="Governor" value={pressureState !== 'NORMAL' ? 'ACTIVE' : 'STANDBY'} />
                <CompactMetric label="Shedding" value={isExtreme ? 'ACTIVE' : isHigh ? 'SAMPLING' : 'DISABLED'} />
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                {/* Tier 1 Visual Invariant */}
                <div style={{ padding: '10px 12px', background: 'rgba(99, 91, 255, 0.04)', border: '1px solid rgba(99, 91, 255, 0.16)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-indigo-700)', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span className="dot dot-tier1" />
                      TIER 1: ZERO-LOSS GUARANTEE
                    </span>
                    <span className="badge badge-success badge-pulse-green" style={{ fontSize: 10, padding: '1px 6px' }}>
                      100% PROTECTED
                    </span>
                  </div>
                  <div className="progress-bar-track" style={{ height: 5 }}>
                    <div className="progress-bar-fill progress-bar-fill-indigo" style={{ width: '100%' }} />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--color-indigo-600)', fontWeight: 600 }}>
                    <span>0 Critical Loss Invariant</span>
                    <span>Dedicated Worker Lane</span>
                  </div>
                </div>

                {/* Tier 2 Visual Deferral Meter */}
                <div style={{ padding: '10px 12px', background: 'var(--color-gray-50)', border: '1px solid var(--color-border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span className="dot dot-tier2" />
                      TIER 2: ADAPTIVE DEFERRAL
                    </span>
                    <span className={`badge ${isExtreme ? 'badge-warning badge-pulse-amber' : isHigh ? 'badge-indigo badge-pulse-indigo' : 'badge-success'}`} style={{ fontSize: 10, padding: '1px 6px' }}>
                      {isExtreme ? 'DEFERRED (SURGE)' : isHigh ? 'MICRO-BATCH' : 'CONTINUOUS STREAM'}
                    </span>
                  </div>
                  <div className="progress-bar-track" style={{ height: 5 }}>
                    <div
                      className="progress-bar-fill"
                      style={{
                        width: isExtreme ? '35%' : isHigh ? '75%' : '100%',
                        background: isExtreme ? 'var(--color-warning)' : 'var(--color-indigo-500)'
                      }}
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--color-text-secondary)', fontWeight: 600 }}>
                    <span>Capacity: {isExtreme ? 'Throttled for T1' : isHigh ? 'Micro-Batching' : 'Nominal Stream'}</span>
                    <span>SLA Target &lt; 150ms</span>
                  </div>
                </div>

                {/* Tier 3 Visual Retention Meter */}
                <div style={{ padding: '10px 12px', background: 'var(--color-gray-50)', border: '1px solid var(--color-border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span className="dot dot-tier3" />
                      TIER 3: LOAD SHEDDING
                    </span>
                    <span className={`badge ${isExtreme ? 'badge-error badge-pulse-red' : isHigh ? 'badge-warning' : 'badge-success'}`} style={{ fontSize: 10, padding: '1px 6px' }}>
                      {isExtreme ? 'SHEDDING ACTIVE' : isHigh ? '50% SAMPLE' : 'PASS-THROUGH'}
                    </span>
                  </div>
                  <div className="progress-bar-track" style={{ height: 5 }}>
                    <div
                      className="progress-bar-fill"
                      style={{
                        width: isExtreme ? '15%' : isHigh ? '50%' : '100%',
                        background: isExtreme ? 'var(--color-error)' : isHigh ? 'var(--color-warning)' : 'var(--color-gray-400)'
                      }}
                    />
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, fontSize: 10, color: 'var(--color-text-secondary)', fontWeight: 600 }}>
                    <span>Pass-Through: {isExtreme ? '15%' : isHigh ? '50%' : '100%'}</span>
                    <span>Surge Resilient</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Taken Grid */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-4)' }}>Degradation &amp; Protection Counters</div>
              <div className="grid grid-cols-2" style={{ gap: 'var(--space-3)' }}>
                
                {/* 1. SHED EVENTS */}
                <div
                  id="counter-shed-events"
                  className="card-interactive"
                  style={{
                    padding: 'var(--space-4)',
                    background: 'rgba(217, 45, 32, 0.05)',
                    border: '1px solid rgba(217, 45, 32, 0.18)',
                    borderRadius: 'var(--radius-sm)',
                    transition: 'all var(--transition-normal)'
                  }}
                >
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-error)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span>SHED EVENTS</span>
                    <span style={{ fontSize: '10px', background: 'rgba(217, 45, 32, 0.12)', padding: '1px 6px', borderRadius: 'var(--radius-full)' }}>
                      Tier 3
                    </span>
                  </div>
                  <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, color: 'var(--color-error)', fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>
                    {totalShedEvents.toLocaleString()}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--color-error)', opacity: 0.9, marginTop: 2 }}>
                    {shedSubtitle}
                  </div>
                </div>

                {/* 2. DEFERRED */}
                <div
                  id="counter-deferred-events"
                  className="card-interactive"
                  style={{
                    padding: 'var(--space-4)',
                    background: 'rgba(247, 144, 9, 0.05)',
                    border: '1px solid rgba(247, 144, 9, 0.18)',
                    borderRadius: 'var(--radius-sm)',
                    transition: 'all var(--transition-normal)'
                  }}
                >
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-warning)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span>DEFERRED</span>
                    <span style={{ fontSize: '10px', background: 'rgba(247, 144, 9, 0.12)', padding: '1px 6px', borderRadius: 'var(--radius-full)' }}>
                      Tier 2
                    </span>
                  </div>
                  <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, color: 'var(--color-warning)', fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>
                    {totalDeferredEvents.toLocaleString()}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--color-warning)', opacity: 0.9, marginTop: 2 }}>
                    {deferredSubtitle}
                  </div>
                </div>

                {/* 3. SAMPLED */}
                <div
                  id="counter-sampled-events"
                  className="card-interactive"
                  style={{
                    padding: 'var(--space-4)',
                    background: 'rgba(113, 113, 122, 0.05)',
                    border: '1px solid rgba(113, 113, 122, 0.22)',
                    borderRadius: 'var(--radius-sm)',
                    transition: 'all var(--transition-normal)'
                  }}
                >
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span>SAMPLED</span>
                    <span style={{ fontSize: '10px', background: 'rgba(113, 113, 122, 0.12)', padding: '1px 6px', borderRadius: 'var(--radius-full)' }}>
                      50% Downsample
                    </span>
                  </div>
                  <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>
                    {(shedStats.sampled ?? 0).toLocaleString()}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--color-text-tertiary)', marginTop: 2 }}>
                    {sampledSubtitle}
                  </div>
                </div>

                {/* 4. PROTECTED CRITICAL */}
                <div
                  id="counter-protected-events"
                  className="card-interactive"
                  style={{
                    padding: 'var(--space-4)',
                    background: 'rgba(99, 91, 255, 0.08)',
                    border: '1px solid rgba(99, 91, 255, 0.25)',
                    borderRadius: 'var(--radius-sm)',
                    transition: 'all var(--transition-normal)'
                  }}
                >
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-indigo-600)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Shield size={12} /> PROTECTED
                    </span>
                    <span style={{ fontSize: '10px', background: 'rgba(99, 91, 255, 0.15)', color: 'var(--color-indigo-700)', padding: '1px 6px', borderRadius: 'var(--radius-full)', fontWeight: 700 }}>
                      Tier 1
                    </span>
                  </div>
                  <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color: 'var(--color-indigo-700)', fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>
                    {protectedCount > 0 ? `${protectedCount.toLocaleString()} DELIVERED` : '100% PROTECTED'}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--color-indigo-600)', fontWeight: 600, marginTop: 2 }}>
                    0 Lost • Payments &amp; Orders Guaranteed
                  </div>
                </div>

              </div>
            </div>

          </div>
        </section>

      </div>
    </>
  )
}

function varRadius(tier) {
  return 'var(--radius-sm)';
}
