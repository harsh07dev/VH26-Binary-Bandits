/* 
  TechPulse Control & Telemetry Client (Machine 1)
  
  Interacts with the Authoritative Python Traffic Generator on port 8001.
  Does NOT generate duplicate traffic in the browser.
  Fetches live metrics, controls preset spikes, custom spikes, and custom event runs.
*/

const TECHPULSE_API_URL = import.meta.env.VITE_TECHPULSE_API_URL || 'http://localhost:8001';
const PULSEFLOW_BASE_URL = import.meta.env.VITE_PULSEFLOW_BASE_URL || 'http://localhost:8000';

class TelemetryClient {
  constructor() {
    this.generatorConnected = false;
    this.pulseflowConnected = false;
    this.latencyMs = 1.2;
    this.burstHistory = [];
    this.listeners = new Set();
    this.pollInterval = null;

    // Current authoritative generator state snapshot
    this.currentState = {
      running: true,
      state: 'BASELINE',
      baselineRate: 100,
      currentTargetRate: 100,
      measuredRate: 100,
      multiplier: 1.0,
      spikeMode: 'NONE',
      spikeLabel: 'Steady Baseline',
      remainingSeconds: null,
      eventsTarget: null,
      eventsSpiked: 0,
      eventsGenerated: 0,
      eventsAttempted: 0,
      eventsDelivered: 0,
      eventsFailed: 0,
      batchesGenerated: 0,
      batchesDelivered: 0,
      errors: 0,
      elapsedTime: 0,
      pulseflowUrl: PULSEFLOW_BASE_URL,
      pulseflowConnected: true,
      pulseflowLatencyMs: 1.2,
      distribution: {
        CLICK: 30,
        PAGE_VIEW: 25,
        LOG: 15,
        CART_ADD: 10,
        INVENTORY_UPDATE: 10,
        ORDER: 5,
        PAYMENT: 5,
      },
      distributionPreset: 'standard',
      distributionLabel: 'Standard Browsing',
    };

    this.startPolling();
  }

  startPolling() {
    const poll = async () => {
      try {
        const start = performance.now();
        const res = await fetch(`${TECHPULSE_API_URL}/metrics`, {
          method: 'GET',
          headers: { 'Accept': 'application/json' },
        });

        if (res.ok) {
          const data = await res.json();
          this.generatorConnected = true;
          this.pulseflowConnected = Boolean(data.pulseflow_connected);
          this.latencyMs = data.pulseflow_latency_ms || Math.max(0.5, Number((performance.now() - start).toFixed(1)));

          this.currentState = {
            running: data.running,
            state: data.state || 'BASELINE',
            baselineRate: data.baseline_rate || 100,
            currentTargetRate: data.current_target_rate || 100,
            measuredRate: data.measured_rate !== undefined ? data.measured_rate : data.current_target_rate,
            multiplier: data.multiplier || 1.0,
            spikeMode: data.spike_mode || 'NONE',
            spikeLabel: data.spike_label || 'Steady Baseline',
            remainingSeconds: data.remaining_seconds,
            eventsTarget: data.events_target,
            eventsSpiked: data.events_spiked || 0,
            eventsGenerated: data.events_generated || 0,
            eventsAttempted: data.events_attempted || 0,
            eventsDelivered: data.events_delivered || 0,
            eventsFailed: data.events_failed || 0,
            batchesGenerated: data.batches_generated || 0,
            batchesDelivered: data.batches_delivered || 0,
            errors: data.errors || 0,
            elapsedTime: data.elapsed_time || 0,
            pulseflowUrl: data.pulseflow_url || PULSEFLOW_BASE_URL,
            pulseflowConnected: this.pulseflowConnected,
            pulseflowLatencyMs: this.latencyMs,
            distribution: data.distribution || this.currentState.distribution,
            distributionPreset: data.distribution_preset || this.currentState.distributionPreset || 'custom',
            distributionLabel: data.distribution_label || this.currentState.distributionLabel || 'Custom Workload Mix',
          };
        } else {
          this.generatorConnected = false;
        }
      } catch {
        this.generatorConnected = false;
      }
      this.notify();
    };

    poll();
    this.pollInterval = setInterval(poll, 600);
  }

  subscribe(cb) {
    this.listeners.add(cb);
    cb(this.getPayload());
    return () => this.listeners.delete(cb);
  }

