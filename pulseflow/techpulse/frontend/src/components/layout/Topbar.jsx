import { useState, useEffect } from 'react'
import { Server, ExternalLink, Activity, ArrowRight } from 'lucide-react'
import { telemetryClient } from '../../api/telemetry.js'

/**
 * Topbar — System Bar
 * Left: Machine 1 breadcrumbs & Target Pipeline indicator
 * Right: Live Bridge status & link to Machine 2 Observability
 */
export default function Topbar() {
  const [bridgeStatus, setBridgeStatus] = useState({
    isConnected: true,
    latencyMs: 1.2,
  })

  useEffect(() => {
    const unsub = telemetryClient.subscribe(state => {
      setBridgeStatus({
        isConnected: state.isConnected,
        latencyMs: state.latencyMs,
      })
    })
    return unsub
  }, [])

  return (
    <header className="topbar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 var(--space-6)' }}>
      {/* ── Left: Breadcrumb & Pipeline Bridge Indicator ──── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: 'var(--text-xs)', fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--color-text-secondary)' }}>
          <span style={{ color: 'var(--color-indigo-600)', background: 'rgba(99, 91, 255, 0.08)', padding: '2px 7px', borderRadius: 'var(--radius-xs)' }}>
            Machine 1
          </span>
          <span>/</span>
          <span style={{ color: 'var(--color-text-primary)' }}>Synthetic Workload &amp; Surge Generator</span>
        </div>

        <div style={{ width: 1, height: 14, background: 'var(--color-border)' }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: 'var(--color-text-tertiary)' }}>
          <span>Target Bridge:</span>
          <span style={{ color: 'var(--color-text-secondary)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
            Machine 2 (PulseFlow :8000)
          </span>
        </div>
      </div>

      {/* ── Right: Bridge Status & Telemetry Link ─────────── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        {/* Live Bridge Ping Pill */}
        <div
          className={`status-pill ${bridgeStatus.isConnected ? 'status-pill-online' : 'status-pill-error'}`}
          style={{ fontSize: '11px', padding: '3px 9px', display: 'flex', alignItems: 'center', gap: '6px' }}
          title="HTTP Ingestion Bridge to Machine 2 (/events/batch)"
        >
          <span className={`status-dot status-dot-sm ${bridgeStatus.isConnected ? 'status-dot-live-green' : 'status-dot-live-red'}`} />
          <span style={{ fontWeight: 700 }}>
            {bridgeStatus.isConnected ? 'BRIDGE ONLINE' : 'BRIDGE DISCONNECTED'}
          </span>
          <span style={{ color: 'var(--color-text-tertiary)', fontVariantNumeric: 'tabular-nums' }}>
            ({bridgeStatus.latencyMs}ms)
          </span>
        </div>

        {/* Link to Observability Dashboard */}
        <a
          href="http://localhost:5174/"
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-secondary btn-sm"
          style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '5px', fontWeight: 600 }}
          title="Open PulseFlow Observability Dashboard in Machine 2"
        >
          <span>Observability (5174)</span>
          <ExternalLink size={12} strokeWidth={2} />
        </a>
      </div>
    </header>
  )
}

