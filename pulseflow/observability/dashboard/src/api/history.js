/*
  history.js — History API client for HistoryPage.

  All requests go to BACKEND_URL which is defined once here.
  To point at a different host (e.g. http://192.168.137.10:8000),
  change only this constant.
*/

const BACKEND_URL = 'http://127.0.0.1:8000';

/**
 * Fetch processed event history with optional filters.
 *
 * @param {object} filters
 * @param {string} [filters.event_id]
 * @param {string} [filters.event_type]
 * @param {string} [filters.priority]
 * @param {string} [filters.status]
 * @param {number} [filters.limit=50]
 * @returns {Promise<{status: string, count: number, events: object[]}>}
 */
export async function fetchEventHistory({
  event_id = '',
  event_type = '',
  priority = '',
  status = '',
  limit = 50,
} = {}) {
  const params = new URLSearchParams();
  if (event_id)   params.set('event_id',   event_id.trim());
  if (event_type) params.set('event_type', event_type);
  if (priority)   params.set('priority',   priority);
  if (status)     params.set('status',     status);
  params.set('limit', String(limit));

  const res = await fetch(`${BACKEND_URL}/events/history?${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/**
 * Fetch a single persisted event by ID.
 *
 * @param {string} eventId
 * @returns {Promise<object>}
 * @throws {Error} with status 404 if not found
 */
export async function fetchEventById(eventId) {
  const res = await fetch(`${BACKEND_URL}/events/${encodeURIComponent(eventId)}`);
  if (res.status === 404) throw Object.assign(new Error('not_found'), { status: 404 });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
