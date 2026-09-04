import { useState } from 'react'
import Sidebar from './components/layout/Sidebar.jsx'
import Topbar from './components/layout/Topbar.jsx'
import LoadSpikerPage from './pages/LoadSpikerPage.jsx'

export default function App() {
  const [activeNav, setActiveNav] = useState('load-spiker')

  return (
    <div className="app-shell">
      <Sidebar activeNav={activeNav} onNavChange={setActiveNav} />

      <div className="main-content">
        <Topbar />

        {/* Route to the correct page */}
        {activeNav === 'load-spiker' && <LoadSpikerPage />}

        {/* Other pages — stubs, will be built later */}
        {activeNav !== 'load-spiker' && (
          <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>
              {activeNav.charAt(0).toUpperCase() + activeNav.slice(1)} — coming soon
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
