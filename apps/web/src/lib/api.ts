import type { Aim3Row, Aim4Row, Gate, GateSummary, RunRecord, TableResponse } from './types';

/*
  Browser calls must stay same-origin during local/Vite use.

  Previous version called http://localhost:8000/api/v1 directly from the browser.
  When Vite is opened as http://172.18.0.1:5173, that becomes a cross-origin
  request and fails CORS before the FastAPI response can be used.

  Default path therefore goes through the SvelteKit proxy route:
    /api/pesi/* -> http://localhost:8000/api/v1/*

  Direct browser-to-FastAPI mode remains available only when explicitly enabled:
    VITE_PESI_DIRECT_BACKEND=true
    VITE_PESI_API_BASE_URL=http://localhost:8000/api/v1
*/
const DIRECT_BACKEND = import.meta.env.VITE_PESI_DIRECT_BACKEND === 'true';
const CONFIGURED_BASE_URL = import.meta.env.VITE_PESI_API_BASE_URL as string | undefined;
const BASE_URL = DIRECT_BACKEND && CONFIGURED_BASE_URL ? CONFIGURED_BASE_URL.replace(/\/$/, '') : '/api/pesi';
const API_KEY = import.meta.env.VITE_PESI_API_KEY ?? '';

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

export type QueryParams = Record<string, string | number | boolean | null | undefined>;

function makeUrl(path: string, params?: QueryParams): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const base = path.startsWith('http') ? path : `${BASE_URL}${cleanPath}`;
  const url = new URL(base, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
  }
  return url.toString();
}

function readErrorMessage(payload: unknown, status: number): string {
  if (typeof payload === 'object' && payload && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    return typeof detail === 'string' ? detail : JSON.stringify(detail);
  }
  if (typeof payload === 'object' && payload && 'message' in payload) {
    return String((payload as { message: unknown }).message);
  }
  if (typeof payload === 'string' && payload.trim()) return payload;
  return `Request failed with ${status}`;
}

async function apiFetch<T>(path: string, options: RequestInit = {}, params?: QueryParams): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (API_KEY) headers.set('X-API-Key', API_KEY);

  const res = await fetch(makeUrl(path, params), { ...options, headers });
  const text = await res.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!res.ok) throw new ApiError(readErrorMessage(payload, res.status), res.status, payload);
  return payload as T;
}

export function withAbort<T>(loader: (signal: AbortSignal) => Promise<T>): { promise: Promise<T>; cancel: () => void } {
  const controller = new AbortController();
  return { promise: loader(controller.signal), cancel: () => controller.abort() };
}

export const api = {
  health: () => apiFetch<{ status: string; service: string; version: string }>('/health'),
  launchRun: (body: unknown) => apiFetch<RunRecord>('/runs', { method: 'POST', body: JSON.stringify(body) }),
  runs: () => apiFetch<{ status: string; runs: RunRecord[] }>('/runs'),
  run: (id: string) => apiFetch<RunRecord>(`/runs/${id}`),
  logs: (id: string) => apiFetch<{ status: string; lines: string[]; total_lines: number }>(`/runs/${id}/logs`, {}, { tail: 1000 }),
  artifacts: (id: string) => apiFetch<{ status: string; files: Array<Record<string, unknown>> }>(`/runs/${id}/artifacts`),
  kg: () => apiFetch<Record<string, unknown>>('/results/kg-summary'),
  aim2Summary: () => apiFetch<Record<string, unknown>>('/results/aim2'),
  aim2Signatures: (params?: QueryParams) => apiFetch<TableResponse>('/results/aim2-signatures', {}, params),
  aim3: (params?: QueryParams) => apiFetch<TableResponse<Aim3Row>>('/results/aim3', {}, params),
  aim4: (params?: QueryParams) => apiFetch<TableResponse<Aim4Row>>('/results/aim4', {}, params),
  synergy: (params?: QueryParams) => apiFetch<TableResponse>('/results/synergy', {}, params),
  scenario: (params?: QueryParams) => apiFetch<TableResponse>('/results/scenario-selectivity', {}, params),
  compoundPool: (params?: QueryParams) => apiFetch<TableResponse>('/results/compound-pool', {}, params),
  benchmarkSummary: () => apiFetch<{ status: string; production_gate_summary: GateSummary; aim4_diversity_summary: Record<string, number> }>('/benchmarks/summary'),
  benchmarkGates: () => apiFetch<{ status: string; gates: Gate[]; summary: GateSummary }>('/benchmarks/gates'),
  benchmarkLeaderboard: () => apiFetch<TableResponse>('/benchmarks/leaderboard'),
  interpretRun: () => apiFetch<Record<string, unknown>>('/interpret/run', { method: 'POST', body: JSON.stringify({}) }),
  interpretIntervention: (body: unknown) => apiFetch<Record<string, unknown>>('/interpret/intervention', { method: 'POST', body: JSON.stringify(body) }),
  interpretTarget: (body: unknown) => apiFetch<Record<string, unknown>>('/interpret/target', { method: 'POST', body: JSON.stringify(body) }),
  report: () => apiFetch<Record<string, unknown>>('/reports', { method: 'POST', body: JSON.stringify({ format: 'json' }) })
};
