import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

/**
 * Design System Preview Page
 * Showcases all design tokens: cards, buttons, badges, status indicators, typography
 */
export default function DesignSystemPreview() {
  return (
    <div className="animate-fade-in">

      {/* Page Header */}
      <div className="page-header">
        <h1 className="page-title">Design System</h1>
        <p className="page-subtitle">
          PulseFlow UI foundations — tokens, components & layout primitives
        </p>
      </div>

      {/* ── Section: Metric Cards ── */}
      <Section title="Metric Cards" subtitle="Compact KPI tiles used across the dashboard">
        <div className="grid grid-cols-4 gap-4">
          <MetricCard
            label="Requests/sec"
            value="24,381"
            unit="rps"
            delta="+18.4%"
            direction="up"
          />
          <MetricCard
            label="Surge Multiplier"
            value="20×"
            delta="SURGE ACTIVE"
            direction="warn"
          />
          <MetricCard
            label="P99 Latency"
            value="142"
            unit="ms"
            delta="-3.1%"
            direction="down"
          />
          <MetricCard
            label="Error Rate"
            value="0.08"
            unit="%"
            delta="nominal"
            direction="neutral"
          />
        </div>
      </Section>

      {/* ── Section: Status Indicators ── */}
      <Section title="Status Indicators" subtitle="Live status dots, pills and badges">
        <div className="flex items-center flex-wrap gap-6">
          <div className="flex items-center gap-2">
            <span className="status-dot status-dot-live-green" />
            <span className="text-sm text-secondary">Live / Healthy</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="status-dot status-dot-live" />
            <span className="text-sm text-secondary">Live / Processing</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="status-dot status-dot-live-red" />
            <span className="text-sm text-secondary">Live / Critical</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="status-dot status-dot-warning" />
            <span className="text-sm text-secondary">Warning</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="status-dot status-dot-idle" />
            <span className="text-sm text-secondary">Idle</span>
          </div>
        </div>

        <div className="flex items-center flex-wrap gap-3 mt-4">
          <div className="status-pill status-pill-online">
            <span className="status-dot status-dot-sm status-dot-live-green" />
            Online
          </div>
          <div className="status-pill status-pill-warning">
            <span className="status-dot status-dot-sm status-dot-warning" />
            Pressure
          </div>
          <div className="status-pill status-pill-error">
            <span className="status-dot status-dot-sm status-dot-live-red" />
            Critical
          </div>
          <div className="status-pill status-pill-idle">
            <span className="status-dot status-dot-sm status-dot-idle" />
            Standby
          </div>
        </div>
      </Section>

      {/* ── Section: Badges ── */}
      <Section title="Badges" subtitle="Priority tiers, state labels and semantic classifications">
        <div className="flex items-center flex-wrap gap-2">
          <span className="badge badge-error">
            <span className="badge-dot" style={{ background: 'var(--color-error)' }} />
            CRITICAL
          </span>
          <span className="badge badge-success">
            <span className="badge-dot" style={{ background: 'var(--color-success)' }} />
            NORMAL
          </span>
          <span className="badge badge-gray">
            <span className="badge-dot" style={{ background: 'var(--color-gray-400)' }} />
            BEST-EFFORT
          </span>
          <span className="badge badge-warning">SURGE</span>
          <span className="badge badge-indigo">STREAMING</span>
          <span className="badge badge-info">MICRO-BATCH</span>
          <span className="badge badge-outline">SAMPLED</span>
          <span className="badge badge-gray">DEFERRED</span>
        </div>
      </Section>

      {/* ── Section: Buttons ── */}
      <Section title="Buttons" subtitle="Primary, secondary, ghost and utility actions">
        <div className="flex items-center flex-wrap gap-3">
          <button className="btn btn-primary">Start Surge</button>
          <button className="btn btn-primary btn-lg">Run Benchmark</button>
          <button className="btn btn-secondary">Configure</button>
          <button className="btn btn-secondary btn-sm">Export</button>
          <button className="btn btn-ghost">View Logs</button>
          <button className="btn btn-danger">Halt</button>
          <button className="btn btn-ghost btn-sm">Cancel</button>
        </div>
      </Section>

      {/* ── Section: Progress Bars ── */}
      <Section title="Progress Bars" subtitle="Queue depth, worker utilisation, throughput meters">
        <div className="flex flex-col gap-4" style={{ maxWidth: 480 }}>
          <ProgressRow label="Critical Queue" value={82} variant="indigo" />
          <ProgressRow label="Normal Queue"   value={51} variant="success" />
          <ProgressRow label="Best-Effort"    value={34} variant="warning" />
          <ProgressRow label="Error Rate"     value={8}  variant="error" />
        </div>
      </Section>

      {/* ── Section: Cards ── */}
      <Section title="Cards" subtitle="Surface variants used across the layout">
        <div className="grid grid-cols-3 gap-4">
          {/* Standard card */}
          <div className="card">
            <div className="card-header">
              <div className="card-header-left">
                <span className="status-dot status-dot-live-green" />
                <span className="card-title">Queue Status</span>
              </div>
              <span className="badge badge-success">Healthy</span>
            </div>
            <div className="card-body-sm p-4">
              <p className="text-sm text-secondary">
                All three queues operating within nominal bounds. No shedding active.
              </p>
            </div>
          </div>

          {/* Interactive card */}
          <div className="card card-interactive">
            <div className="card-header">
              <div className="card-header-left">
                <span className="status-dot status-dot-warning" />
                <span className="card-title">Pressure Event</span>
              </div>
              <span className="badge badge-warning">Watch</span>
            </div>
            <div className="card-body-sm p-4">
              <p className="text-sm text-secondary">
                Normal queue depth elevated. Workers partially reassigned.
              </p>
            </div>
          </div>

          {/* Error card */}
          <div className="card">
            <div className="card-header">
              <div className="card-header-left">
                <span className="status-dot status-dot-live-red" />
                <span className="card-title">Surge Active</span>
              </div>
              <span className="badge badge-error">20×</span>
            </div>
            <div className="card-body-sm p-4">
              <p className="text-sm text-secondary">
                Machine 1 generating 20× synthetic load. Best-effort shedding enabled.
              </p>
            </div>
          </div>
        </div>
      </Section>

      {/* ── Section: Typography Scale ── */}
      <Section title="Typography" subtitle="Inter typeface across all text styles">
        <div className="card">
          <div className="card-body-sm p-5">
            <div className="flex flex-col gap-3">
              <div className="flex items-baseline gap-4">
                <span className="text-3xl font-bold tracking-tight">3xl · Dashboard Title</span>
                <span className="text-xs text-tertiary">28px bold</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-2xl font-bold tracking-tight">2xl · Section Heading</span>
                <span className="text-xs text-tertiary">22px bold</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-xl font-semibold">xl · Card Title Large</span>
                <span className="text-xs text-tertiary">18px semibold</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-lg font-medium">lg · Card Title</span>
                <span className="text-xs text-tertiary">16px medium</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-md">md · Body Default</span>
                <span className="text-xs text-tertiary">14px regular</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-base text-secondary">base · Secondary text</span>
                <span className="text-xs text-tertiary">13px regular</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-sm text-tertiary">sm · Label / Meta</span>
                <span className="text-xs text-tertiary">12px regular</span>
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-xs uppercase tracking-wide font-semibold text-tertiary">xs · SECTION LABEL</span>
                <span className="text-xs text-tertiary">11px, uppercase</span>
              </div>
            </div>
          </div>
        </div>
      </Section>

      {/* ── Section: Color Palette ── */}
      <Section title="Color Palette" subtitle="90% neutral · 8% indigo · 2% semantic">
        <div className="flex flex-col gap-4">
          <SwatchRow label="Indigo (Primary)" swatches={[
            { name: '50',  bg: '#EEEEFF', fg: '#635BFF' },
            { name: '100', bg: '#E0E0FF', fg: '#635BFF' },
            { name: '200', bg: '#C4C4FF', fg: '#4F46E5' },
            { name: '400', bg: '#8B83FF', fg: 'white' },
            { name: '500', bg: '#635BFF', fg: 'white' },
            { name: '600', bg: '#4F46E5', fg: 'white' },
            { name: '700', bg: '#3730A3', fg: 'white' },
            { name: '900', bg: '#1E1B4B', fg: 'white' },
          ]} />
          <SwatchRow label="Neutral" swatches={[
            { name: '50',  bg: '#F9FAFB', fg: '#6B7280' },
            { name: '100', bg: '#F3F4F6', fg: '#6B7280' },
            { name: '200', bg: '#E5E7EB', fg: '#374151' },
            { name: '300', bg: '#D1D5DB', fg: '#374151' },
            { name: '400', bg: '#9CA3AF', fg: 'white' },
            { name: '500', bg: '#6B7280', fg: 'white' },
            { name: '700', bg: '#374151', fg: 'white' },
            { name: '900', bg: '#111827', fg: 'white' },
          ]} />
          <SwatchRow label="Semantic" swatches={[
            { name: 'Success', bg: '#22C55E', fg: 'white' },
            { name: 'Warning', bg: '#F59E0B', fg: 'white' },
            { name: 'Error',   bg: '#EF4444', fg: 'white' },
          ]} />
        </div>
      </Section>

    </div>
  )
}

