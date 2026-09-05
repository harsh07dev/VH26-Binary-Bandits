import { useState, useEffect } from 'react'
import { ExternalLink } from 'lucide-react'
import { telemetryService } from '../../api/telemetry.js'

/**
 * Topbar — Machine 2 System Bar
 * Left:  Breadcrumb navigation (no duplicate titles)
 * Right: Workload generator cross-link & single live status dot
 */
export default function Topbar() {
  const [connected, setConnected] = useState(telemetryService.isConnected)

  useEffect(() => {
    return telemetryService.onConnectionChange(setConnected)
  }, [])

  return (
    <header className="topbar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 var(--space-6)' }}>
      {/* ── Left: Clean Breadcrumbs (No duplicate title) ──── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 'var(--text-xs)', fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--color-text-secondary)' }}>
          <span style={{ color: 'var(--color-indigo-600)', background: 'rgba(99, 91, 255, 0.08)', padding: '2px 7px', borderRadius: 'var(--radius-xs)' }}>
            Machine 2
          </span>
          <span>/</span>
          <span style={{ color: 'var(--color-text-primary)' }}>PulseFlow Observability Engine</span>
        </div>
      </div>

      {/* ── Right: Workload Generator Cross-Link + Single status dot ──── */}
      <div className="topbar-right" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <a
          href="http://localhost:5173/"
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-secondary btn-sm"
          style={{
            textDecoration: 'none',
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            fontWeight: 600,
            fontSize: '11px',
            padding: '3px 10px',
            borderRadius: 'var(--radius-xs)'
          }}
          title="Open TechPulse Workload Generator (Machine 1)"
        >
          <span>Workload Generator (5173)</span>
          <ExternalLink size={12} strokeWidth={2} />
        </a>

        <span
          id="topbar-pipeline-status-dot"
          className={`status-dot ${connected ? 'status-dot-live-green' : 'status-dot-live-red'}`}
          title={connected ? 'Pipeline Active (Machine 2)' : 'Pipeline Offline'}
          style={{ width: 8, height: 8, cursor: 'default' }}
        />
      </div>
    </header>
  )
}

