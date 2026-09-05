import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Search, RefreshCw, X, Clock, Database, AlertCircle, ChevronRight } from 'lucide-react'
import { fetchEventHistory, fetchEventById } from '../api/history'

/* ─── Constants ─────────────────────────────────────────────── */

const PRIORITY_OPTIONS = ['', 'CRITICAL', 'NORMAL', 'BEST_EFFORT']
const DEFAULT_LIMIT = 50

/* ─── Priority badge helper (reuses existing badge-* classes) ── */
function PriorityBadge({ priority }) {
  if (priority === 'CRITICAL') {
    return <span className="badge badge-indigo">{priority}</span>
  }
  if (priority === 'NORMAL') {
    return <span className="badge badge-outline">{priority}</span>
  }
  if (priority === 'BEST_EFFORT') {
    return <span className="badge badge-gray">{priority}</span>
  }
  return <span className="badge badge-gray">{priority ?? '—'}</span>
}

/* ─── Status badge helper ────────────────────────────────────── */
function StatusBadge({ status }) {
  if (!status) return <span className="badge badge-gray">—</span>
  const s = status.toLowerCase()
  if (s === 'processed')  return <span className="badge badge-success">{status}</span>
  if (s === 'failed')     return <span className="badge badge-error">{status}</span>
  if (s === 'deferred')   return <span className="badge badge-warning">{status}</span>
  return <span className="badge badge-gray">{status}</span>
}