  getPayload() {
    return {
      generatorConnected: this.generatorConnected,
      isConnected: this.pulseflowConnected,
      pulseflowConnected: this.pulseflowConnected,
      latencyMs: this.latencyMs,
      history: this.burstHistory,
      ...this.currentState,
    };
  }

  notify() {
    const payload = this.getPayload();
    this.listeners.forEach(cb => {
      try {
        cb(payload);
      } catch (err) {
        console.error('[TechPulse] telemetry listener error:', err);
      }
    });
  }

  addAuditEntry(label, targetRate, events, status = 'HTTP 200 OK', isOk = true) {
    const timestamp = new Date().toLocaleTimeString([], { hour12: false });
    const entry = {
      id: `burst-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
      timestamp,
      label,
      targetRate,
      events,
      target: `${PULSEFLOW_BASE_URL}/events/batch`,
      status,
      isOk,
      latency: this.latencyMs,
    };
    this.burstHistory = [entry, ...this.burstHistory].slice(0, 12);
    this.notify();
  }

  /**
   * Apply a preset multiplier spike on Machine 1 generator.
   * e.g. 1x (100 ev/s), 5x (500 ev/s), 10x (1000 ev/s), 20x (2000 ev/s)
   */
  async triggerPreset(multiplier, duration = 20) {
    console.log(`[TechPulse] Sending preset spike ${multiplier}x for ${duration}s to Generator API...`);
    try {
      const res = await fetch(`${TECHPULSE_API_URL}/control/preset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ multiplier, duration }),
      });
      const data = await res.json();
      if (res.ok) {
        this.addAuditEntry(
          `+${multiplier}× Preset Surge`,
          data.target_rate || multiplier * 100,
          `~${Math.round((data.target_rate || multiplier * 100) * duration)}`,
          'HTTP 200 OK',
          true
        );
        return { ok: true, data };
      }
      return { ok: false, error: data.detail };
    } catch (err) {
      console.warn('[TechPulse] Preset spike command failed:', err.message);
      this.addAuditEntry(`+${multiplier}× Preset Surge`, multiplier * 100, '--', 'FAILED', false);
      return { ok: false, error: err.message };
    }
  }

  /**
   * Apply an arbitrary custom target rate & duration.
   */
  async triggerCustomSpike(targetRate, duration) {
    console.log(`[TechPulse] Sending custom spike (${targetRate} ev/s, ${duration}s) to Generator API...`);
    try {
      const res = await fetch(`${TECHPULSE_API_URL}/control/custom-spike`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_rate: Number(targetRate), duration: Number(duration) }),
      });
      const data = await res.json();
      if (res.ok) {
        this.addAuditEntry(
          `Custom Surge (${Number(targetRate).toLocaleString()} ev/s)`,
          targetRate,
          `~${Math.round(targetRate * duration)}`,
          'HTTP 200 OK',
          true
        );
        return { ok: true, data };
      }
      return { ok: false, error: data.detail };
    } catch (err) {
      console.warn('[TechPulse] Custom spike command failed:', err.message);
      this.addAuditEntry(`Custom Surge (${targetRate} ev/s)`, targetRate, '--', 'FAILED', false);
      return { ok: false, error: err.message };
    }
  }

  /**
   * Update synthetic event mix and trigger rate spike simultaneously.
   */
  async triggerMixSpike(targetRate, duration, distribution, presetId = 'custom', presetLabel = 'Custom Workload Mix') {
    console.log(`[TechPulse] Triggering mix surge (${targetRate} ev/s, ${duration}s, preset: ${presetId})...`);
    try {
      const res = await fetch(`${TECHPULSE_API_URL}/control/custom-mix-spike`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_rate: Number(targetRate),
          duration: Number(duration),
          distribution,
          preset_id: presetId,
          preset_label: presetLabel,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        if (data.distribution) {
          this.currentState.distribution = data.distribution;
        }
        this.currentState.distributionPreset = data.distribution_preset || presetId;
        this.currentState.distributionLabel = data.distribution_label || presetLabel;
        this.addAuditEntry(
          `Mix Surge (${Number(targetRate).toLocaleString()} ev/s [${presetLabel}])`,
          targetRate,
          `~${Math.round(targetRate * duration)}`,
          'HTTP 200 OK',
          true
        );
        this.notify();
        return { ok: true, data };
      }
      return { ok: false, error: data.detail };
    } catch (err) {
      console.warn('[TechPulse] Mix surge command failed:', err.message);
      this.addAuditEntry(`Mix Surge (${targetRate} ev/s)`, targetRate, '--', 'FAILED', false);
      return { ok: false, error: err.message };
    }
  }

  /**
   * Apply an exact event count benchmark run.
   */
  async triggerCustomRun(totalEvents, maxRate) {
    console.log(`[TechPulse] Sending custom event run (${totalEvents} events @ max ${maxRate} ev/s)...`);
    try {
      const res = await fetch(`${TECHPULSE_API_URL}/control/custom-run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ total_events: Number(totalEvents), max_rate: Number(maxRate) }),
      });
      const data = await res.json();
      if (res.ok) {
        this.addAuditEntry(
          `Custom Run (${Number(totalEvents).toLocaleString()} ev)`,
          maxRate,
          totalEvents,
          'HTTP 200 OK',
          true
        );
        return { ok: true, data };
      }
      return { ok: false, error: data.detail };
    } catch (err) {
      console.warn('[TechPulse] Custom run command failed:', err.message);
      this.addAuditEntry(`Custom Run (${totalEvents} ev)`, maxRate, totalEvents, 'FAILED', false);
      return { ok: false, error: err.message };
    }
  }

  /**
   * Cancel active spike and immediately recover to baseline (~100 ev/s).
   * NEVER drops to 0.
   */
  async recoverToBaseline() {
    console.log('[TechPulse] Sending recover to baseline command...');
    try {
      const res = await fetch(`${TECHPULSE_API_URL}/control/recover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (res.ok) {
        this.addAuditEntry('Recover to Baseline', 100, '--', 'RECOVERED (100 ev/s)', true);
        return { ok: true, data };
      }
      return { ok: false, error: data.detail };
    } catch (err) {
      console.warn('[TechPulse] Recover command failed:', err.message);
      return { ok: false, error: err.message };
    }
  }

  /**
   * Reset session: cancels active spike, resets multiplier = 1, restores baseline rate.
   */
  async resetSession() {
    console.log('[TechPulse] Sending reset session command...');
    try {
      const res = await fetch(`${TECHPULSE_API_URL}/control/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      this.burstHistory = [];
      this.addAuditEntry('Session Reset', 100, '--', 'RESET (100 ev/s)', true);
      return { ok: true, data };
    } catch (err) {
      console.warn('[TechPulse] Reset command failed:', err.message);
      return { ok: false, error: err.message };
    }
  }

  /**
   * Pause or resume the authoritative generator.
   */
  async togglePause(isCurrentlyPaused) {
    const endpoint = isCurrentlyPaused ? '/control/resume' : '/control/pause';
    try {
      const res = await fetch(`${TECHPULSE_API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      return { ok: res.ok, isRunning: data.running };
    } catch (err) {
      console.warn('[TechPulse] Toggle pause command failed:', err.message);
      return { ok: false, isRunning: !isCurrentlyPaused };
    }
  }

  /**
   * Update synthetic event mix distribution weights on the Python generator.
   */
  async updateDistribution(distribution, presetId = 'custom', presetLabel = 'Custom Workload Mix') {
    console.log('[TechPulse] Updating synthetic event distribution:', distribution, presetId, presetLabel);
    try {
      const res = await fetch(`${TECHPULSE_API_URL}/control/distribution`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          distribution,
          preset_id: presetId,
          preset_label: presetLabel,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        this.currentState.distribution = data.distribution || distribution;
        this.currentState.distributionPreset = data.distribution_preset || presetId;
        this.currentState.distributionLabel = data.distribution_label || presetLabel;
        this.addAuditEntry(`Event Mix: ${presetLabel}`, this.currentState.currentTargetRate, '--', 'MIX APPLIED', true);
        this.notify();
        return {
          ok: true,
          distribution: this.currentState.distribution,
          distributionPreset: this.currentState.distributionPreset,
          distributionLabel: this.currentState.distributionLabel,
        };
      }
      return { ok: false, error: data.detail };
    } catch (err) {
      console.warn('[TechPulse] Update distribution command failed:', err.message);
      return { ok: false, error: err.message };
    }
  }
}

export const telemetryClient = new TelemetryClient();
