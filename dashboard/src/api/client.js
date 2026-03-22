/**
 * API client for the ReAgent dashboard.
 *
 * Using live backend via HTTP.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

function getHeaders() {
  const headers = {
    'Content-Type': 'application/json',
  };
  const apiKey = localStorage.getItem('reagent_api_key');
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`;
  }
  return headers;
}

function buildQuery(params) {
  if (!params) return '';
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      query.append(key, value);
    }
  }
  const str = query.toString();
  return str ? `?${str}` : '';
}

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const response = await fetch(url, {
    headers: getHeaders(),
    ...options,
  });
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    const error = new Error(`API error ${response.status}: ${response.statusText}`);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

export function fetchRuns(params) {
  return request(`/api/v1/runs${buildQuery(params)}`);
}

export function fetchRun(runId) {
  return request(`/api/v1/runs/${runId}`);
}

export function fetchRunMetadata(runId) {
  return request(`/api/v1/runs/${runId}/metadata`);
}

export function fetchRunSteps(runId, params) {
  return request(`/api/v1/runs/${runId}/steps${buildQuery(params)}`);
}

export function fetchRunCount(params) {
  return request(`/api/v1/runs/count${buildQuery(params)}`);
}

export function deleteRun(runId) {
  return request(`/api/v1/runs/${runId}`, { method: 'DELETE' });
}

export function searchRuns(query, params) {
  return request(`/api/v1/search${buildQuery({ q: query, ...params })}`);
}

export function fetchFailures(params) {
  return request(`/api/v1/failures${buildQuery(params)}`);
}

export function fetchFailureStats(params) {
  return request(`/api/v1/failures/stats${buildQuery(params)}`);
}

export function fetchStats(params) {
  return request(`/api/v1/stats${buildQuery(params)}`);
}

export function fetchHealth() {
  return request('/health');
}