/* ─── Timestamp formatter ────────────────────────────────────── */
function fmtTs(epoch) {
  if (!epoch) return '—'
  return new Date(epoch * 1000).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function fmtLatency(ms) {
  if (ms == null) return '—'
  return `${Number(ms).toFixed(2)} ms`
}

/* ─── Detail Drawer ──────────────────────────────────────────── */
function EventDrawer({ eventId, onClose }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    if (!eventId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setData(null)
    fetchEventById(eventId)
      .then(d => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch(e => { if (!cancelled) { setError(e); setLoading(false) } })
    return () => { cancelled = true }
  }, [eventId])

  // Close on Escape
  useEffect(() => {
    const handler = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(17,24,39,0.18)',
          zIndex: 'var(--z-overlay)',
          animation: 'fade-in 150ms ease',
        }}
      />

      {/* Drawer panel */}
      <div
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0,
          width: 440,
          background: 'var(--color-surface)',
          borderLeft: '1px solid var(--color-border)',
          boxShadow: 'var(--shadow-lg)',
          zIndex: 'var(--z-modal)',
          display: 'flex', flexDirection: 'column',
          animation: 'slide-in-right 180ms ease',
        }}
      >
        {/* Drawer header */}
        <div className="card-header" style={{ flexShrink: 0 }}>
          <div className="card-header-left">
            <Database size={14} style={{ color: 'var(--color-indigo-500)' }} strokeWidth={1.8} />
            <span className="card-title">Event Detail</span>
          </div>
          <button className="btn btn-ghost btn-icon btn-icon-sm" onClick={onClose} title="Close">
            <X size={14} />
          </button>
        </div>

        {/* Drawer body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-5)' }}>

          {loading && (
            <div style={{ textAlign: 'center', padding: 'var(--space-10)', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>
              <RefreshCw size={16} style={{ marginBottom: 8, animation: 'spin 1s linear infinite', display: 'block', margin: '0 auto 8px' }} />
              Loading…
            </div>
          )}

          {!loading && error && error.status === 404 && (
            <div style={{ textAlign: 'center', padding: 'var(--space-10)' }}>
              <AlertCircle size={28} style={{ color: 'var(--color-text-tertiary)', marginBottom: 8, display: 'block', margin: '0 auto 8px' }} />
              <div style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)' }}>Event not found.</div>
            </div>
          )}

          {!loading && error && error.status !== 404 && (
            <div className="card" style={{ padding: 'var(--space-4)', background: 'var(--color-error-bg)', borderColor: 'var(--color-error-border)' }}>
              <span style={{ color: 'var(--color-error-text)', fontSize: 'var(--text-sm)' }}>
                Failed to load event: {error.message}
              </span>
            </div>
          )}

          {!loading && !error && data && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              {/* Identity */}
              <div className="card card-sm">
                <div className="card-header">
                  <span className="card-title">Identity</span>
                </div>
                <div className="card-body-sm">
                  <DetailRow label="Event ID"       value={<code style={{ fontFamily: 'monospace', fontSize: 'var(--text-xs)', background: 'var(--color-gray-100)', padding: '2px 5px', borderRadius: 4 }}>{data.event_id}</code>} />
                  <DetailRow label="Event Type"     value={data.event_type} />
                  <DetailRow label="Priority"       value={<PriorityBadge priority={data.priority} />} />
                  <DetailRow label="Status"         value={<StatusBadge status={data.status} />} />
                  <DetailRow label="Processing Mode" value={data.processing_mode ?? '—'} />
                </div>
              </div>

              {/* Timing */}
              <div className="card card-sm">
                <div className="card-header">
                  <span className="card-title">Timing</span>
                </div>
                <div className="card-body-sm">
                  <DetailRow label="Received At"   value={fmtTs(data.received_at)} />
                  <DetailRow label="Processed At"  value={fmtTs(data.processed_at)} />
                  <DetailRow label="Latency"       value={<span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--color-indigo-600)', fontWeight: 600 }}>{fmtLatency(data.latency_ms)}</span>} />
                </div>
              </div>

              {/* Payload */}
              <div className="card card-sm">
                <div className="card-header">
                  <span className="card-title">Payload</span>
                </div>
                <div style={{ padding: 'var(--space-4)' }}>
                  <pre style={{
                    fontSize: 'var(--text-xs)',
                    fontFamily: 'monospace',
                    color: 'var(--color-text-primary)',
                    background: 'var(--color-gray-50)',
                    border: '1px solid var(--color-border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: 'var(--space-3)',
                    overflowX: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                    margin: 0,
                  }}>
                    {JSON.stringify(data.payload, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

/* Small key-value row inside the drawer */
function DetailRow({ label, value }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center',
      gap: 'var(--space-3)',
      padding: '6px 0',
      borderBottom: '1px solid var(--color-border-subtle)',
    }}>
      <span style={{
        width: 120, flexShrink: 0,
        fontSize: 'var(--text-xs)', fontWeight: 600,
        textTransform: 'uppercase', letterSpacing: '0.04em',
        color: 'var(--color-text-tertiary)',
      }}>
        {label}
      </span>
      <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-primary)', minWidth: 0 }}>
        {value}
      </span>
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   HistoryPage — Additive page, existing UI untouched
═══════════════════════════════════════════════════════════════ */
export default function HistoryPage() {
  /* ── Filter state ────────────────────────────────────────── */
  const [eventId,   setEventId]   = useState('')
  const [eventType, setEventType] = useState('')
  const [priority,  setPriority]  = useState('')
  const [status,    setStatus]    = useState('')
  const [limit,     setLimit]     = useState(DEFAULT_LIMIT)

  /* ── Data state ──────────────────────────────────────────── */
  const [events,   setEvents]   = useState([])
  const [count,    setCount]    = useState(0)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState(null)

  /* ── Drawer state ────────────────────────────────────────── */
  const [selectedId, setSelectedId] = useState(null)

  /* ── Debounce event_id search ─────────────────────────────── */
  const debounceRef = useRef(null)

  const load = useCallback(async (filters) => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetchEventHistory(filters)
      setEvents(res.events ?? [])
      setCount(res.count ?? 0)
    } catch (e) {
      setError(e.message)
      setEvents([])
      setCount(0)
    } finally {
      setLoading(false)
    }
  }, [])

  /* Initial load */
  useEffect(() => {
    load({ limit: DEFAULT_LIMIT })
  }, [load])

  /* ── Apply filters ────────────────────────────────────────── */
  const applyFilters = useCallback(() => {
    clearTimeout(debounceRef.current)
    load({ event_id: eventId, event_type: eventType, priority, status, limit })
  }, [eventId, eventType, priority, status, limit, load])

  /* Debounce event_id as user types */
  useEffect(() => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      load({ event_id: eventId, event_type: eventType, priority, status, limit })
    }, 400)
    return () => clearTimeout(debounceRef.current)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId])

  /* Re-run when select filters change immediately */
  useEffect(() => {
    load({ event_id: eventId, event_type: eventType, priority, status, limit })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventType, priority, status, limit])

  const clearFilters = () => {
    setEventId(''); setEventType(''); setPriority(''); setStatus(''); setLimit(DEFAULT_LIMIT)
    load({ limit: DEFAULT_LIMIT })
  }

  const hasFilters = eventId || eventType || priority || status

  return (
    <div className="page" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)', paddingBottom: 'var(--space-10)' }}>

      {/* ── Page heading ─────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-3)' }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 2 }}>
            Event History
          </h1>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-secondary)' }}>
            Browse and search persisted processed events from the PulseFlow pipeline database.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          {count > 0 && (
            <span className="stat-pill">
              <span className="stat-pill-label">Results</span>
              <span className="stat-pill-divider" />
              <span className="stat-pill-value">{count}</span>
            </span>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={applyFilters}
            disabled={loading}
            title="Refresh results"
          >
            <RefreshCw size={12} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── Filter toolbar ────────────────────────────────────── */}
      <div className="card card-sm">
        <div className="card-body-sm">
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'flex-end' }}>

            {/* Event ID search */}
            <div style={{ flex: '2 1 180px', minWidth: 160 }}>
              <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>
                Event ID
              </label>
              <div style={{ position: 'relative' }}>
                <Search size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-tertiary)' }} />
                <input
                  className="input"
                  style={{ paddingLeft: 26, fontSize: 'var(--text-sm)' }}
                  placeholder="Search by event ID…"
                  value={eventId}
                  onChange={e => setEventId(e.target.value)}
                />
              </div>
            </div>

            {/* Event Type */}
            <div style={{ flex: '1 1 130px', minWidth: 120 }}>
              <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>
                Event Type
              </label>
              <input
                className="input"
                style={{ fontSize: 'var(--text-sm)' }}
                placeholder="ORDER, CLICK…"
                value={eventType}
                onChange={e => setEventType(e.target.value)}
              />
            </div>

            {/* Priority */}
            <div style={{ flex: '1 1 130px', minWidth: 120 }}>
              <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>
                Priority
              </label>
              <select
                className="input"
                style={{ fontSize: 'var(--text-sm)', cursor: 'pointer' }}
                value={priority}
                onChange={e => setPriority(e.target.value)}
              >
                <option value="">All priorities</option>
                {PRIORITY_OPTIONS.filter(Boolean).map(p => (
                  <option key={p} value={p}>{p.replace('_', ' ')}</option>
                ))}
              </select>
            </div>

            {/* Status */}
            <div style={{ flex: '1 1 120px', minWidth: 110 }}>
              <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>
                Status
              </label>
              <input
                className="input"
                style={{ fontSize: 'var(--text-sm)' }}
                placeholder="processed…"
                value={status}
                onChange={e => setStatus(e.target.value)}
              />
            </div>

            {/* Limit */}
            <div style={{ flex: '0 0 80px' }}>
              <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>
                Limit
              </label>
              <select
                className="input"
                style={{ fontSize: 'var(--text-sm)', cursor: 'pointer' }}
                value={limit}
                onChange={e => setLimit(Number(e.target.value))}
              >
                {[20, 50, 100, 250, 500].map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>

            {/* Clear */}
            {hasFilters && (
              <div style={{ alignSelf: 'flex-end' }}>
                <button className="btn btn-ghost btn-sm" onClick={clearFilters} title="Clear all filters">
                  <X size={12} /> Clear
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Error banner ──────────────────────────────────────── */}
      {error && (
        <div className="card" style={{
          padding: 'var(--space-4)',
          background: 'var(--color-error-bg)',
          borderColor: 'var(--color-error-border)',
          display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
        }}>
          <AlertCircle size={14} style={{ color: 'var(--color-error-text)', flexShrink: 0 }} />
          <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-error-text)' }}>
            Failed to load history: {error}
          </span>
        </div>
      )}

      {/* ── Results table ─────────────────────────────────────── */}
      <div className="card" style={{ overflow: 'hidden' }}>
        <div className="card-header">
          <div className="card-header-left">
            <Clock size={13} style={{ color: 'var(--color-text-tertiary)' }} strokeWidth={1.8} />
            <span className="card-title">Processed Events</span>
            {loading && (
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-tertiary)' }}>
                <RefreshCw size={11} style={{ display: 'inline', animation: 'spin 1s linear infinite', marginRight: 4 }} />
                Loading…
              </span>
            )}
          </div>
          <span className="card-subtitle">Sorted by processed time, newest first · Click a row for details</span>
        </div>

        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Event ID</th>
                <th>Type</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Mode</th>
                <th>Latency</th>
                <th>Processed At</th>
                <th style={{ width: 28 }} />
              </tr>
            </thead>
            <tbody>
              {!loading && events.length === 0 && (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 'var(--space-10)', color: 'var(--color-text-tertiary)', fontSize: 'var(--text-sm)' }}>
                    <Database size={24} style={{ display: 'block', margin: '0 auto var(--space-2)' }} />
                    No events found.{hasFilters ? ' Try adjusting your filters.' : ''}
                  </td>
                </tr>
              )}
              {events.map(evt => (
                <tr
                  key={evt.event_id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setSelectedId(evt.event_id)}
                >
                  <td>
                    <code style={{
                      fontFamily: 'monospace', fontSize: 'var(--text-xs)',
                      background: 'var(--color-gray-100)',
                      padding: '2px 5px', borderRadius: 4,
                      color: 'var(--color-text-primary)',
                    }}>
                      {evt.event_id}
                    </code>
                  </td>
                  <td>
                    <span className="tag">{evt.event_type}</span>
                  </td>
                  <td><PriorityBadge priority={evt.priority} /></td>
                  <td><StatusBadge status={evt.status} /></td>
                  <td style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>
                    {evt.processing_mode ?? '—'}
                  </td>
                  <td style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)' }}>
                    {fmtLatency(evt.latency_ms)}
                  </td>
                  <td style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}>
                    {fmtTs(evt.processed_at)}
                  </td>
                  <td style={{ paddingLeft: 0 }}>
                    <ChevronRight size={12} style={{ color: 'var(--color-text-tertiary)' }} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Event detail drawer ───────────────────────────────── */}
      {selectedId && (
        <EventDrawer eventId={selectedId} onClose={() => setSelectedId(null)} />
      )}

      {/* Inline spin keyframe (no new CSS file needed) */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
