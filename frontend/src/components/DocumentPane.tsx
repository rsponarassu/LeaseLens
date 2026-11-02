import { AnimatePresence, motion } from "framer-motion"
import {
  Download,
  ExternalLink,
  FileWarning,
  Highlighter,
  Loader2,
  RotateCcw,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { annotatePdf, samplePdfUrl } from "../lib/api"
import { documentMeta, formatBytes } from "../lib/format"
import type { ReviewOrigin } from "../lib/review"
import type { AnalysisReport } from "../lib/types"

type View = "annotated" | "original"

/**
 * The document pane.
 *
 * The highlighted PDF is rendered by the backend, not approximated in the DOM:
 * `POST /annotate-pdf` returns the real file with PyMuPDF rectangles drawn at
 * the clause coordinates the pipeline recorded. For a review restored from
 * history the server session may already have expired, so this falls back to a
 * clause-by-clause text view instead of pretending the file is still there.
 */
export function DocumentPane({
  report,
  origin,
}: {
  report: AnalysisReport
  origin: ReviewOrigin | null
}) {
  const [view, setView] = useState<View>("annotated")
  const [annotatedUrl, setAnnotatedUrl] = useState<string | null>(null)
  const [originalUrl, setOriginalUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const urls = useRef<string[]>([])

  const target = useMemo(() => {
    if (origin?.kind === "sample") return { sampleId: origin.sampleId }
    if (report.sample_id) return { sampleId: report.sample_id }
    if (report.session_id) return { sessionId: report.session_id }
    return null
  }, [origin, report.sample_id, report.session_id])

  useEffect(() => {
    setAnnotatedUrl(null)
    setError(null)
    setLoading(true)
    if (!target) {
      setLoading(false)
      setError("This review has no live document session. Upload the PDF again to see highlights.")
      return
    }

    let cancelled = false
    annotatePdf(target)
      .then((blob) => {
        if (cancelled) return
        const url = URL.createObjectURL(blob)
        urls.current.push(url)
        setAnnotatedUrl(url)
      })
      .catch((cause: Error) => {
        if (cancelled) return
        setError(cause.message)
        setView("original")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [target, attempt])

  useEffect(() => {
    if (origin?.kind === "upload") {
      const url = URL.createObjectURL(origin.file)
      urls.current.push(url)
      setOriginalUrl(url)
      return
    }
    if (origin?.kind === "sample") {
      setOriginalUrl(origin.sampleId ? samplePdfUrl(origin.sampleId) : null)
      return
    }
    if (origin?.kind === "history" && report.sample_id) {
      setOriginalUrl(samplePdfUrl(report.sample_id))
    }
  }, [origin, report.sample_id])

  useEffect(() => {
    return () => {
      for (const url of urls.current) {
        if (url.startsWith("blob:")) URL.revokeObjectURL(url)
      }
      urls.current = []
    }
  }, [])

  const activeUrl = view === "annotated" ? annotatedUrl : originalUrl

  const download = useCallback(() => {
    const url = annotatedUrl ?? originalUrl
    if (!url) return
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = report.file_name.replace(/\.pdf$/i, "") + "-leaselens.pdf"
    document.body.append(anchor)
    anchor.click()
    anchor.remove()
  }, [annotatedUrl, originalUrl, report.file_name])

  return (
    <section className="flex min-h-[720px] flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#111214]">
      <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-white/8 px-4 py-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-white/70">{report.file_name}</p>
          <p className="mt-0.5 text-[10px] text-white/28">
            {documentMeta(report.page_count, report.file_size_bytes)}
            {report.extraction.ocr_used && " · OCR used"}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="segmented compact" aria-label="Document version">
            <button
              type="button"
              className={view === "annotated" ? "active" : ""}
              onClick={() => setView("annotated")}
              disabled={!annotatedUrl}
            >
              <Highlighter size={12} /> Marked up
            </button>
            <button
              type="button"
              className={view === "original" ? "active" : ""}
              onClick={() => setView("original")}
              disabled={!originalUrl}
            >
              Original
            </button>
          </div>
          <button
            className="icon-button"
            onClick={() => setAttempt((value) => value + 1)}
            aria-label="Re-render highlights"
            title="Re-render highlights"
          >
            <RotateCcw size={14} />
          </button>
          <a
            className="icon-button"
            href={activeUrl ?? undefined}
            target="_blank"
            rel="noreferrer"
            aria-label="Open in new tab"
            aria-disabled={!activeUrl}
            onClick={(event) => {
              if (!activeUrl) event.preventDefault()
            }}
          >
            <ExternalLink size={14} />
          </a>
          <button
            className="icon-button"
            onClick={download}
            disabled={!annotatedUrl && !originalUrl}
            aria-label="Download PDF"
            title="Download the highlighted PDF"
          >
            <Download size={14} />
          </button>
        </div>
      </div>

      <div className="relative flex-1">
        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div
              key="loading"
              className="absolute inset-0 grid place-items-center"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <div className="text-center">
                <Loader2 size={22} className="mx-auto animate-spin text-cobalt" />
                <p className="mt-3 text-xs text-white/40">Drawing highlights on your PDF…</p>
              </div>
            </motion.div>
          ) : activeUrl ? (
            <motion.iframe
              key={activeUrl}
              title={`${report.file_name} — ${view === "annotated" ? "highlighted" : "original"}`}
              src={`${activeUrl}#view=FitH&toolbar=0&navpanes=0`}
              className="h-full min-h-[660px] w-full bg-[#0e0f11]"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            />
          ) : (
            <motion.div
              key="fallback"
              className="h-full overflow-y-auto scroll-thin p-4 sm:p-6"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber/25 bg-amber/[0.07] p-3">
                <FileWarning size={16} className="mt-0.5 shrink-0 text-amber" />
                <div>
                  <p className="text-xs font-semibold text-amber">Highlighted file unavailable</p>
                  <p className="mt-1 text-[11px] leading-5 text-white/50">
                    {error ??
                      "The in-memory copy of this lease expired when the server restarted. The clause verdicts below are saved, so nothing is lost — re-upload the PDF for a marked-up copy."}
                  </p>
                </div>
              </div>
              <div className="space-y-2">
                {report.findings.map((finding) => (
                  <article
                    key={finding.clause_id}
                    className="clause-row"
                    data-tone={finding.risk_color}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-[11px] font-semibold text-white/75">
                        {finding.heading}
                      </p>
                      <span className="shrink-0 font-mono text-[9px] uppercase tracking-widest text-white/25">
                        p.{finding.page_number}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-4 text-[11.5px] leading-5 text-white/40">
                      {finding.raw_text ||
                        `${finding.headline}. The clause text itself was cleared when this review was saved, so only the finding is kept.`}
                    </p>
                  </article>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="flex h-11 items-center justify-between border-t border-white/8 px-4 text-[10px] text-white/28">
        <span className="flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-red" /> high risk
          <span className="ml-2 size-1.5 rounded-full bg-amber" /> review
          <span className="ml-2 size-1.5 rounded-full bg-mint" /> balanced
        </span>
        <span className="font-mono">
          {report.page_count} pages · {formatBytes(report.file_size_bytes)}
        </span>
      </div>
    </section>
  )
}
