/* 
  Real API connection to Machine 2 (PulseFlow Pipeline).
  Polls the /metrics/adaptive endpoint every ~1.2s and broadcasts to subscribers.
  Falls back gracefully when the backend is unreachable.
*/

const BACKEND_URL = 'http://localhost:8000';
const POLL_INTERVAL_MS = 1200;

export class TelemetryService {
  constructor() {
    this.subscribers = new Set();
    this.eventSubscribers = new Set();
    this.connectionSubscribers = new Set();
    this.seenEvents = new Set();
    this.lastPayload = null;
    this.connected = false;
    this.isFetching = false;
    this.isPolling = false;
    this.pollTimer = null;
    this.initialTimeout = null;

    this.startPolling();
  }

  /**
   * Returns current backend connection status.
   */
  get isConnected() {
    return this.connected;
  }

  getConnectionStatus() {
    return this.connected;
  }

  /**
   * Subscribe to backend connection status changes.
   * Immediately invokes callback with current connection state.
   */
  onConnectionChange(callback) {
    this.connectionSubscribers.add(callback);
    callback(this.connected);
    return () => this.connectionSubscribers.delete(callback);
  }

  setConnected(status) {
    const changed = this.connected !== status;
    this.connected = status;
    if (changed) {
      this.connectionSubscribers.forEach(cb => {
        try {
          cb(this.connected);
        } catch (e) {
          console.error('[TelemetryService] Connection callback error:', e);
        }
      });
    }
  }

  onTelemetryUpdate(callback) {
    this.subscribers.add(callback);
    // Immediately emit last known payload if available
    if (this.lastPayload) callback(this.lastPayload);
    return () => this.subscribers.delete(callback);
  }

  onNewEvent(callback) {
    this.eventSubscribers.add(callback);
    return () => this.eventSubscribers.delete(callback);
  }

