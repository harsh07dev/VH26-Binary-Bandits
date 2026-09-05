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
    this.spikeInterval = null;
  }

  async sendBatch(count = 50) {
    const events = Array.from({ length: count }, (_, i) => createEvent(i));
    try {
      const res = await fetch(`${BACKEND_URL}/events/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ events }),
      });
      if (!res.ok) {
        console.warn(`[TechPulse] Ingest batch HTTP ${res.status}`);
      }
    } catch (err) {
      console.warn('[TechPulse] Failed to send event batch to backend:', err.message);
    }
  }

  /**
   * Triggers a surge/spike in the backend processing engine.
   * @param {number} level - The surge multiplier/level selected by the user.
   * @param {number} expectedEvents - Expected event count.
   */
  triggerSpike(level = 5, expectedEvents = 200) {
    console.log(`[TechPulse] Injecting SPIKE to Machine 2 (Level: ${level}, Events: ${expectedEvents})...`);
    this.resetSpike();

    const batchSize = Math.max(100, Math.min(500, Math.round((expectedEvents || 1000) / 20)));
    
    // Send immediate first burst
    this.sendBatch(batchSize);

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

