/**
 * Review history.
 *
 * What is stored is the *derived* report — verdicts, scores and the generated
 * counter-clauses — with the verbatim clause text stripped first. The uploaded
 * PDF is never persisted here; the server keeps it in memory only long enough to
 * render a highlighted copy, and the browser keeps it only while the tab is open.
 *
 * With Supabase configured the rows live in `lease_reviews` behind row-level
 * security. Without it they live in localStorage, capped at 40 entries.
 */

import type { AnalysisReport, RiskLevel } from "./types"
import { REVIEWS_TABLE, supabase } from "./supabase"

const LOCAL_PREFIX = "leaselens.reviews."
const LOCAL_LIMIT = 40

export type HistoryMode = "cloud" | "device"

export interface ReviewRecord {
  id: string
  created_at: string
  file_name: string
  page_count: number
  overall_score: number
  risk_level: RiskLevel
  violation_count: number
  top_drivers: string[]
  session_id: string | null
  sample_id: string | null
  report: AnalysisReport
}

export class HistoryError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "HistoryError"
  }
}

/**
 * Turn a PostgREST failure into something the user can act on.
 *
 * The three cases below are the ones a fresh project actually hits: the table
 * has not been created yet, the policies are missing, or the session expired
 * while the tab was open. Everything else keeps its original message, which is
 * the fastest way to a fix for anyone who knows SQL.
 */
function describe(action: string, error: { message: string; code?: string }): HistoryError {
  const code = error.code ?? ""
  const text = error.message.toLowerCase()
  if (code === "PGRST205" || code === "42P01" || text.includes("could not find the table")) {
    return new HistoryError(
      "Saved reviews are not set up on this Supabase project yet. Run supabase/schema.sql once, then try again.",
    )
  }
  if (code === "42501" || text.includes("permission denied")) {
    return new HistoryError(
      `This account is not allowed to ${action} (check the row-level security policies).`,
    )
  }
  if (code === "PGRST301" || text.includes("jwt expired")) {
    return new HistoryError("Your session expired. Sign in again to continue.")
  }
  return new HistoryError(`Could not ${action}: ${error.message}`)
}

function localKey(userId: string): string {
  return `${LOCAL_PREFIX}${userId}`
}

function readLocal(userId: string): ReviewRecord[] {
  try {
    const raw = window.localStorage.getItem(localKey(userId))
    if (!raw) return []
    const parsed = JSON.parse(raw) as ReviewRecord[]
    return Array.isArray(parsed) ? parsed.filter((row) => row && row.report) : []
  } catch {
    return []
  }
}

function writeLocal(userId: string, rows: ReviewRecord[]) {
  try {
    window.localStorage.setItem(localKey(userId), JSON.stringify(rows.slice(0, LOCAL_LIMIT)))
  } catch {
    // A full quota must not break the review the user just paid attention to.
    throw new HistoryError(
      "This device is out of storage space. Delete an older review and try again.",
    )
  }
}

/**
 * Strip the verbatim lease text before anything is persisted.
 *
 * The report embeds the clause text it read. Keeping that in a database would
 * contradict the promise made on the security page, so the saved copy keeps the
 * verdicts, explanations and counter-clauses and drops `raw_text`. The session
 * cache still holds the full document in memory until it expires.
 */
function redactText(report: AnalysisReport): AnalysisReport {
  return {
    ...report,
    findings: report.findings.map((finding) => ({ ...finding, raw_text: "" })),
  }
}

export function recordFromReport(report: AnalysisReport): ReviewRecord {
  return {
    id: crypto.randomUUID(),
    created_at: new Date().toISOString(),
    file_name: report.file_name,
    page_count: report.page_count,
    overall_score: report.risk.overall_score,
    risk_level: report.risk.risk_level,
    violation_count: report.risk.violation_count,
    top_drivers: report.risk.top_drivers.slice(0, 3),
    session_id: report.sample_id ? null : report.session_id,
    sample_id: report.sample_id,
    report: redactText(report),
  }
}

export async function listReviews(userId: string, mode: HistoryMode): Promise<ReviewRecord[]> {
  if (mode === "device") return readLocal(userId)

  if (!supabase) throw new HistoryError("Supabase is not configured.")
  const { data, error } = await supabase
    .from(REVIEWS_TABLE)
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(100)

  if (error) throw describe("load your history", error)
  return (data ?? []) as ReviewRecord[]
}

export async function saveReview(
  userId: string,
  mode: HistoryMode,
  report: AnalysisReport,
): Promise<ReviewRecord> {
  const record = recordFromReport(report)

  if (mode === "device") {
    const existing = readLocal(userId)
    // Re-analysing the same file twice, or reopening the same demo lease, should
    // not double up in the list.
    const deduped = existing.filter(
      (row) =>
        !(row.file_name === record.file_name && row.session_id === record.session_id) &&
        !(record.sample_id && row.sample_id === record.sample_id),
    )
    writeLocal(userId, [record, ...deduped])
    return record
  }

  if (!supabase) throw new HistoryError("Supabase is not configured.")
  const payload = {
    user_id: userId,
    file_name: record.file_name,
    page_count: record.page_count,
    overall_score: record.overall_score,
    risk_level: record.risk_level,
    violation_count: record.violation_count,
    top_drivers: record.top_drivers,
    session_id: record.session_id,
    sample_id: record.sample_id,
    report: record.report,
  }

  // A demo lease can be opened any number of times; keep one row per sample
  // instead of appending a near-identical copy on every visit.
  if (record.sample_id) {
    const { data: existing, error: lookupError } = await supabase
      .from(REVIEWS_TABLE)
      .select("id")
      .eq("user_id", userId)
      .eq("sample_id", record.sample_id)
      .maybeSingle()

    if (lookupError) {
      throw describe("save this review", lookupError)
    }
    if (existing) {
      const { data, error } = await supabase
        .from(REVIEWS_TABLE)
        .update(payload)
        .eq("id", (existing as { id: string }).id)
        .select()
        .single()
      if (error) throw describe("save this review", error)
      return data as ReviewRecord
    }
  }

  const { data, error } = await supabase
    .from(REVIEWS_TABLE)
    .insert(payload)
    .select()
    .single()

  if (error) throw describe("save this review", error)
  return data as ReviewRecord
}

export async function deleteReview(
  userId: string,
  mode: HistoryMode,
  id: string,
): Promise<void> {
  if (mode === "device") {
    writeLocal(
      userId,
      readLocal(userId).filter((row) => row.id !== id),
    )
    return
  }

  if (!supabase) throw new HistoryError("Supabase is not configured.")
  const { error } = await supabase.from(REVIEWS_TABLE).delete().eq("id", id).eq("user_id", userId)
  if (error) throw describe("delete this review", error)
}

export async function clearReviews(userId: string, mode: HistoryMode): Promise<void> {
  if (mode === "device") {
    writeLocal(userId, [])
    return
  }

  if (!supabase) throw new HistoryError("Supabase is not configured.")
  const { error } = await supabase.from(REVIEWS_TABLE).delete().eq("user_id", userId)
  if (error) throw describe("clear your history", error)
}
