/**
 * PageHeader — Main content area header
 *
 * Renders:
 *   · Large title
 *   · Subtitle line
 *   · Compact stat pills (Spikes Injected · Total Boosted Events)
 */
export default function PageHeader({ spikesInjected = 44, spikesTotal = 50, boostedEvents = '720,000' }) {
  return (
    <div className="page-header">

      {/* Title */}
      <h1 className="page-header-title">
        Tech Pulse
      </h1>

      {/* Subtitle */}
      <p className="page-header-subtitle">
        <strong style={{ color: 'var(--color-text-primary)' }}>Synthetic Load Spiker &amp; Surge Engine</strong><br/>
        Generate controlled synthetic traffic and payload spikes for the PulseFlow adaptive pipeline.
      </p>

      {/* Stat pills row */}
      <div className="page-header-pills">

        {/* Pill 1: Spikes Injected */}
        <div className="stat-pill" id="pill-spikes-injected">
          <span className="stat-pill-label">Spikes Injected</span>
          <span className="stat-pill-divider" />
          <span className="stat-pill-value">
            {spikesInjected}
            <span style={{ color: 'var(--color-text-tertiary)', fontWeight: 400 }}>
              {' '}/ {spikesTotal}
            </span>
          </span>
        </div>

        {/* Pill 2: Total Boosted Events */}
        <div className="stat-pill" id="pill-boosted-events">
          <span className="stat-pill-label">Total Boosted Events</span>
          <span className="stat-pill-divider" />
          <span className="stat-pill-value" style={{ color: 'var(--color-indigo-600)' }}>
            +{boostedEvents} events
          </span>
        </div>

      </div>
    </div>
  )
}
