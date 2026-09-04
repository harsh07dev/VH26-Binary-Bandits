import { useState } from 'react'
import Sidebar from './components/layout/Sidebar.jsx'
import Topbar from './components/layout/Topbar.jsx'
import ObservabilityPage from './pages/ObservabilityPage.jsx'

export default function App() {
  const [activeNav, setActiveNav] = useState('observability')

  return (
    <div className="app-shell">
      <Sidebar activeNav={activeNav} onNavChange={setActiveNav} />

      <div className="main-content">
        <Topbar />

        {/* Active page */}
        {activeNav === 'observability' && <ObservabilityPage />}

        {/* Stub pages for other nav items */}
        {activeNav !== 'observability' && (
          <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>
              {activeNav.charAt(0).toUpperCase() + activeNav.slice(1).replace('-', ' ')} — coming soon
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
