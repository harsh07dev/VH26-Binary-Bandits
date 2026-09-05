/* 
  Real HTTP connection to Machine 2 (PulseFlow Ingestion Pipeline).
  Sends synthetic events and spike bursts to /events/batch.
*/

const BACKEND_URL = 'http://localhost:8000';

const EVENT_TYPES = [
  'ORDER',
  'PAYMENT',
  'CART_ADD',
  'INVENTORY_UPDATE',
  'CLICK',
  'PAGE_VIEW',
  'LOG',
];

function createEvent(idx) {
  const type = EVENT_TYPES[Math.floor(Math.random() * EVENT_TYPES.length)];
  return {
    event_id: `tp-${Date.now()}-${idx}-${Math.random().toString(36).substring(2, 7)}`,
    event_type: type,
    timestamp: Date.now() / 1000,
    payload: { source: 'techpulse-ui', sequence: idx },
  };
}

class TelemetryClient {
  constructor() {
    this.isConnected = true;
    this.latencyMs = 1.2;
    this.spikeInterval = null;
    this.burstHistory = [];
    this.listeners = new Set();
    this.pingInterval = null;
    this.startHealthCheck();
  }

  startHealthCheck() {
    const check = async () => {
      const start = performance.now();
      try {
        const res = await fetch(`${BACKEND_URL}/health`, { method: 'GET' });
        this.isConnected = res.ok;
        this.latencyMs = Math.max(0.5, Number((performance.now() - start).toFixed(1)));
      } catch {
        this.isConnected = false;
      }
      this.notify();
    };
    check();
    this.pingInterval = setInterval(check, 4000);
  }

  subscribe(cb) {
    this.listeners.add(cb);
    cb({ isConnected: this.isConnected, latencyMs: this.latencyMs, history: this.burstHistory });
    return () => this.listeners.delete(cb);
  }

  notify() {
    this.listeners.forEach(cb => {
      try {
        cb({ isConnected: this.isConnected, latencyMs: this.latencyMs, history: this.burstHistory });
      } catch (err) {
        console.error('[TechPulse] telemetry listener error:', err);
      }
    });
  }

  async sendBatch(count = 50) {
    const events = Array.from({ length: count }, (_, i) => createEvent(i));
    const start = performance.now();
    try {
      const res = await fetch(`${BACKEND_URL}/events/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events }),
      });
      const transitMs = Number((performance.now() - start).toFixed(1));
      this.latencyMs = transitMs;
      return { ok: res.ok, status: res.status, transitMs };
    } catch (err) {
      console.warn('[TechPulse] Failed to send event batch to backend:', err.message);
      return { ok: false, status: 0, transitMs: 0 };
    }
  }

  /**
   * Triggers a surge/spike in the backend processing engine.
   * @param {number} level - The surge multiplier/level selected by the user.
   * @param {number} expectedEvents - Expected event count.
   */
  triggerSpike(level = 5, expectedEvents = 200, label = 'Burst Spikes') {
    console.log(`[TechPulse] Injecting SPIKE to Machine 2 (Level: ${level}, Events: ${expectedEvents})...`);
    this.resetSpike();

    const batchSize = Math.max(100, Math.min(500, Math.round((expectedEvents || 1000) / 20)));
    const timestamp = new Date().toLocaleTimeString([], { hour12: false });
    
    // Send immediate first burst
    this.sendBatch(batchSize).then(result => {
      const burstEntry = {
        id: `burst-${Date.now()}`,
        timestamp,
        level,
        label,
        events: expectedEvents,
        target: `${BACKEND_URL}/events/batch`,
        status: result.ok ? 'HTTP 200 OK' : 'FAILED',
        isOk: result.ok,
        latency: result.transitMs || this.latencyMs,
      };
      this.burstHistory = [burstEntry, ...this.burstHistory].slice(0, 10);
      this.notify();
    });

    // Send rapid follow-up bursts over the next 3-4 seconds to generate sustained pressure
    let burstsSent = 0;
    const maxBursts = Math.min(30, Math.max(10, Number(level) * 4));
    this.spikeInterval = setInterval(() => {
      burstsSent++;
      this.sendBatch(batchSize);
      if (burstsSent >= maxBursts) {
        this.resetSpike();
      }
    }, 100);
  }

  /**
   * Resets the surge in the backend processing engine.
   */
  resetSpike() {
    if (this.spikeInterval) {
      clearInterval(this.spikeInterval);
      this.spikeInterval = null;
    }
  }
}

export const telemetryClient = new TelemetryClient();


