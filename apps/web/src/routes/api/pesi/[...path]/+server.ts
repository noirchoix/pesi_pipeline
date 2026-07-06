import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const DEFAULT_BACKEND_BASE_URL = 'http://localhost:8000/api/v1';

const HOP_BY_HOP_RESPONSE_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'content-encoding',
  'content-length'
]);

function backendBaseUrl(): string {
  return (
    env.PESI_BACKEND_API_BASE_URL ||
    env.PESI_INTERNAL_API_BASE_URL ||
    env.PESI_API_BASE_URL ||
    DEFAULT_BACKEND_BASE_URL
  ).replace(/\/$/, '');
}

function backendApiKey(request: Request): string {
  return env.PESI_API_KEY || request.headers.get('x-api-key') || '';
}

function targetUrl(path: string | undefined, sourceUrl: URL): URL {
  const cleanPath = (path ?? '').replace(/^\/+/, '');
  const target = new URL(`${backendBaseUrl()}/${cleanPath}`);
  target.search = sourceUrl.search;
  return target;
}

function responseHeaders(source: Headers): Headers {
  const headers = new Headers();
  for (const [key, value] of source.entries()) {
    if (!HOP_BY_HOP_RESPONSE_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  }
  return headers;
}

const proxy: RequestHandler = async ({ request, params, url, fetch }) => {
  const method = request.method.toUpperCase();
  const headers = new Headers();
  const accept = request.headers.get('accept');
  const contentType = request.headers.get('content-type');
  const apiKey = backendApiKey(request);

  if (accept) headers.set('accept', accept);
  if (apiKey) headers.set('x-api-key', apiKey);

  let body: ArrayBuffer | undefined;
  if (method !== 'GET' && method !== 'HEAD') {
    body = await request.arrayBuffer();
    if (body.byteLength > 0 && contentType) headers.set('content-type', contentType);
  }

  const upstream = await fetch(targetUrl(params.path, url), {
    method,
    headers,
    body: body && body.byteLength > 0 ? body : undefined
  });

  return new Response(await upstream.arrayBuffer(), {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders(upstream.headers)
  });
};

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
