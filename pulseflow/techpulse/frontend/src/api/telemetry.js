/* 
  Simulated WebSocket/API connection to Machine 2 (PulseFlow Observability).
  This abstracts the API communication out of the UI, preparing for a real backend connection.
*/

class TelemetryClient {
  constructor() {
    this.isConnected = true; // Simulated connection state
  }

  /**
   * Triggers a surge/spike in the backend processing engine.
   * @param {number} level - The surge multiplier/level selected by the user.
   */
  triggerSpike(level, expectedEvents) {
    console.log(`[API MOCK] Emitting SPIKE event (Level: ${level}, Events: ${expectedEvents}) to Machine 2...`);
    // Future implementation:
    // if (this.ws.readyState === WebSocket.OPEN) {
    //   this.ws.send(JSON.stringify({ type: 'TRIGGER_SPIKE', payload: { level, expectedEvents } }));
    // }
  }

  /**
   * Resets the surge in the backend processing engine.
   */
  resetSpike() {
    console.log(`[API MOCK] Emitting RESET event to Machine 2...`);
    // Future implementation:
    // if (this.ws.readyState === WebSocket.OPEN) {
    //   this.ws.send(JSON.stringify({ type: 'RESET_SPIKE' }));
    // }
  }
}

export const telemetryClient = new TelemetryClient();
