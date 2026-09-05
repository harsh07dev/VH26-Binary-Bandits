/*
  benchmark.js — API client for Benchmark & Comparison subsystem.
  Communicates with Machine 2 FastAPI backend at http://127.0.0.1:8000.
*/

const BACKEND_URL = 'http://127.0.0.1:8000';

/**
 * Fetch available benchmark scenarios and preset profiles.
 * @returns {Promise<{scenarios: Array<object>}>}
 */
export async function fetchBenchmarkScenarios() {
  const res = await fetch(`${BACKEND_URL}/benchmark/scenarios`);
  if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch scenarios`);
  return res.json();
}

/**
 * Run a benchmark execution.
 * @param {object} params
 * @param {string} [params.scenario="FLASH_SALE"]
 * @param {string} [params.mode="both"]
 * @param {number} [params.total_events]
 * @param {number} [params.target_rate]
 * @param {number} [params.seed]
 * @param {object} [params.distribution]
 * @param {boolean} [params.fast_simulation=true]
 * @returns {Promise<object>} Normalized comparison result JSON
 */
export async function runBenchmark({
  scenario = 'FLASH_SALE',
  mode = 'both',
  total_events,
  target_rate,
  seed = 42,
  distribution,
  fast_simulation = true,
} = {}) {
  const body = {
    scenario,
    mode,
    total_events: total_events ? Number(total_events) : undefined,
    target_rate: target_rate ? Number(target_rate) : undefined,
    seed: seed ? Number(seed) : 42,
    distribution,
    fast_simulation,
  };

  const res = await fetch(`${BACKEND_URL}/benchmark/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errText}`);
  }
  return res.json();
}

/**
 * Fetch historical benchmark runs.
 * @param {number} [limit=50]
 * @returns {Promise<{count: number, benchmarks: Array<object>}>}
 */
export async function fetchBenchmarkHistory(limit = 50) {
  const res = await fetch(`${BACKEND_URL}/benchmark/history?limit=${limit}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch history`);
  return res.json();
}

/**
 * Fetch complete benchmark result by ID.
 * @param {string} benchmarkId
 * @returns {Promise<object>}
 */
export async function fetchBenchmarkById(benchmarkId) {
  const res = await fetch(`${BACKEND_URL}/benchmark/results/${encodeURIComponent(benchmarkId)}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}: Benchmark not found`);
  return res.json();
}
