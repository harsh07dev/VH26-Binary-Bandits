/**
 * Topbar — Machine 2 System Bar
 * Title:    PulseFlow Observability
 * Subtitle: Monitor adaptive processing…
 * Right:    ● Pipeline Live
 */
export default function Topbar() {
  return (
    <header className="topbar">

      {/* ── Left: title stack ─────────────────────────────── */}
      <div className="topbar-left">
        <div className="topbar-title">PulseFlow Observability</div>
        <div className="topbar-subtitle">
          Monitor adaptive processing, queue pressure, routing decisions and critical-event latency in real time.
        </div>
      </div>

      {/* ── Right: status indicator ───────────────────────── */}
      <div className="topbar-right">
        <div className="status-ready" id="topbar-pipeline-status">
          <span
            className="status-dot status-dot-live-green"
            style={{ width: 6, height: 6 }}
          />
          Pipeline Live
        </div>
      </div>

    </header>
  )
}