  async fetchTelemetry() {
    // Prevent overlapping polling requests
    if (this.isFetching) {
      return;
    }

    this.isFetching = true;
    try {
      const response = await fetch(`${BACKEND_URL}/metrics/adaptive`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      this.setConnected(true);

      // ── Map backend response to dashboard shape ──────────────────────
      const totalWorkers = (data.infraMetrics?.totalWorkers && Number(data.infraMetrics.totalWorkers) > 0)
        ? Number(data.infraMetrics.totalWorkers)
        : 8;

      const infraMetrics = {
        // Queue depths (real)
        queueT1: data.infraMetrics?.queueT1 ?? 0,
        queueT2: data.infraMetrics?.queueT2 ?? 0,
        queueT3: data.infraMetrics?.queueT3 ?? 0,
        // Latency
        latT1: data.infraMetrics?.latT1 ?? 0,
        latT2: data.infraMetrics?.latT2 ?? 0,
        latT3: data.infraMetrics?.latT3 ?? 0,
        // Worker allocation → convert count to % of pool for the progress bars
        w1: Math.round(((data.infraMetrics?.w1 ?? 0) / totalWorkers) * 100),
        w2: Math.round(((data.infraMetrics?.w2 ?? 0) / totalWorkers) * 100),
        w3: Math.round(((data.infraMetrics?.w3 ?? 0) / totalWorkers) * 100),
        w4: Math.round(((data.infraMetrics?.w4 ?? 0) / totalWorkers) * 100),
        // Raw worker counts
        w1Count: data.infraMetrics?.w1 ?? 0,
        w2Count: data.infraMetrics?.w2 ?? 0,
        w3Count: data.infraMetrics?.w3 ?? 0,
        w4Count: data.infraMetrics?.w4 ?? 0,
        totalWorkers,
      };

      // Pressure state from backend drives isSpikeMode
      const pressureState = data.metrics?.pressureState ?? 
        (data.metrics?.isSpikeMode ? 'HIGH' : 'NORMAL');

      // Consume the actual ingress rate from the new fields or fallback to ingress
      const actualIngressRate = Number(
        data.metrics?.actual_ingress_rate ??
        data.metrics?.ingress_rate ??
        data.metrics?.ingressRate ??
        data.actual_ingress_rate ??
        data.ingress_rate ??
        data.ingressRate ??
        data.metrics?.ingress ??
        0
      );

      const metrics = {
        queueSize:         data.metrics?.queueSize ?? 0,
        latency:           data.metrics?.latency ?? 0,
        workerLoad:        Math.round(data.metrics?.workerLoad ?? 0),
        processingCost:    data.metrics?.processingCost ?? 'LOW',
        isSpikeMode:       data.metrics?.isSpikeMode ?? false,
        ingress:           actualIngressRate,
        actualIngressRate: actualIngressRate,
        ingressRate:       actualIngressRate,
        throughput:        data.metrics?.throughput ?? 0,
        pressureState,
        pressureScore:     data.metrics?.pressureScore ?? 0,
      };

      const shedStats = {
        shed:              data.shedStats?.shed ?? 0,
        deferred:          data.shedStats?.deferred ?? 0,
        sampled:           data.shedStats?.sampled ?? 0,
        sampled_kept:      data.shedStats?.sampled_kept ?? 0,
        sampled_dropped:   data.shedStats?.sampled_dropped ?? 0,
        batched:           data.shedStats?.batched ?? 0,
        streamed:          data.shedStats?.streamed ?? 0,
        critical_protected: data.shedStats?.critical_protected ?? 0,
        ...(data.shedStats ?? {}),
      };

      const payload = {
        metrics,
        infraMetrics,
        shedStats,
        connected: this.connected,
        actualIngressRate,
        // Raw snapshot of the current recent-events window — type + tier only,
        // so subscribers can compute live distributions (e.g. event mix).
        recentEventTypes: (data.recentEvents ?? []).map(e => ({
          type: e.type ?? 'EVENT',
          tier: e.tier  ?? 'NORMAL',
        })),
      };
      this.lastPayload = payload;
      this.subscribers.forEach(cb => cb(payload));

      // ── Dispatch new events to stream table ─────────────────────────
      const recentEvents = data.recentEvents ?? [];
      recentEvents.forEach(evt => {
        if (!this.seenEvents.has(evt.id)) {
          this.seenEvents.add(evt.id);
          if (this.seenEvents.size > 2000) this.seenEvents.clear();

          // Normalise time field — backend stores ISO timestamp, dashboard expects HH:MM:SS.mmm
          const timeStr = evt.time
            ? (typeof evt.time === 'number'
                ? new Date(evt.time * 1000).toISOString().substring(11, 23)
                : String(evt.time).substring(11, 23))
            : new Date().toISOString().substring(11, 23);

          // Normalise tier label for dashboard badge colours
          const tierMap = { CRITICAL: 'Critical', NORMAL: 'Normal', BEST_EFFORT: 'Best Effort' };
          const statusMap = { STREAM: 'STREAM', BATCH: 'MICRO-BATCH', DEFER: 'DEFER', SAMPLE: 'SAMPLE', SHED: 'SHED' };

          this.eventSubscribers.forEach(cb => cb({
            time:   timeStr,
            id:     evt.id ?? ('evt_' + Math.random().toString(16).substring(2, 7)),
            type:   evt.type ?? 'EVENT',
            tier:   tierMap[evt.tier] ?? evt.tier,
            status: statusMap[evt.status] ?? evt.status,
            reason: evt.reason ?? '',
          }));
        }
      });

    } catch (err) {
      if (this.connected) {
        console.warn('[TelemetryService] Backend unreachable — retrying:', err.message);
      }
      this.setConnected(false);
    } finally {
      this.isFetching = false;
    }
  }

  startPolling(intervalMs = POLL_INTERVAL_MS) {
    this.stopPolling();
    this.isPolling = true;

    // Initial fetch immediately
    this.initialTimeout = setTimeout(() => {
      if (this.isPolling) {
        this.fetchTelemetry();
      }
    }, 100);

    // Then poll on interval
    this.pollTimer = setInterval(() => {
      if (this.isPolling) {
        this.fetchTelemetry();
      }
    }, intervalMs);
  }

  stopPolling() {
    this.isPolling = false;
    if (this.initialTimeout) {
      clearTimeout(this.initialTimeout);
      this.initialTimeout = null;
    }
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
}

export const telemetryService = new TelemetryService();
