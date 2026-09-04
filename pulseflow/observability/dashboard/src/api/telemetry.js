/* 
  Simulated WebSocket/API connection to Machine 1 (PulseFlow Generator).
  This abstracts the simulation logic out of the UI, preparing for a real backend connection.
*/

const eventMix = [
  { type: 'PAYMENT', tier: 'Critical', pct: 15, isCritical: true },
  { type: 'ORDER', tier: 'Critical', pct: 25, isCritical: true },
  { type: 'INVENTORY', tier: 'Normal', pct: 15, isCritical: false },
  { type: 'ACTIVITY / VIEWS', tier: 'Best Effort', pct: 30, isCritical: false },
  { type: 'LOGS / TELEMETRY', tier: 'Best Effort', pct: 15, isCritical: false },
]

class TelemetryService {
  constructor() {
    this.subscribers = new Set();
    this.eventSubscribers = new Set();
    this.isSpikeMode = false;
    this.shedStats = { shed: 1519, deferred: 3483 };
    
    this.startSimulation();
  }

  onTelemetryUpdate(callback) {
    this.subscribers.add(callback);
    return () => this.subscribers.delete(callback);
  }

  onNewEvent(callback) {
    this.eventSubscribers.add(callback);
    return () => this.eventSubscribers.delete(callback);
  }

  _notifyTelemetry() {
    const metrics = this.isSpikeMode 
      ? { queueSize: 12480, latency: 85, workerLoad: 92, processingCost: 'HIGH', isSpikeMode: true, ingress: 20000, throughput: 320 }
      : { queueSize: 1140, latency: 12, workerLoad: 45, processingCost: 'LOW', isSpikeMode: false, ingress: 1000, throughput: 1000 };
      
    const infraMetrics = this.isSpikeMode 
      ? { queueT1: 120, latT1: 4, queueT2: 2840, latT2: 38, queueT3: 9520, latT3: 210, w1: 82, w2: 76, w3: 71, w4: 68 }
      : { queueT1: 24, latT1: 2, queueT2: 45, latT2: 3, queueT3: 115, latT3: 6, w1: 42, w2: 38, w3: 40, w4: 35 };

    const payload = { metrics, infraMetrics, shedStats: this.shedStats };
    this.subscribers.forEach(cb => cb(payload));
  }

  _getProcessingDecision(priority, queueSize, latency, workerLoad, dataSize, processingCost) {
    const isSpike = queueSize > 10000 || latency > 50 || workerLoad > 85;
    if (!isSpike) return 'STREAM';
    
    if (priority === 'Critical') return 'STREAM';
    if (priority === 'Normal') return 'MICRO-BATCH';
    if (priority === 'Best Effort') {
      if (processingCost === 'HIGH' && dataSize > 500) return 'SAMPLE';
      return 'DEFER';
    }
    return 'DEFER';
  }

  _generateEvent() {
    const randomMix = eventMix[Math.floor(Math.random() * eventMix.length)];
    const dataSize = Math.random() * 1000;
    
    const decision = this._getProcessingDecision(
      randomMix.tier, 
      this.isSpikeMode ? 12480 : 1140, 
      this.isSpikeMode ? 85 : 12, 
      this.isSpikeMode ? 92 : 45, 
      dataSize, 
      this.isSpikeMode ? 'HIGH' : 'LOW'
    );
    
    const newEvt = {
      time: new Date().toISOString().substring(11, 23),
      id: 'evt_' + Math.random().toString(16).substring(2, 7),
      type: randomMix.type,
      tier: randomMix.tier,
      status: decision,
    };
    
    this.eventSubscribers.forEach(cb => cb(newEvt));
  }

  startSimulation() {
    setInterval(() => {
      this.isSpikeMode = !this.isSpikeMode;
      this._notifyTelemetry();
    }, 12000);

    setInterval(() => {
      const count = Math.floor(Math.random() * 3) + 1;
      for(let i=0; i<count; i++) {
        this._generateEvent();
      }

      if (this.isSpikeMode) {
        this.shedStats.shed += Math.floor(Math.random() * 12);
        this.shedStats.deferred += Math.floor(Math.random() * 30);
        this._notifyTelemetry();
      }
    }, 1200);

    setTimeout(() => this._notifyTelemetry(), 100);
  }
}

export const telemetryService = new TelemetryService();
