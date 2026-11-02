import { motion } from "framer-motion"
import {
  CalendarClock,
  ChevronRight,
  CloudOff,
  FileText,
  Loader2,
  Search,
  ShieldAlert,
  Trash2,
  UploadCloud,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useAuth } from "../lib/auth"
import { formatBytes, formatDate, formatRelative, LEVEL_LABEL, levelTone } from "../lib/format"
import { clearReviews, deleteReview, listReviews } from "../lib/history"
import type { ReviewRecord } from "../lib/history"
import { useReview } from "../lib/review"
import { useRouter } from "../lib/router"
import { useToast } from "../lib/toast"
import type { RiskLevel } from "../lib/types"

const FILTERS: { value: "all" | RiskLevel; label: string }[] = [
  { value: "all", label: "All" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "elevated", label: "Elevated" },
  { value: "moderate", label: "Moderate" },
  { value: "low", label: "Low" },
]

export function History() {
  const { user, mode } = useAuth()
  const { open } = useReview()
  const { navigate } = useRouter()
  const toast = useToast()

  const [records, setRecords] = useState<ReviewRecord[] | null>(null)
  const [error, setError] = useState("")
  const [query, setQuery] = useState("")
  const [filter, setFilter] = useState<"all" | RiskLevel>("all")
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    if (!user) return
    setError("")
    try {
      setRecords(await listReviews(user.id, mode))
    } catch (cause) {
      setError((cause as Error).message)
      setRecords([])
    }
  }, [user, mode])

  useEffect(() => {
    void load()
  }, [load])

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase()
    return (records ?? []).filter((record) => {
      const matchesFilter = filter === "all" || record.risk_level === filter
      const matchesTerm =
        !term ||
        record.file_name.toLowerCase().includes(term) ||
        record.top_drivers.some((driver) => driver.toLowerCase().includes(term))
      return matchesFilter && matchesTerm
    })
  }, [records, query, filter])

  const openRecord = (record: ReviewRecord) => {
    open(record.report, { kind: "history" })
    navigate("/app/review")
    toast.info(
      record.session_id
        ? "Reopened from your history. The highlighted PDF is re-rendered if the session is still warm."
        : "Reopened from your history.",
      { title: "Review restored", duration: 4000 },
    )
  }

  const remove = async (record: ReviewRecord) => {
    if (!user) return
    setBusy(true)
    try {
      await deleteReview(user.id, mode, record.id)
      setRecords((current) => (current ?? []).filter((row) => row.id !== record.id))
      toast.success(`“${record.file_name}” was removed from your history.`, { title: "Review deleted" })
    } catch (cause) {
      toast.error((cause as Error).message, { title: "Couldn't delete" })
    } finally {
      setBusy(false)
      setPendingDelete(null)
    }
  }

  const clearAll = async () => {
    if (!user) return
    setBusy(true)
    try {
      await clearReviews(user.id, mode)
      setRecords([])
      toast.success("Your review history is empty.", { title: "History cleared" })
    } catch (cause) {
      toast.error((cause as Error).message, { title: "Couldn't clear history" })
    } finally {
      setBusy(false)
      setConfirmClear(false)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mono-label text-cobalt">Your workspace</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.05em] text-white">
            Past reviews
          </h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-white/40">
            <span>
              {records === null ? "Loading…" : `${records.length} saved`} ·{" "}
              {mode === "cloud" ? "stored in your account" : "stored on this device only"}
            </span>
            {mode === "device" && (
              <span className="flex items-center gap-1 text-amber/80">
                <CloudOff size={11} /> add Supabase keys for cross-device history
              </span>
            )}
          </p>
        </div>
        {records && records.length > 0 && (
          <div className="flex items-center gap-2">
            {confirmClear ? (
              <>
                <button className="danger-button" onClick={clearAll} disabled={busy}>
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                  Delete everything
                </button>
                <button className="ghost-button" onClick={() => setConfirmClear(false)}>
                  Cancel
                </button>
              </>
            ) : (
              <button className="ghost-button" onClick={() => setConfirmClear(true)}>
                <Trash2 size={13} /> Clear all
              </button>
            )}
          </div>
        )}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[13rem] flex-1">
          <Search size={14} className="field-icon" />
          <input
            className="field pl-10!"
            placeholder="Search by file name or finding…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="Search reviews"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((option) => (
            <button
              key={option.value}
              className={`filter-chip ${filter === option.value ? "active" : ""}`}
              onClick={() => setFilter(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mt-5 rounded-xl border border-red/25 bg-red/[0.06] p-4">
          <p className="text-xs font-semibold text-red">Couldn't load your history</p>
          <p className="mt-1 text-[11px] leading-5 text-white/50">{error}</p>
          <button className="ghost-button mt-3" onClick={() => void load()}>
            Try again
          </button>
        </div>
      )}

      {records === null && (
        <div className="mt-5 space-y-2">
          {[0, 1, 2].map((key) => (
            <div key={key} className="skeleton h-[88px] rounded-2xl" />
          ))}
        </div>
      )}

      {records !== null && visible.length === 0 && (
        <div className="mt-8 rounded-2xl border border-dashed border-white/12 bg-white/[0.02] px-6 py-14 text-center">
          <span className="mx-auto grid size-12 place-items-center rounded-2xl border border-white/10 bg-white/[0.04] text-cobalt">
            <FileText size={20} />
          </span>
          <p className="mt-4 text-sm font-semibold text-white">
            {records.length === 0 ? "No reviews yet" : "Nothing matches that filter"}
          </p>
          <p className="mx-auto mt-1.5 max-w-sm text-xs leading-5 text-white/38">
            {records.length === 0
              ? "Every analysis you run is saved here with its score and findings, so you can compare versions of the same lease before signing."
              : "Try a different risk level or clear the search box."}
          </p>
          {records.length === 0 && (
            <button className="primary-button mx-auto mt-5" onClick={() => navigate("/app/review")}>
              <UploadCloud size={16} /> Analyse a lease
            </button>
          )}
        </div>
      )}

      <div className="mt-5 space-y-2">
        {visible.map((record) => {
          const tone = levelTone(record.risk_level)
          const deleting = pendingDelete === record.id
          return (
            <motion.article
              key={record.id}
              layout
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="history-row"
            >
              <button
                type="button"
                className="flex min-w-0 flex-1 items-center gap-4 text-left"
                onClick={() => openRecord(record)}
              >
                <span className={`history-score tone-${tone}`}>{record.overall_score}</span>
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-semibold text-white">
                      {record.file_name}
                    </span>
                    <span className={`risk-badge ${tone === "red" ? "high" : tone === "amber" ? "medium" : "safe"}`}>
                      {LEVEL_LABEL[record.risk_level]}
                    </span>
                    {record.sample_id && (
                      <span className="rounded-full bg-white/8 px-2 py-0.5 text-[9px] uppercase tracking-wider text-white/40">
                        demo
                      </span>
                    )}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-white/30">
                    <span className="flex items-center gap-1">
                      <CalendarClock size={10} /> {formatDate(record.created_at)}
                    </span>
                    <span>{formatRelative(record.created_at)}</span>
                    <span>{record.page_count} pages</span>
                    <span className="flex items-center gap-1 text-red/70">
                      <ShieldAlert size={10} /> {record.violation_count} violations
                    </span>
                    {record.report ? (
                      <span>{formatBytes(record.report.file_size_bytes)}</span>
                    ) : null}
                  </span>
                  {record.top_drivers[0] && (
                    <span className="mt-1.5 line-clamp-1 block text-[11px] text-white/35">
                      {record.top_drivers[0]}
                    </span>
                  )}
                </span>
                <ChevronRight size={15} className="ml-auto shrink-0 text-white/20" />
              </button>

              <div className="flex shrink-0 items-center gap-1.5">
                {deleting ? (
                  <>
                    <button
                      className="danger-button"
                      onClick={() => void remove(record)}
                      disabled={busy}
                    >
                      {busy ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                      Delete
                    </button>
                    <button className="ghost-button" onClick={() => setPendingDelete(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    className="icon-button"
                    onClick={() => setPendingDelete(record.id)}
                    aria-label={`Delete review of ${record.file_name}`}
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
            </motion.article>
          )
        })}
      </div>

      {records && records.length > 0 && (
        <p className="mt-6 text-[10.5px] leading-5 text-white/22">
          Deleting a review removes the saved report and findings. The PDF itself was never stored
          here — only the server-side highlight session, which expires on its own.
        </p>
      )}
    </div>
  )
}
