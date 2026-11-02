import { motion } from "framer-motion"
import { ArrowLeft, Clock3, Cpu, Gauge, Share2, TriangleAlert } from "lucide-react"
import { useState } from "react"
import { DocumentPane } from "./DocumentPane"
import { FixKit } from "./FixKit"
import type { Language } from "./FixKit"
import { LEVEL_LABEL, levelTone, scoreVerdict } from "../lib/format"
import type { ReviewOrigin } from "../lib/review"
import { useToast } from "../lib/toast"
import type { AnalysisReport } from "../lib/types"

export function ReportWorkspace({
  report,
  origin,
  onNew,
}: {
  report: AnalysisReport
  origin: ReviewOrigin | null
  onNew: () => void
}) {
  const [active, setActive] = useState(0)
  const [language, setLanguage] = useState<Language>("en")
  const toast = useToast()
  const tone = levelTone(report.risk.risk_level)
  const warnings = [...report.extraction.warnings, ...report.engine.warnings]

  const share = async () => {
    const lines = [
      `LeaseLens review — ${report.file_name}`,
      `Risk score: ${report.risk.overall_score}/100 (${LEVEL_LABEL[report.risk.risk_level]})`,
      `${report.risk.violation_count} clause(s) need attention.`,
      ...report.risk.top_drivers.map((driver) => `• ${driver}`),
    ].join("\n")
    try {
      await navigator.clipboard.writeText(lines)
      toast.success("Summary copied — paste it into a chat or email.", { title: "Summary copied" })
    } catch {
      toast.error("Clipboard access was blocked by your browser.")
    }
  }

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-5 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button className="ghost-button" type="button" onClick={onNew}>
          <ArrowLeft size={14} /> New review
        </button>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`risk-badge ${tone === "red" ? "high" : tone === "amber" ? "medium" : "safe"}`}>
            {LEVEL_LABEL[report.risk.risk_level]}
          </span>
          <span className="meta-chip">
            <Gauge size={11} /> {report.risk.scoring_version}
          </span>
          <span className="meta-chip">
            <Clock3 size={11} /> {(report.engine.duration_ms / 1000).toFixed(1)}s
          </span>
          <span className="meta-chip">
            <Cpu size={11} />
            {report.engine.analysis_mode === "llm_assisted"
              ? report.engine.llm_provider
              : "deterministic"}
          </span>
          <button className="icon-button" onClick={share} aria-label="Copy summary">
            <Share2 size={15} />
          </button>
        </div>
      </div>

      <motion.div
        className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(390px,.8fr)]"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="order-2 xl:order-1">
          <DocumentPane report={report} origin={origin} />
        </div>

        <div className="order-1 space-y-4 xl:order-2">
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="mono-label text-white/30">{report.risk.band_label}</p>
                <h1 className="mt-2 max-w-md text-balance text-2xl font-semibold leading-tight tracking-[-0.04em] text-white">
                  {report.risk.headline}
                </h1>
                <p className={`mt-2 text-xs font-semibold tone-${tone}`}>
                  {scoreVerdict(report.risk.risk_level)}
                </p>
              </div>
              <div className="text-right">
                <p className={`text-4xl font-semibold tracking-[-0.06em] tone-${tone}`}>
                  {report.risk.overall_score}
                </p>
                <p className="text-[10px] uppercase tracking-[0.14em] text-white/25">risk score</p>
              </div>
            </div>

            {report.risk.top_drivers.length > 0 && (
              <ul className="mt-4 space-y-1.5 border-t border-white/8 pt-3">
                {report.risk.top_drivers.map((driver) => (
                  <li key={driver} className="flex gap-2 text-[11.5px] leading-5 text-white/45">
                    <span className={`mt-1.5 size-1 shrink-0 rounded-full tone-dot-${tone}`} />
                    {driver}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <FixKit
            report={report}
            language={language}
            active={active}
            onSelect={setActive}
            onLanguage={setLanguage}
          />
        </div>
      </motion.div>

      {warnings.length > 0 && (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-amber/20 bg-amber/[0.05] p-3">
          <TriangleAlert size={14} className="mt-0.5 shrink-0 text-amber" />
          <div className="text-[11px] leading-5 text-white/45">
            <p className="font-semibold text-amber/90">Extraction notes</p>
            <ul className="mt-1 space-y-0.5">
              {warnings.slice(0, 4).map((warning) => (
                <li key={warning}>· {warning}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <p className="mt-5 max-w-3xl text-[11px] leading-5 text-white/25">{report.disclaimer}</p>
    </div>
  )
}
