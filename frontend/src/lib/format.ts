import type { RiskLevel, Severity } from "./types"

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 KB"
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return "—"
  const diff = Date.now() - then
  const minutes = Math.round(diff / 60_000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} hr ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`
  return formatDate(iso)
}

/** Tailwind-ish colour token used by dots, badges and rings. */
export function levelTone(level: RiskLevel): "red" | "amber" | "mint" {
  if (level === "critical" || level === "high") return "red"
  if (level === "elevated" || level === "moderate") return "amber"
  return "mint"
}

export function severityTone(severity: Severity): "red" | "amber" | "mint" | "grey" {
  if (severity === "critical" || severity === "high") return "red"
  if (severity === "moderate") return "amber"
  if (severity === "low" || severity === "info") return "mint"
  return "grey"
}

export const LEVEL_LABEL: Record<RiskLevel, string> = {
  low: "Low risk",
  moderate: "Moderate",
  elevated: "Needs attention",
  high: "High risk",
  critical: "Critical",
}

/** Plain-English verdict shown next to the score. */
export function scoreVerdict(level: RiskLevel): string {
  switch (level) {
    case "critical":
      return "Do not sign without changes"
    case "high":
      return "Several clauses need negotiation"
    case "elevated":
      return "Worth negotiating before you sign"
    case "moderate":
      return "Mostly fair, a few points to check"
    default:
      return "Broadly balanced"
  }
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** Small helper for the "12 pages · 2.4 MB" line. */
export function documentMeta(pages: number, bytes: number): string {
  return `${pages} page${pages === 1 ? "" : "s"} · ${formatBytes(bytes)}`
}

export function initialsFrom(nameOrEmail: string): string {
  const cleaned = nameOrEmail.trim()
  if (!cleaned) return "LL"
  const words = cleaned.split(/[\s._-]+/).filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  return cleaned.slice(0, 2).toUpperCase()
}
