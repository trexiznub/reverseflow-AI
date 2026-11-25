"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getUserId } from "./session";

// An empty NEXT_PUBLIC_API_URL means "same origin": the website's own server
// forwards /api to the backend (see BACKEND_URL in next.config.mjs).
const RAW = process.env.NEXT_PUBLIC_API_URL;
export const API = RAW === undefined ? "http://localhost:8040" : RAW.replace(/\/$/, "");
/** True when the backend is a hosted service (for example Render), not a local or same-origin process. */
export const IS_HOSTED = API !== "" && !/localhost|127\.0\.0\.1/.test(API);

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "X-User-Id": getUserId(), ...(init.headers as any) };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${API}/api${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Cannot reach the REVERSEFLOW API. Is the backend running on " + (API || "this server") + "?");
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new ApiError(res.status, msg);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export const post = <T = any>(path: string, body?: any) => api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T = any>(path: string, body?: any) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });

/** Data hook with loading / error / reload and optional polling. */
export function useApi<T = any>(path: string | null, opts: { poll?: number; deps?: any[] } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const alive = useRef(true);

  const load = useCallback(async (silent = false) => {
    if (!path) return;
    if (!silent) setLoading(true);
    try {
      const d = await api<T>(path);
      if (alive.current) { setData(d); setError(null); }
    } catch (e: any) {
      if (alive.current) setError(e);
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...(opts.deps || [])]);

  useEffect(() => {
    alive.current = true;
    load();
    let t: any;
    if (opts.poll) t = setInterval(() => load(true), opts.poll);
    const onUser = () => load();
    window.addEventListener("rf-user-changed", onUser);
    return () => { alive.current = false; clearInterval(t); window.removeEventListener("rf-user-changed", onUser); };
  }, [load, opts.poll]);

  return { data, error, loading, reload: load, setData };
}
