import { motion } from "framer-motion"
import {
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  FileText,
  Loader2,
  MessageCircleQuestion,
  RefreshCw,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { ApiError, analyzeLease, listSamples } from "../lib/api"
import { useAuth } from "../lib/auth"
import { formatBytes, formatRelative, levelTone } from "../lib/format"
import { saveReview } from "../lib/history"
import { useReview } from "../lib/review"
import { useSound } from "../lib/sound"
import { useToast } from "../lib/toast"
import type { AnalysisReport, SampleLease } from "../lib/types"
import { ReportWorkspace } from "./ReportWorkspace"
import { UploadZone } from "./UploadZone"

type Phase = "idle" | "uploading" | "analyzing" | "error"

const ERROR_TITLES: Record<string, string> = {
  not_a_pdf: "That file isn't a PDF",
  unsupported_media_type: "That file isn't a PDF",
  file_too_large: "File too large",
  empty_upload: "Nothing to analyse",
  password_protected_pdf: "This PDF is locked",
  corrupt_pdf: "Couldn't read that PDF",
  unstructured_pdf: "No text found",
  network_error: "Backend unreachable",
  timeout: "Analysis timed out",
  cancelled: "Analysis cancelled",
}

export function Review() {
  const { report, origin, open, clear } = useReview()
  const { user, mode } = useAuth()
  const toast = useToast()
  const { play } = useSound()

  const [phase, setPhase] = useState<Phase>("idle")
  const [percent, setPercent] = useState(0)
  const [activeFile, setActiveFile] = useState<File | null>(null)
  const [errorText, setErrorText] = useState("")
  const [samples, setSamples] = useState<SampleLease[] | null>(null)
  const [samplesError, setSamplesError] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const announced = useRef(false)

  useEffect(() => {
    let cancelled = false
    listSamples()
      .then((result) => {
        if (!cancelled) setSamples(result)
      })
      .catch((cause: Error) => {
        if (cancelled) return
        setSamplesError(true)
        if (!announced.current) {
          announced.current = true
          toast.error(cause.message, { title: "Demo leases unavailable" })
        }
      })
    return () => {
      cancelled = true
    }
    // `toast` is stable (memoised provider value) and this must run once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const persist = async (result: AnalysisReport) => {
    if (!user) return
    try {
      await saveReview(user.id, mode, result)
    } catch (cause) {
      toast.warning(
        `${(cause as Error).message} The review is still open, but it won't appear in your history.`,
        { title: "Couldn't save to history" },
      )
    }
  }

  const start = async (file: File) => {
    setActiveFile(file)
    setErrorText("")
    setPercent(0)
    setPhase("uploading")
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const result = await analyzeLease(file, {
        signal: controller.signal,
        onProgress: (value) => {
          setPercent(value)
          if (value >= 100) setPhase("analyzing")
        },
      })
      setPhase("idle")
      open(result, { kind: "upload", file })
      toast.success(
        `Risk ${result.risk.overall_score}/100 · ${result.risk.violation_count} clause${
          result.risk.violation_count === 1 ? "" : "s"
        } need attention.`,
        { title: "Analysis complete" },
      )
      await persist(result)
    } catch (cause) {
      const error = cause as ApiError
      setPhase("error")
      if (error.code === "cancelled") {
        setErrorText("")
        setPhase("idle")
        toast.info("The upload was cancelled. Nothing was sent to the server.", {
          title: "Cancelled",
        })
        return
      }
      setErrorText(error.message)
      toast.error(error.message, {
        title: ERROR_TITLES[error.code] ?? "Analysis failed",
      })
    } finally {
      abortRef.current = null
    }
  }

  const cancel = () => {
    abortRef.current?.abort()
  }

  const openSample = (sample: SampleLease) => {
    play("tap")
    open(sample.analysis, { kind: "sample", sampleId: sample.sample_id })
    toast.success(`Loaded “${sample.title}” from the pre-analysed demo set.`, {
      title: "Demo lease opened",
      duration: 3500,
    })
    // A demo lease is still a review the user looked at, so it belongs in the
    // same history. Re-opening it updates that row rather than adding another.
    void persist(sample.analysis)
  }

  if (report) {
    return <ReportWorkspace report={report} origin={origin} onNew={clear} />
  }

  return (
    <div className="relative overflow-hidden">
      <div className="mesh absolute inset-0 opacity-70" />
      <section className="relative mx-auto grid max-w-7xl items-center gap-12 px-5 py-14 md:px-8 lg:min-h-[calc(100vh-64px)] lg:grid-cols-[1fr_.82fr] lg:py-16">
        <div>
          <div className="mb-6 flex items-center gap-2">
            <span className="status-pulse" />
            <span className="mono-label text-white/38">TN tenancy law · Act 42 of 2017</span>
          </div>
          <h1 className="max-w-3xl text-balance text-[clamp(2.9rem,5.6vw,5.8rem)] font-semibold leading-[0.92] tracking-[-0.075em] text-white">
            Upload a lease.
            <br />
            <span className="text-white/25">See the red flags.</span>
            <br />
            Fix them <span className="text-cobalt">before you sign.</span>
          </h1>
          <p className="mt-7 max-w-lg text-base leading-7 text-white/45">
            LeaseLens reads your agreement clause by clause, compares it with 25 benchmarks from
            Tamil Nadu tenancy law, and hands you the wording to negotiate.
          </p>
          <div className="mt-9 flex flex-wrap gap-x-7 gap-y-3 text-xs text-white/35">
            <span className="flex items-center gap-2">
              <CheckCircle2 size={14} className="text-mint" /> Plain-language findings
            </span>
            <span className="flex items-center gap-2">
              <CheckCircle2 size={14} className="text-mint" /> English + தமிழ்
            </span>
            <span className="flex items-center gap-2">
              <CheckCircle2 size={14} className="text-mint" /> File never stored
            </span>
          </div>
          {user?.email && (
            <p className="mt-7 text-[11px] text-white/25">
              Reviews are saved {mode === "cloud" ? "to your account" : "on this device"} as{" "}
              {user.email}.
            </p>
          )}
        </div>

        <div>
          {phase === "uploading" || phase === "analyzing" ? (
            <motion.div
              className="rounded-[28px] border border-white/12 bg-white/[0.04] p-6 sm:p-8"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
            >
              <div className="scan-document mx-auto mb-7">
                <FileCheck2 size={42} className="text-cobalt" />
                <motion.span
                  className="absolute left-2 right-2 h-px bg-cobalt shadow-[0_0_16px_#7186ff]"
                  animate={{ top: ["12%", "88%", "12%"] }}
                  transition={{ duration: 1.7, repeat: Infinity, ease: "easeInOut" }}
                />
              </div>
              <p className="mono-label text-center text-cobalt">
                {phase === "uploading" ? `Uploading ${percent}%` : "Analysing"}
              </p>
              <h2 className="mt-3 text-center text-xl font-semibold tracking-[-0.04em] text-white">
                {phase === "uploading" ? "Sending your lease securely" : "Finding what deserves your attention"}
              </h2>
              <p className="mt-2 truncate text-center text-xs text-white/38">
                {activeFile?.name} · {activeFile ? formatBytes(activeFile.size) : ""}
              </p>
              <div className="mt-6 h-1 overflow-hidden rounded-full bg-white/8">
                {phase === "uploading" ? (
                  <div
                    className="h-full rounded-full bg-cobalt transition-[width] duration-200"
                    style={{ width: `${Math.max(4, percent)}%` }}
                  />
                ) : (
                  <motion.div
                    className="h-full w-1/3 rounded-full bg-cobalt"
                    animate={{ x: ["-100%", "300%"] }}
                    transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
                  />
                )}
              </div>
              <p className="mt-4 text-center text-[11px] leading-5 text-white/30">
                Extracting text · splitting clauses · applying 25 statutory benchmarks
              </p>
              <button className="ghost-button mx-auto mt-5" type="button" onClick={cancel}>
                <X size={13} /> Cancel
              </button>
            </motion.div>
          ) : (
            <>
              <UploadZone
                onFile={start}
                onReject={(message) => toast.error(message, { title: "Upload rejected" })}
              />
              {phase === "error" && errorText && (
                <div className="mt-3 flex items-start gap-2 rounded-xl border border-red/25 bg-red/[0.06] p-3">
                  <TriangleAlert size={14} className="mt-0.5 shrink-0 text-red" />
                  <p className="text-[11px] leading-5 text-white/55">{errorText}</p>
                  <button
                    className="ml-auto text-white/40 hover:text-white"
                    onClick={() => setPhase("idle")}
                    aria-label="Dismiss error"
                  >
                    <X size={13} />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </section>

      <section className="relative border-t border-white/8 bg-black/20 px-5 py-12 md:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="mono-label text-cobalt">Demo leases</p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-white">
                Three real agreements, analysed at startup
              </h2>
              <p className="mt-1.5 max-w-xl text-xs leading-5 text-white/35">
                No upload, no API key, no waiting — these reports are pinned in memory so a
                presentation never depends on the network.
              </p>
            </div>
            {samplesError && (
              <button className="ghost-button" onClick={() => window.location.reload()}>
                <RefreshCw size={13} /> Retry
              </button>
            )}
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {!samples && !samplesError && (
              <>
                {[0, 1, 2].map((key) => (
                  <div key={key} className="skeleton h-40 rounded-2xl" />
                ))}
              </>
            )}
            {samples?.map((sample) => {
              const tone = levelTone(sample.analysis.risk.risk_level)
              return (
                <motion.button
                  key={sample.sample_id}
                  type="button"
                  className="sample-card text-left"
                  whileHover={{ y: -3 }}
                  onClick={() => openSample(sample)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className={`risk-dot ${tone === "amber" ? "medium" : tone === "red" ? "high" : "safe"}`} />
                      <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-white/30">
                        {sample.tenant_persona}
                      </span>
                    </div>
                    <span className={`text-lg font-semibold tone-${tone}`}>
                      {sample.analysis.risk.overall_score}
                      <span className="text-[10px] text-white/25">/100</span>
                    </span>
                  </div>
                  <p className="mt-3 text-sm font-semibold leading-snug text-white">{sample.title}</p>
                  <p className="mt-1.5 line-clamp-2 text-[11.5px] leading-5 text-white/38">
                    {sample.scenario}
                  </p>
                  <div className="mt-3 flex items-center justify-between text-[10px] text-white/25">
                    <span>
                      {sample.analysis.page_count} pages · {sample.analysis.risk.violation_count}{" "}
                      violations
                    </span>
                    <span className="flex items-center gap-1 text-cobalt">
                      Open <ArrowRight size={11} />
                    </span>
                  </div>
                </motion.button>
              )
            })}
          </div>

          {samples && (
            <p className="mt-3 text-[10px] text-white/20">
              Generated and scored {formatRelative(samples[0].analysis.created_at)} · score version{" "}
              {samples[0].analysis.risk.scoring_version}
            </p>
          )}
        </div>
      </section>

      <section className="relative border-t border-white/8 bg-black/20 px-5 py-12 md:px-8">
        <div className="mx-auto grid max-w-7xl gap-4 md:grid-cols-3">
          {[
            [
              FileText,
              "01",
              "Upload securely",
              "The PDF goes straight to the analyser over HTTPS. It is held in memory for the session, never written to disk.",
            ],
            [
              Sparkles,
              "02",
              "Understand the risk",
              "Every clause is classified and compared with the Act 42 of 2017 benchmarks. Code decides the verdict, not a model.",
            ],
            [
              MessageCircleQuestion,
              "03",
              "Know what to say",
              "Each violation comes with a counter-clause and an email you can send your landlord.",
            ],
          ].map(([Icon, number, title, copy]) => {
            const FeatureIcon = Icon as typeof FileText
            return (
              <motion.article key={String(number)} className="feature-card" whileHover={{ y: -4 }}>
                <div className="flex items-center justify-between">
                  <FeatureIcon size={20} className="text-cobalt" />
                  <span className="font-mono text-[10px] text-white/20">{String(number)}</span>
                </div>
                <h2 className="mt-8 text-lg font-semibold tracking-tight text-white">
                  {String(title)}
                </h2>
                <p className="mt-2 text-sm leading-6 text-white/38">{String(copy)}</p>
              </motion.article>
            )
          })}
        </div>
      </section>

      <div className="pointer-events-none fixed bottom-24 left-1/2 -translate-x-1/2 md:hidden">
        {phase === "analyzing" && (
          <span className="flex items-center gap-2 rounded-full border border-white/10 bg-black/70 px-3 py-1.5 text-[11px] text-white/60 backdrop-blur">
            <Loader2 size={12} className="animate-spin" /> analysing…
          </span>
        )}
      </div>
    </div>
  )
}
