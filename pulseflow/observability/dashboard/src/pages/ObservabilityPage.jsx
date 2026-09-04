import React, { useState, useEffect } from 'react'
import {
  Activity, Layers, Users, GitBranch, Clock,
  TrendingUp, AlertTriangle, CheckCircle, Zap, Shield, Target
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

/* ─── Data ────────────────────────────────────────────────── */
const waveformData = [
  { time: '10:00:00', events: 1000 },
  { time: '10:00:10', events: 1050 },
  { time: '10:00:20', events: 950 },
  { time: '10:00:30', events: 1100 },
  { time: '10:00:40', events: 8000 },
  { time: '10:00:50', events: 20000 },
  { time: '10:01:00', events: 19500 },
  { time: '10:01:10', events: 10500 },
  { time: '10:01:20', events: 10200 },
  { time: '10:01:30', events: 4000 },
  { time: '10:01:40', events: 1200 },
  { time: '10:01:50', events: 1000 },
]

const eventMix = [
  { type: 'PAYMENT', tier: 'Critical', pct: 15, color: 'var(--color-indigo-600)', isCritical: true },
  { type: 'ORDER', tier: 'Critical', pct: 25, color: 'var(--color-indigo-500)', isCritical: true },
  { type: 'INVENTORY', tier: 'Normal', pct: 15, color: 'var(--color-gray-500)', isCritical: false },
  { type: 'ACTIVITY / VIEWS', tier: 'Best Effort', pct: 30, color: 'var(--color-gray-400)', isCritical: false },
  { type: 'LOGS / TELEMETRY', tier: 'Best Effort', pct: 15, color: 'var(--color-gray-300)', isCritical: false },
]

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
  
  const [metrics, setMetrics] = useState({ queueSize: 0, latency: 0, workerLoad: 0, processingCost: 'LOW', isSpikeMode: false, ingress: 1000, throughput: 1000 })
  const [infraMetrics, setInfraMetrics] = useState({ queueT1: 0, latT1: 0, queueT2: 0, latT2: 0, queueT3: 0, latT3: 0, w1: 0, w2: 0, w3: 0, w4: 0 })
  const [shedStats, setShedStats] = useState({ shed: 0, deferred: 0 })

  useEffect(() => {
    const unsubTelemetry = telemetryService.onTelemetryUpdate((data) => {
      setMetrics(data.metrics);
      setInfraMetrics(data.infraMetrics);
      setShedStats({ ...data.shedStats });
    });

    const unsubEvents = telemetryService.onNewEvent((evt) => {
      setStreamData(prev => [{...evt, statusColor: getStatusColor(evt.status)}, ...prev].slice(0, 10));
    });

    return () => {
      unsubTelemetry();
      unsubEvents();
    }
  }, []);

  const isSpikeMode = metrics.isSpikeMode;
  
  return (
    <>
      <div className="page-header">
        <h1 className="page-header-title">PulseFlow Observability</h1>
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
            <CompactMetric label="Ingress" value={isSpikeMode ? "20,000" : "1,000"} subValue=" events/min" />
            <CompactMetric label="Queue Depth" value={metrics.queueSize.toLocaleString()} />
            <CompactMetric label="Throughput" value={isSpikeMode ? "~320" : "~1,000"} subValue=" events/sec" />
            <CompactMetric label="System Load" value={`${metrics.workerLoad}%`} />
            <CompactMetric label="Governor" value={isSpikeMode ? "ADAPTIVE" : "STANDBY"} valueColor={isSpikeMode ? "var(--color-indigo-600)" : "var(--color-text-secondary)"} />
            <CompactMetric label="Critical Events" value="PROTECTED" valueColor="var(--color-success-text)" />
          </div>
        </section>
        
        {/* ── 2. ADAPTIVE GOVERNOR ──────────────────────── */}
        <section>
          <SectionHeading>2. Adaptive Governor</SectionHeading>
          <div className="grid grid-cols-3" style={{ gap: 'var(--space-4)' }}>
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-4)' }}>
                {isSpikeMode ? 'SPIKE LOAD' : 'NORMAL LOAD'}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>QUEUE PRESSURE</span>
                  <span style={{ fontWeight: 600, color: isSpikeMode ? 'var(--color-error)' : 'var(--color-success-text)' }}>
                    {isSpikeMode ? 'HIGH' : 'LOW'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-sm)' }}>
                  <span style={{ color: 'var(--color-text-secondary)' }}>LATENCY</span>
                  <span style={{ fontWeight: 600 }}>{metrics.latency}ms</span>
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
                  <span style={{ color: 'var(--color-text-secondary)' }}>CURRENT STRATEGY</span>
                  <span style={{ fontWeight: 700, color: isSpikeMode ? 'var(--color-indigo-600)' : 'var(--color-success-text)' }}>
                    {isSpikeMode ? 'ADAPTIVE' : 'STREAM'}
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
                  <span className={`badge ${isSpikeMode ? 'badge-indigo' : 'badge-success'}`}>
                    {isSpikeMode ? 'MICRO-BATCH' : 'STREAM'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--color-gray-50)', borderRadius: 'var(--radius-sm)' }}>
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Best Effort (Views, Logs)</span>
                  <span className={`badge ${isSpikeMode ? 'badge-warning' : 'badge-success'}`}>
                    {isSpikeMode ? 'DEFER / SAMPLE' : 'STREAM'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── 3. REAL-TIME INGRESS WAVEFORM ─────────────── */}
        <section>
          <SectionHeading>3. Real-Time Ingress Waveform &amp; Governor Tripwire</SectionHeading>
          <div className="card" style={{ padding: 'var(--space-5)', height: 350 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
              <div style={{ display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--text-xs)', fontWeight: 500 }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>BASELINE <span style={{ color: 'var(--color-border)' }}>→</span> 20× SPIKE <span style={{ color: 'var(--color-border)' }}>→</span> GOVERNOR ACTIVATION <span style={{ color: 'var(--color-border)' }}>→</span> CONTROLLED PROCESSING <span style={{ color: 'var(--color-border)' }}>→</span> RECOVERY</span>
              </div>
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={waveformData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorEvents" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-indigo-500)" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="var(--color-indigo-500)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--color-border-subtle)" />
                <XAxis dataKey="time" tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} axisLine={false} tickLine={false} />
                <Tooltip 
                  contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-xs)' }}
                  itemStyle={{ color: 'var(--color-indigo-600)', fontWeight: 600 }}
                />
                <ReferenceLine y={10000} stroke="var(--color-error)" strokeDasharray="4 4" label={{ position: 'insideTopLeft', value: 'Governor Tripwire', fill: 'var(--color-error)', fontSize: 10, fontWeight: 600 }} />
                <Area type="monotone" dataKey="events" stroke="var(--color-indigo-500)" strokeWidth={2} fillOpacity={1} fill="url(#colorEvents)" activeDot={{ r: 4, fill: 'var(--color-indigo-600)' }} />
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
                  <div style={{ fontWeight: 600, color: 'var(--color-success-text)' }}>{infraMetrics.latT1}ms</div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Tier 2 — Normal</div>
                    <div style={{ fontSize: '10px', color: 'var(--color-text-tertiary)' }}>Depth: {infraMetrics.queueT2.toLocaleString()}</div>
                  </div>
                  <div style={{ fontWeight: 600, color: infraMetrics.latT2 > 20 ? 'var(--color-warning)' : 'var(--color-success-text)' }}>{infraMetrics.latT2}ms</div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>Tier 3 — Best Effort</div>
                    <div style={{ fontSize: '10px', color: 'var(--color-text-tertiary)' }}>Depth: {infraMetrics.queueT3.toLocaleString()}</div>
                  </div>
                  <div style={{ fontWeight: 600, color: infraMetrics.latT3 > 100 ? 'var(--color-error)' : 'var(--color-success-text)' }}>{infraMetrics.latT3}ms</div>
                </div>
              </div>
            </div>

            {/* Worker Utilization */}
            <div className="card" style={{ padding: 'var(--space-5)' }}>
              <div className="card-title" style={{ marginBottom: 'var(--space-5)' }}>Worker Utilization</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
                {['Worker 1', 'Worker 2', 'Worker 3', 'Worker 4'].map((worker, i) => {
                  const pct = infraMetrics[`w${i + 1}`];
                  const color = pct > 80 ? 'var(--color-error)' : pct > 70 ? 'var(--color-warning)' : 'var(--color-indigo-500)';
                  return (
                    <div key={worker}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 'var(--text-xs)' }}>
                        <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>{worker}</span>
                        <span style={{ fontWeight: 600, color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>{pct}%</span>
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
                <CompactMetric label="Queue Pressure" value={isSpikeMode ? 'HIGH' : 'LOW'} valueColor={isSpikeMode ? 'var(--color-error)' : 'var(--color-success-text)'} />
                <CompactMetric label="Governor" value={isSpikeMode ? 'ACTIVE' : 'STANDBY'} />
                <CompactMetric label="Shedding" value={isSpikeMode ? 'NON-CRITICAL ONLY' : 'DISABLED'} />
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
                    {shedStats.shed.toLocaleString()}
                  </div>
                </div>

                <div style={{ padding: 'var(--space-4)', background: 'rgba(247, 144, 9, 0.05)', border: '1px solid rgba(247, 144, 9, 0.15)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-warning)' }}>DEFERRED</div>
                  <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--color-warning)', fontVariantNumeric: 'tabular-nums' }}>
                    {shedStats.deferred.toLocaleString()}
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
