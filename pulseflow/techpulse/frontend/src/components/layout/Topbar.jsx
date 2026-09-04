/**
 * Topbar — System Bar
 * Left: title + subtitle
 * Right: Simulator Ready status indicator
 */
export default function Topbar() {
  return (
    <header className="topbar">

      {/* ── Left: title stack ─────────────────────────────── */}
      <div className="topbar-left">
        <div className="topbar-title">Tech Pulse <span style={{ color: 'var(--color-text-tertiary)', fontWeight: 400 }}>|</span> Synthetic Load Spiker &amp; Surge Engine</div>
        <div className="topbar-subtitle">
          Generate controlled synthetic traffic and payload spikes for the PulseFlow adaptive pipeline.
        </div>
      </div>

      {/* ── Right: status indicator ───────────────────────── */}
      <div className="topbar-right">
        <div className="status-ready" id="topbar-simulator-status">
          <span
            className="status-dot status-dot-live-green"
            style={{ width: 6, height: 6 }}
          />
          Simulator Ready
        </div>
      </div>

    </header>
  )
}
