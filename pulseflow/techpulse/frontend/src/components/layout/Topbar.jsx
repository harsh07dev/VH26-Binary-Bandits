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
        <div className="topbar-title">Synthetic Load Spiker &amp; Surge Engine</div>
        <div className="topbar-subtitle">
          Select spike volume, preview immediate pipeline stress, and trigger instantaneous surge waves.
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
