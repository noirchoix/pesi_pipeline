import type {
  AnalysisProgress,
  Explanation,
  Gate,
  GateSummary,
  InferenceOptions,
  InferenceResults,
  ReadableReport,
  RunRecord,
  TableResponse
} from './types';

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
  if (typeof payload === 'object' && payload && 'message' in payload) return String((payload as { message: unknown }).message);
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
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!res.ok) throw new ApiError(readErrorMessage(payload, res.status), res.status, payload);
  return payload as T;
}

export function activeRunId(): string {
  if (typeof localStorage === 'undefined') return '';
  return localStorage.getItem('pesi.activeRunId') ?? '';
}

export function rememberRun(runId: string, scenario?: unknown): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem('pesi.activeRunId', runId);
  if (scenario) localStorage.setItem('pesi.scenario', JSON.stringify(scenario));
}

export function rememberedScenario(): Record<string, string> {
  if (typeof localStorage === 'undefined') return {};
  try { return JSON.parse(localStorage.getItem('pesi.scenario') ?? '{}'); } catch { return {}; }
}

export const api = {
  health: () => apiFetch<{ status: string; service: string; version: string }>('/health'),

  inferenceOptions: () => apiFetch<InferenceOptions>('/inference/options'),
  startAnalysis: (body: unknown) => apiFetch<{ status: string; analysis_id: string; run: RunRecord; progress_url: string; results_url: string }>('/inference/analyses', { method: 'POST', body: JSON.stringify(body) }),
  analysisProgress: (runId: string) => apiFetch<AnalysisProgress>(`/inference/analyses/${runId}/progress`),
  inferenceResults: (runId?: string, limit = 40) => apiFetch<InferenceResults>('/inference/results', {}, { run_id: runId || undefined, limit }),
  explainRecommendation: (body: unknown) => apiFetch<Explanation>('/inference/explain/recommendation', { method: 'POST', body: JSON.stringify(body) }),
  explainTarget: (body: unknown) => apiFetch<Explanation>('/inference/explain/target', { method: 'POST', body: JSON.stringify(body) }),
  inferenceReport: (body: unknown) => apiFetch<ReadableReport>('/inference/reports', { method: 'POST', body: JSON.stringify(body) }),

  launchRun: (body: unknown) => apiFetch<RunRecord>('/runs', { method: 'POST', body: JSON.stringify(body) }),
  runs: () => apiFetch<{ status: string; runs: RunRecord[] }>('/runs'),
  run: (id: string) => apiFetch<RunRecord>(`/runs/${id}`),
  logs: (id: string) => apiFetch<{ status: string; lines: string[]; total_lines: number }>(`/runs/${id}/logs`, {}, { tail: 1000 }),
  artifacts: (id: string) => apiFetch<{ status: string; files: Array<Record<string, unknown>> }>(`/runs/${id}/artifacts`),
  kg: () => apiFetch<Record<string, unknown>>('/results/kg-summary'),
  aim2Summary: () => apiFetch<Record<string, unknown>>('/results/aim2'),
  aim2Signatures: (params?: QueryParams) => apiFetch<TableResponse>('/results/aim2-signatures', {}, params),
  aim3: (params?: QueryParams) => apiFetch<TableResponse>('/results/aim3', {}, params),
  aim4: (params?: QueryParams) => apiFetch<TableResponse>('/results/aim4', {}, params),
  synergy: (params?: QueryParams) => apiFetch<TableResponse>('/results/synergy', {}, params),
  scenario: (params?: QueryParams) => apiFetch<TableResponse>('/results/scenario-selectivity', {}, params),
  compoundPool: (params?: QueryParams) => apiFetch<TableResponse>('/results/compound-pool', {}, params),
  benchmarkSummary: () => apiFetch<{ status: string; production_gate_summary: GateSummary; aim4_diversity_summary: Record<string, number> }>('/benchmarks/summary'),
  benchmarkGates: () => apiFetch<{ status: string; gates: Gate[]; summary: GateSummary }>('/benchmarks/gates'),
  benchmarkLeaderboard: () => apiFetch<TableResponse>('/benchmarks/leaderboard')
};