/* ── Helper sub-components ── */

function Section({ title, subtitle, children }) {
  return (
    <section style={{ marginBottom: 'var(--space-8)' }}>
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <h2 className="text-md font-semibold text-primary">{title}</h2>
        {subtitle && <p className="text-sm text-secondary mt-1">{subtitle}</p>}
      </div>
      {children}
    </section>
  )
}

function MetricCard({ label, value, unit, delta, direction }) {
  const deltaClass =
    direction === 'up'   ? 'up'    :
    direction === 'down' ? 'down'  :
    direction === 'warn' ? 'down'  : 'neutral'

  const DeltaIcon =
    direction === 'up'   ? TrendingUp   :
    direction === 'down' ? TrendingDown :
    Minus

  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="metric-value tabular-nums">{value}</span>
        {unit && <span className="metric-unit">{unit}</span>}
      </div>
      <div className={`metric-delta ${deltaClass}`}>
        <DeltaIcon size={11} strokeWidth={2.5} />
        <span>{delta}</span>
      </div>
    </div>
  )
}

function ProgressRow({ label, value, variant }) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="text-sm text-secondary">{label}</span>
        <span className="text-sm font-medium tabular-nums text-primary">{value}%</span>
      </div>
      <div className="progress-bar-track">
        <div
          className={`progress-bar-fill progress-bar-fill-${variant}`}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  )
}

function SwatchRow({ label, swatches }) {
  return (
    <div>
      <div className="text-xs text-tertiary mb-2 uppercase tracking-wide font-semibold">{label}</div>
      <div className="flex flex-wrap gap-2">
        {swatches.map(({ name, bg, fg }) => (
          <div key={name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <div
              style={{
                width: 48,
                height: 32,
                background: bg,
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--color-border)',
              }}
            />
            <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)' }}>{name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
