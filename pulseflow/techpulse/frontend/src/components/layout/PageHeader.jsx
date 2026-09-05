import { Zap, Activity, CheckCircle, Flame } from 'lucide-react'

/**
 * PageHeader — Main content area header
 * High-density title and status pills matching Observability
 */
export default function PageHeader({
  spikesInjected = 0,
  spikesTotal = 50,
  boostedEvents = '0',
  egressRate = '8,400',
  isSurging = false,
  isPaused = false
}) {
  return (
    <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <h1 className="page-header-title" style={{ margin: 0 }}>
            TechPulse Workload Generator
          </h1>
          <span className={`status-pill ${isPaused ? 'status-pill-warning' : isSurging ? 'status-pill-error' : 'status-pill-online'}`} style={{ fontSize: '11px', padding: '3px 9px' }}>
            <span className={`status-dot status-dot-sm ${isPaused ? 'status-dot-warning' : isSurging ? 'status-dot-live-red' : 'status-dot-live-green'}`} />
            {isPaused ? 'SIMULATION PAUSED' : isSurging ? 'SURGE BURST ACTIVE' : 'STEADY BASELINE'}
          </span>
          {isSurging && (
            <span className="badge badge-error badge-pulse-red" style={{ padding: '3px 8px', fontSize: '11px' }}>
              <Flame size={12} /> STRESSING PIPELINE
            </span>
          )}
        </div>
      </div>

      {/* Stat pills row */}
      <div className="page-header-pills" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        {/* Pill 1: Spikes Injected */}
        <div className="stat-pill" id="pill-spikes-injected">
          <span className="stat-pill-label">Spikes Injected</span>
          <span className="stat-pill-divider" />
          <span className="stat-pill-value font-mono">
            {spikesInjected}
            <span style={{ color: 'var(--color-text-tertiary)', fontWeight: 400 }}>
              {' '}/ {spikesTotal}
            </span>
          </span>
        </div>

        {/* Pill 2: Total Session Events */}
        <div className="stat-pill" id="pill-boosted-events">
          <span className="stat-pill-label">Total Generated</span>
          <span className="stat-pill-divider" />
          <span className="stat-pill-value font-mono" style={{ color: 'var(--color-indigo-600)' }}>
            +{boostedEvents}
          </span>
        </div>

        {/* Pill 3: Egress Velocity */}
        <div className="stat-pill">
          <span className="stat-pill-label">Egress Velocity</span>
          <span className="stat-pill-divider" />
          <span className="stat-pill-value font-mono" style={{ color: isSurging ? 'var(--color-error)' : 'var(--color-success-text)' }}>
            {egressRate} ev/s
          </span>
        </div>
      </div>
    </div>
  )
}

