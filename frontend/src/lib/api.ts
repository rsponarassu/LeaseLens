/**
 * Single entry point for everything the browser asks the FastAPI backend.
 *
 * Two non-negotiables:
 *  1. Every failure surfaces as `ApiError` carrying the server's own error code,
 *     so the UI can react to `session_expired` vs `rate_limited` instead of
 *     string-matching a message.
 *  2. The uploaded PDF never touches storage: it is streamed straight to
 *     `/analyze` and held in memory by the server for the life of the session.
 */

import type {
  AnalysisReport,
  AnalysisSummary,
  HealthResponse,
  RuleCatalogue,
  SampleLease,
} from "./types"

const RAW_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "")
export const API_ROOT = `${RAW_BASE}/api/v1`

/** Absolute URL for an API path, safe to use in <a download> or <iframe>. */
export function apiUrl(path: string): string {
  return `${API_ROOT}${path.startsWith("/") ? path : `/${path}`}`
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown> | null
  readonly requestId: string | null

  constructor(
    message: string,
    options: {
      code?: string
      status?: number
      details?: Record<string, unknown> | null
      requestId?: string | null
    } = {},
  ) {
    super(message)
    this.name = "ApiError"
    this.code = options.code ?? "unknown_error"
    this.status = options.status ?? 0
    this.details = options.details ?? null
    this.requestId = options.requestId ?? null
  }

  get isOffline(): boolean {
    return this.code === "network_error"
  }

  get isExpired(): boolean {
    return this.code === "session_expired"
  }
}

interface ErrorEnvelope {
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown> | null
    request_id?: string | null
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let payload: ErrorEnvelope | null = null
  try {
    payload = (await response.json()) as ErrorEnvelope
  } catch {
    payload = null
  }
  const body = payload?.error
  return new ApiError(body?.message ?? `Request failed with status ${response.status}.`, {
    code: body?.code ?? `http_${response.status}`,
    status: response.status,
    details: body?.details ?? null,
    requestId: body?.request_id ?? response.headers.get("x-request-id"),
  })
}

const OFFLINE_MESSAGE =
  "Can't reach the LeaseLens API. Check that the backend is running, then try again."

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 45_000): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      signal: init.signal ?? controller.signal,
      headers: { Accept: "application/json", ...(init.headers ?? {}) },
    })
    if (!response.ok) throw await toApiError(response)
    // DELETE returns 204 with an empty body; parsing it as JSON would throw.
    if (response.status === 204) return undefined as T
    const text = await response.text()
    return (text ? JSON.parse(text) : undefined) as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if ((error as Error)?.name === "AbortError") {
      throw new ApiError("The analysis took too long and was cancelled.", {
        code: "timeout",
      })
    }
    throw new ApiError(OFFLINE_MESSAGE, { code: "network_error" })
  } finally {
    window.clearTimeout(timer)
  }
}

async function requestBlob(
  path: string,
  init: RequestInit = {},
  timeoutMs = 60_000,
): Promise<Blob> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(apiUrl(path), { ...init, signal: controller.signal })
    if (!response.ok) throw await toApiError(response)
    return await response.blob()
  } catch (error) {
    if (error instanceof ApiError) throw error
    if ((error as Error)?.name === "AbortError") {
      throw new ApiError("Rendering the highlighted PDF timed out.", { code: "timeout" })
    }
    throw new ApiError(OFFLINE_MESSAGE, { code: "network_error" })
  } finally {
    window.clearTimeout(timer)
  }
}

/* -------------------------------------------------------------------------- */
/* Health, rules, samples                                                     */
/* -------------------------------------------------------------------------- */

export const getHealth = () => request<HealthResponse>("/health", {}, 8_000)

export const listRules = () => request<RuleCatalogue>("/rules")

export const listSamples = () => request<SampleLease[]>("/sample-leases", {}, 60_000)

