import React, { useState, useEffect } from 'react'
import {
  Activity, Layers, Users, GitBranch, Clock,
  TrendingUp, AlertTriangle, CheckCircle, Zap, Shield, Target
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

/* ─── Data ────────────────────────────────────────────────── */
// waveformData accumulates live queue depth snapshots from backend telemetry

// Event-type tier and colour metadata (determines display style; percentages come from live data)
const EVENT_TIER_META = {
  ORDER:             { tier: 'Critical',    color: 'var(--color-indigo-500)', isCritical: true  },
  PAYMENT:           { tier: 'Critical',    color: 'var(--color-indigo-600)', isCritical: true  },
  CART_ADD:          { tier: 'Normal',      color: 'var(--color-gray-500)',   isCritical: false },
  INVENTORY_UPDATE:  { tier: 'Normal',      color: 'var(--color-gray-500)',   isCritical: false },
  CLICK:             { tier: 'Best Effort', color: 'var(--color-gray-400)',   isCritical: false },
  PAGE_VIEW:         { tier: 'Best Effort', color: 'var(--color-gray-400)',   isCritical: false },
  LOG:               { tier: 'Best Effort', color: 'var(--color-gray-300)',   isCritical: false },
};

const TIER_FALLBACK = {
  CRITICAL:    { tier: 'Critical',    color: 'var(--color-indigo-500)', isCritical: true  },
  NORMAL:      { tier: 'Normal',      color: 'var(--color-gray-500)',   isCritical: false },
  BEST_EFFORT: { tier: 'Best Effort', color: 'var(--color-gray-400)',   isCritical: false },
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

import { telemetryService } from '../api/telemetry';

/* ─── Components ──────────────────────────────────────────── */

function CompactMetric({ label, value, subValue, highlight = false, valueColor }) {
  return (
    <div className="metric-card" style={{ padding: 'var(--space-3) var(--space-4)' }}>
      <div className="metric-label" style={{ marginBottom: 4 }}>{label}</div>
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
  if (status === 'STREAM') return 'badge-success';
  if (status === 'MICRO-BATCH') return 'badge-indigo';
  if (status === 'DEFER') return 'badge-warning';
  if (status === 'SAMPLE') return 'badge-gray';
  return 'badge-gray';
}

/* ═══════════════════════════════════════════════════════════
   ObservabilityPage — Machine 2 main content
═══════════════════════════════════════════════════════════ */
export default function ObservabilityPage() {
  const [streamData, setStreamData] = useState([])
  const [waveformData, setWaveformData] = useState([])
  const [connected, setConnected] = useState(false)
  const [eventMix, setEventMix] = useState([])

  const [metrics, setMetrics] = useState({ queueSize: 0, latency: 0, workerLoad: 0, processingCost: 'LOW', isSpikeMode: false, ingress: 0, throughput: 0, pressureState: 'NORMAL', pressureScore: 0 })
  const [infraMetrics, setInfraMetrics] = useState({ queueT1: 0, latT1: 0, queueT2: 0, latT2: 0, queueT3: 0, latT3: 0, w1: 0, w2: 0, w3: 0, w4: 0, totalWorkers: 8 })
  const [shedStats, setShedStats] = useState({ shed: 0, deferred: 0, sampled: 0 })

  useEffect(() => {
    const unsubTelemetry = telemetryService.onTelemetryUpdate((data) => {
      setMetrics(data.metrics);
      setInfraMetrics(data.infraMetrics);
      setShedStats({ ...data.shedStats });

      // Compute live event-type distribution from the backend's recent-events window
      setEventMix(computeEventMix(data.recentEventTypes ?? []));

      // Accumulate waveform data (capped at 60 points = 72 seconds of history)
      setWaveformData(prev => {
        const point = {
          time: new Date().toISOString().substring(11, 19),
          events: data.metrics.queueSize ?? 0,
        };
        return [...prev, point].slice(-60);
      });
    });

    const unsubEvents = telemetryService.onNewEvent((evt) => {
      setStreamData(prev => [{...evt, statusColor: getStatusColor(evt.status)}, ...prev].slice(0, 10));
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

  const isSpikeMode = metrics.isSpikeMode;
  const pressureState = metrics.pressureState ?? 'NORMAL';
  // Derived helpers for 3-state adaptive governor
  const isHigh = pressureState === 'HIGH';
  const isExtreme = pressureState === 'EXTREME';
  
  return (
    <>
      <div className="page-header">
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
        </div>
        <p className="page-header-subtitle">
          Monitor adaptive processing, queue pressure, routing decisions and critical-event latency in real time.
        </p>
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
            <CompactMetric label="Queue Depth" value={metrics.queueSize.toLocaleString()} />
            <CompactMetric label="Ingress Rate" value={(metrics.ingress ?? 0).toFixed(1)} subValue=" ev/s" />
            <CompactMetric label="System Load" value={`${metrics.workerLoad}%`} />
            <CompactMetric
              label="Pressure"
              value={pressureState}
              valueColor={isExtreme ? 'var(--color-error)' : isHigh ? 'var(--color-warning)' : 'var(--color-success-text)'}
            />
            <CompactMetric
              label="Governor"
              value={pressureState === 'NORMAL' ? 'STANDBY' : 'ADAPTIVE'}
              valueColor={pressureState !== 'NORMAL' ? 'var(--color-indigo-600)' : 'var(--color-text-secondary)'}
            />
            <CompactMetric label="Pressure Score" value={(metrics.pressureScore ?? 0).toFixed(3)} />
          </div>
        </section>
        
        {/* ── 2. ADAPTIVE GOVERNOR ──────────────────────── */}
        <section>
          <SectionHeading>2. Adaptive Governor</SectionHeading>
          <div className="grid grid-cols-3" style={{ gap: 'var(--space-4)' }}>
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-4)' }}>
                {pressureState} LOAD
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>QUEUE PRESSURE</span>
                  <span style={{ fontWeight: 600, color: isExtreme ? 'var(--color-error)' : isHigh ? 'var(--color-warning)' : 'var(--color-success-text)' }}>
                    {pressureState}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>QUEUE DEPTH</span>
                  <span style={{ fontWeight: 600 }}>{metrics.queueSize.toLocaleString()}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>WORKER LOAD</span>
                  <span style={{ fontWeight: 600 }}>{metrics.workerLoad}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>PROCESSING COST</span>
                  <span style={{ fontWeight: 600 }}>{metrics.processingCost}</span>
                </div>
                <div className="divider" style={{ margin: '4px 0' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>GOVERNOR</span>
                  <span style={{ fontWeight: 700, color: pressureState !== 'NORMAL' ? 'var(--color-indigo-600)' : 'var(--color-success-text)' }}>
                    {pressureState === 'NORMAL' ? 'STANDBY' : 'ADAPTIVE'}
                  </span>
                </div>
              </div>
            </div>

            <div className="card col-span-2" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-4)' }}>Current Processing Decisions</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--color-gray-50)', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Critical (Payment, Order)</span>
                  <span className="badge badge-success">STREAM</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--color-gray-50)', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Normal (Inventory)</span>
                  <span className={`badge ${isExtreme ? 'badge-warning' : isHigh ? 'badge-indigo' : 'badge-success'}`}>
                    {isExtreme ? 'DEFER' : isHigh ? 'MICRO-BATCH' : 'STREAM'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--color-gray-50)', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Best Effort (Views, Logs)</span>
                  <span className={`badge ${isExtreme ? 'badge-gray' : isHigh ? 'badge-warning' : 'badge-success'}`}>
                    {isExtreme ? 'SAMPLE / SHED' : isHigh ? 'SAMPLE' : 'STREAM'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── 3. REAL-TIME QUEUE DEPTH ─────────────────── */}
        <section>
          <SectionHeading>3. Real-Time Queue Depth</SectionHeading>
          <div className="card" style={{ padding: 'var(--space-5)', height: 350 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
              <div style={{ display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--text-xs)', fontWeight: 500 }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>Total queue depth across all priority lanes — sampled every ~1.2 s</span>
              </div>
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={waveformData.length > 0 ? waveformData : [{ time: '--', events: 0 }]}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="colorEvents" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-indigo-500)" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="var(--color-indigo-500)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-subtle)" />
                <XAxis dataKey="time" tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} axisLine={false} tickLine={false} />
                <Tooltip 
                  contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-xs)' }}
                  itemStyle={{ color: 'var(--color-indigo-600)', fontWeight: 600 }}
                />
                <Area type="monotone" dataKey="events" name="Queue Depth" stroke="var(--color-indigo-500)" strokeWidth={2} fillOpacity={1} fill="url(#colorEvents)" activeDot={{ r: 4, fill: 'var(--color-indigo-600)' }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>

        {/* ── 4. PRIORITY / PAYLOAD PARTITIONING & 5. LIVE INGESTION STREAM */}
        <div className="grid grid-cols-2" style={{ gap: 'var(--space-6)' }}>
          
          <section>
            <SectionHeading>4. Priority / Payload Partitioning</SectionHeading>
            <div className="card" style={{ height: 320, padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-5)' }}>Event Mix Composition</div>
              {eventMix.length === 0 ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, flexDirection: 'column', gap: 'var(--space-3)' }}>
                  <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-tertiary)', fontWeight: 500 }}>No events received yet</span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>Distribution will appear once events flow through the pipeline</span>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                  {eventMix.map((mix) => (
                    <div key={mix.type}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 'var(--text-xs)' }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <span style={{ fontWeight: mix.isCritical ? 700 : 500, color: mix.isCritical ? 'var(--color-text-primary)' : 'var(--color-text-secondary)' }}>
                            {mix.type}
                          </span>
                          <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>{mix.tier}</span>
                        </div>
                        <span style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>{mix.pct}%</span>
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

          <section>
            <SectionHeading>5. Live Ingestion Stream</SectionHeading>
            <div className="card" style={{ height: 320, display: 'flex', flexDirection: 'column' }}>
              <div className="card-header">
                <div className="card-header-left">
                  <div className="card-title">Low-Latency Sink</div>
                  <div className="card-subtitle">Live Ingestion Stream Ring Buffer</div>
                </div>
              </div>
              <div style={{ overflow: 'hidden', flex: 1, padding: 'var(--space-2) 0' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', textAlign: 'left' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--color-border-subtle)', color: 'var(--color-text-tertiary)' }}>
                      <th style={{ padding: '6px var(--space-4)', fontWeight: 600 }}>TIMESTAMP</th>
                      <th style={{ padding: '6px var(--space-2)', fontWeight: 600 }}>TRACK ID</th>
                      <th style={{ padding: '6px var(--space-2)', fontWeight: 600 }}>EVENT TYPE</th>
                      <th style={{ padding: '6px var(--space-2)', fontWeight: 600 }}>SLA TIER</th>
                      <th style={{ padding: '6px var(--space-4)', fontWeight: 600 }}>ROUTING STATUS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {streamData.map((evt, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                        <td style={{ padding: '8px var(--space-4)', color: 'var(--color-text-secondary)', fontVariantNumeric: 'tabular-nums' }}>{evt.time}</td>
                        <td style={{ padding: '8px var(--space-2)', fontFamily: 'monospace', color: 'var(--color-text-tertiary)' }}>{evt.id}</td>
                        <td style={{ padding: '8px var(--space-2)', fontWeight: evt.tier === 'Critical' ? 600 : 400 }}>{evt.type}</td>
                        <td style={{ padding: '8px var(--space-2)', color: 'var(--color-text-secondary)' }}>{evt.tier}</td>
                        <td style={{ padding: '8px var(--space-4)' }}>
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
          <SectionHeading>6. Infrastructure Health</SectionHeading>
          <div className="grid grid-cols-3" style={{ gap: 'var(--space-6)' }}>
            
            {/* Queue Health */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-5)' }}>Queue Depth &amp; Health</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Tier 1 — Critical</div>
                    <div style={{ fontSize: '10px', color: 'var(--color-text-tertiary)' }}>Depth: {infraMetrics.queueT1.toLocaleString()}</div>
                  </div>
                  <div style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>{infraMetrics.latT1}ms</div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Tier 2 — Normal</div>
                    <div style={{ fontSize: '10px', color: 'var(--color-text-tertiary)' }}>Depth: {infraMetrics.queueT2.toLocaleString()}</div>
                  </div>
                  <div style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>{infraMetrics.latT2}ms</div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Tier 3 — Best Effort</div>
                    <div style={{ fontSize: '10px', color: 'var(--color-text-tertiary)' }}>Depth: {infraMetrics.queueT3.toLocaleString()}</div>
                  </div>
                  <div style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>{infraMetrics.latT3}ms</div>
                </div>
              </div>
            </div>

            {/* Worker Allocation */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 'var(--space-5)' }}>
                <div className="card-title">Worker Allocation</div>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>overall {metrics.workerLoad}% utilization</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                {[
                  { label: 'Critical lane',    key: 'w1', countKey: 'w1Count' },
                  { label: 'Normal lane',      key: 'w2', countKey: 'w2Count' },
                  { label: 'Best-effort lane', key: 'w3', countKey: 'w3Count' },
                  { label: 'Spare',            key: 'w4', countKey: 'w4Count' },
                ].map(({ label, key, countKey }) => {
                  const totalWorkers = (infraMetrics.totalWorkers && infraMetrics.totalWorkers > 0)
                    ? infraMetrics.totalWorkers
                    : 8;
                  const pct   = infraMetrics[key] ?? 0;
                  const count = infraMetrics[countKey] !== undefined
                    ? infraMetrics[countKey]
                    : Math.round((pct / 100) * totalWorkers);
                  const color = pct > 80 ? 'var(--color-error)' : pct > 70 ? 'var(--color-warning)' : 'var(--color-indigo-500)';
                  return (
                    <div key={key}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 'var(--text-xs)' }}>
                        <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{label}</span>
                        <span style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>{count}/{totalWorkers}</span>
                      </div>
                      <div className="progress-bar-track">
                        <div className="progress-bar-fill" style={{ width: `${pct}%`, background: color }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Latency by Priority */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-5)' }}>Latency By Priority</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                <div style={{ padding: 'var(--space-3)', background: 'rgba(99, 91, 255, 0.05)', border: '1px solid rgba(99, 91, 255, 0.15)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--color-indigo-600)' }}>TIER 1</span>
                    <span style={{ fontWeight: 700, color: 'var(--color-indigo-600)' }}>~{infraMetrics.latT1}ms</span>
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-indigo-500)' }}>Payment / Order</div>
                </div>
                
                <div style={{ padding: 'var(--space-3)', background: 'var(--color-gray-50)', border: '1px solid var(--color-border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>TIER 2</span>
                    <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>~{infraMetrics.latT2}ms</span>
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Inventory</div>
                </div>

                <div style={{ padding: 'var(--space-3)', background: 'var(--color-gray-50)', border: '1px solid var(--color-border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>TIER 3</span>
                    <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>~{infraMetrics.latT3}ms</span>
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Logs / Activity</div>
                </div>
              </div>
            </div>

          </div>
        </section>

        {/* ── 7. BACKPRESSURE & SHEDDING ────────────────── */}
        <section style={{ paddingBottom: 'var(--space-8)' }}>
          <SectionHeading>7. Backpressure &amp; Shedding</SectionHeading>
          <div className="grid grid-cols-2" style={{ gap: 'var(--space-6)' }}>
            
            {/* Policy Summary */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-4)' }}>State &amp; Policy Summary</div>
              
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
                <div>
                  <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>TIER 1 — CRITICAL</div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Never dropped. Backpressure upstream.</div>
                </div>
                <div>
                  <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>TIER 2 — NORMAL</div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Micro-batched. Buffered when required.</div>
                </div>
                <div>
                  <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>TIER 3 — BEST EFFORT</div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>Deferred / sampled under extreme pressure.</div>
                </div>
              </div>
            </div>

            {/* Action Taken */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-4)' }}>Action Taken</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                
                <div style={{ padding: 'var(--space-4)', background: 'rgba(217, 45, 32, 0.05)', border: '1px solid rgba(217, 45, 32, 0.15)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-error)' }}>SHED EVENTS</div>
                  <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-error)', fontVariantNumeric: 'tabular-nums' }}>
                    {(shedStats.shed ?? 0).toLocaleString()}
                  </div>
                </div>

                <div style={{ padding: 'var(--space-4)', background: 'rgba(247, 144, 9, 0.05)', border: '1px solid rgba(247, 144, 9, 0.15)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-warning)' }}>DEFERRED</div>
                  <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-warning)', fontVariantNumeric: 'tabular-nums' }}>
                    {(shedStats.deferred ?? 0).toLocaleString()}
                  </div>
                </div>

                <div style={{ padding: 'var(--space-4)', background: 'rgba(113, 113, 122, 0.05)', border: '1px solid rgba(113, 113, 122, 0.2)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-secondary)' }}>SAMPLED</div>
                  <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-text-secondary)', fontVariantNumeric: 'tabular-nums' }}>
                    {(shedStats.sampled ?? 0).toLocaleString()}
                  </div>
                </div>

                <div style={{ padding: 'var(--space-4)', background: 'rgba(99, 91, 255, 0.08)', border: '1px solid rgba(99, 91, 255, 0.2)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-indigo-600)' }}>PROTECTED</div>
                  <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-indigo-600)' }}>
                    PAYMENTS + ORDERS
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
