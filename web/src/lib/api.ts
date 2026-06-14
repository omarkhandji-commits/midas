/*
 * Thin fetch wrapper for the MIDAS dashboard API.
 *
 * Reads the CSRF cookie set by /login (`midas_csrf`) and forwards it as the
 * X-MIDAS-CSRF header on every state-changing request — same double-submit
 * pattern the previous vanilla-JS client used. Same-origin only (loopback).
 */

const CSRF_COOKIE = "midas_csrf";
const CSRF_HEADER = "X-MIDAS-CSRF";

function readCsrf(): string {
  const match = document.cookie
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(`${CSRF_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : "";
}

export class ApiError extends Error {
  constructor(public status: number, public body: unknown, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const init: RequestInit = { method, headers, credentials: "same-origin" };

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  if (method !== "GET" && method !== "HEAD") {
    headers[CSRF_HEADER] = readCsrf();
  }

  const res = await fetch(path, init);
  const text = await res.text();
  const parsed = text ? safeJson(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, parsed, `${method} ${path} → ${res.status}`);
  }
  return parsed as T;
}

export type SseFrame = { event: string; data: unknown };

async function streamPost(
  path: string,
  body: unknown,
  onFrame: (frame: SseFrame) => void,
): Promise<void> {
  const headers: Record<string, string> = {
    Accept: "text/event-stream",
    "Content-Type": "application/json",
    [CSRF_HEADER]: readCsrf(),
  };
  const res = await fetch(path, {
    method: "POST",
    headers,
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new ApiError(res.status, safeJson(text), `POST ${path} → ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let reading = true;
  while (reading) {
    const { done, value } = await reader.read();
    if (done) {
      reading = false;
      continue;
    }
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseFrames(buffer);
    buffer = parsed.rest;
    parsed.frames.forEach(onFrame);
  }
  buffer += decoder.decode();
  const tail = parseSseFrames(buffer + "\n\n");
  tail.frames.forEach(onFrame);
}

export function parseSseFrames(input: string): { frames: SseFrame[]; rest: string } {
  const frames: SseFrame[] = [];
  let rest = input;
  let parsing = true;
  while (parsing) {
    const index = rest.indexOf("\n\n");
    if (index === -1) {
      parsing = false;
      continue;
    }
    const raw = rest.slice(0, index);
    rest = rest.slice(index + 2);
    if (!raw.trim()) continue;
    let event = "message";
    const dataLines: string[] = [];
    raw.split("\n").forEach((line) => {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    });
    frames.push({ event, data: safeJson(dataLines.join("\n")) });
  }
  return { frames, rest };
}

function safeJson(text: string): unknown {
  try { return JSON.parse(text); } catch { return text; }
}

export const api = {
  get:  <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
  streamPost,
};
