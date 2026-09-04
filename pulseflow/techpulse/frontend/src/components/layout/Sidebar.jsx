import { Zap, Layers, Users, GitBranch, Eye, Settings } from 'lucide-react'

/* ─ Nav structure ─────────────────────────────────────────── */
const sections = [
  {
    label: 'Simulator & Core',
    items: [
      { id: 'load-spiker', label: 'Load Spiker', icon: Zap },
    ],
  },
  {
    label: 'Infrastructure',
    items: [
      { id: 'queues',        label: 'Queues',        icon: Layers },
      { id: 'workers',       label: 'Workers',       icon: Users },
      { id: 'decisions',     label: 'Decisions',     icon: GitBranch },
      { id: 'observability', label: 'Observability', icon: Eye },
    ],
  },
]

/* ─ Logo mark: two interlocked arcs (pure SVG, no external dep) */
function PulseLogo() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      {/* Waveform-style geometric mark */}
      <rect x="1"  y="8"  width="2" height="4" rx="1" fill="white" opacity="0.7" />
      <rect x="4"  y="5"  width="2" height="7" rx="1" fill="white" opacity="0.85" />
      <rect x="7"  y="2"  width="2" height="10" rx="1" fill="white" />
      <rect x="10" y="5"  width="2" height="7" rx="1" fill="white" opacity="0.85" />
      <rect x="13" y="8"  width="2" height="4" rx="1" fill="white" opacity="0.7" />
    </svg>
  )
}

export default function Sidebar({ activeNav, onNavChange }) {
  return (
    <aside className="sidebar">

      {/* ── Brand ─────────────────────────────────────────── */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">
          <PulseLogo />
        </div>
        <span className="sidebar-brand-name">PulseFlow</span>
      </div>

      {/* ── Nav sections ──────────────────────────────────── */}
      <div className="sidebar-section">
        {sections.map((section, si) => (
          <div key={section.label}>
            {si > 0 && <div className="sidebar-divider" />}

            <div className="sidebar-section-label">{section.label}</div>

            <nav className="sidebar-nav">
              {section.items.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  id={`nav-${id}`}
                  className={`sidebar-nav-item${activeNav === id ? ' active' : ''}`}
                  onClick={() => onNavChange(id)}
                  title={label}
                >
                  <Icon size={14} className="sidebar-nav-icon" strokeWidth={1.8} />
                  <span>{label}</span>
                </button>
              ))}
            </nav>
          </div>
        ))}
      </div>

      {/* ── Footer ────────────────────────────────────────── */}
      <div className="sidebar-footer">
        <button
          className={`sidebar-nav-item${activeNav === 'settings' ? ' active' : ''}`}
          onClick={() => onNavChange('settings')}
          id="nav-settings"
          title="Settings"
        >
          <Settings size={13} className="sidebar-nav-icon" strokeWidth={1.8} />
          <span>Settings</span>
        </button>
      </div>

    </aside>
  )
}