export const getSample = (sampleId: string) =>
  request<SampleLease>(`/sample-leases/${encodeURIComponent(sampleId)}`, {}, 60_000)

export const samplePdfUrl = (sampleId: string) =>
  apiUrl(`/sample-leases/${encodeURIComponent(sampleId)}/pdf`)

/* -------------------------------------------------------------------------- */
/* Analysis                                                                   */
/* -------------------------------------------------------------------------- */

export interface AnalyzeOptions {
  useLlm?: boolean
  tenantName?: string
  landlordName?: string
  monthlyRentInr?: number
  onProgress?: (percent: number) => void
  signal?: AbortSignal
}

/**
 * Uploads and analyses a lease.
 *
 * Uses XMLHttpRequest rather than fetch because only XHR reports *upload*
 * progress, and a 15 MB scanned PDF over a phone connection needs a real
 * percentage bar, not a spinner.
 */
export function analyzeLease(file: File, options: AnalyzeOptions = {}): Promise<AnalysisReport> {
  const params = new URLSearchParams()
  if (options.useLlm === false) params.set("use_llm", "false")
  if (options.tenantName) params.set("tenant_name", options.tenantName)
  if (options.landlordName) params.set("landlord_name", options.landlordName)
  if (options.monthlyRentInr) params.set("monthly_rent_inr", String(options.monthlyRentInr))
  const query = params.toString()

  const form = new FormData()
  form.append("file", file, file.name)

  return new Promise<AnalysisReport>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", apiUrl(`/analyze${query ? `?${query}` : ""}`), true)
    xhr.responseType = "text"
    xhr.timeout = 240_000
    xhr.setRequestHeader("Accept", "application/json")

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && options.onProgress) {
        options.onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }

    xhr.onload = () => {
      let payload: unknown = null
      try {
        payload = JSON.parse(xhr.responseText)
      } catch {
        payload = null
      }
      if (xhr.status >= 200 && xhr.status < 300 && payload) {
        resolve(payload as AnalysisReport)
        return
      }
      const envelope = payload as ErrorEnvelope | null
      const body = envelope?.error
      reject(
        new ApiError(body?.message ?? `The server rejected this upload (${xhr.status}).`, {
          code: body?.code ?? `http_${xhr.status}`,
          status: xhr.status,
          details: body?.details ?? null,
          requestId: body?.request_id ?? xhr.getResponseHeader("x-request-id"),
        }),
      )
    }

    xhr.onerror = () => reject(new ApiError(OFFLINE_MESSAGE, { code: "network_error" }))
    xhr.ontimeout = () =>
      reject(
        new ApiError("The analysis is taking too long. Try a smaller file or a text-based PDF.", {
          code: "timeout",
        }),
      )
    xhr.onabort = () =>
      reject(new ApiError("Analysis cancelled.", { code: "cancelled" }))

    options.signal?.addEventListener("abort", () => xhr.abort(), { once: true })
    xhr.send(form)
  })
}

export const getSession = (sessionId: string) =>
  request<AnalysisReport>(`/sessions/${encodeURIComponent(sessionId)}`, {}, 20_000)

export const listSessions = () => request<AnalysisSummary[]>("/sessions", {}, 20_000)

export const deleteSession = (sessionId: string) =>
  request<null>(`/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }, 15_000)

/* -------------------------------------------------------------------------- */
/* Annotated PDFs                                                             */
/* -------------------------------------------------------------------------- */

export type AnnotateTarget = { sessionId: string } | { sampleId: string }

export function annotatePdf(target: AnnotateTarget): Promise<Blob> {
  const body =
    "sessionId" in target
      ? { session_id: target.sessionId, include_summary_page: true }
      : { sample_id: target.sampleId, include_summary_page: true }
  return requestBlob(
    "/annotate-pdf",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    90_000,
  )
}

export const downloadAnnotated = (sessionId: string) =>
  requestBlob(`/download-annotated/${encodeURIComponent(sessionId)}`, {}, 90_000)
