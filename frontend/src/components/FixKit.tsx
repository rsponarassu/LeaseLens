import { AnimatePresence, motion } from "framer-motion"
import {
  Check,
  Clipboard,
  FileDown,
  Languages,
  Mail,
  Scale,
  ShieldAlert,
  Sparkles,
} from "lucide-react"
import { useMemo, useState } from "react"
import { CATEGORY_LABELS, SEVERITY_RANK } from "../lib/types"
import type { AnalysisReport, ClauseFinding } from "../lib/types"
import { LEVEL_LABEL, levelTone, scoreVerdict } from "../lib/format"
import { useToast } from "../lib/toast"

export type Language = "en" | "ta"

/** Violations first, worst first; compliant clauses after them. */
export function orderFindings(findings: ClauseFinding[]): ClauseFinding[] {
  const weight = (finding: ClauseFinding) =>
    finding.status === "violation" || finding.status === "informational"
      ? 0
      : finding.status === "compliant"
        ? 1
        : 2
  return [...findings].sort((left, right) => {
    const byStatus = weight(left) - weight(right)
    if (byStatus !== 0) return byStatus
    const bySeverity = SEVERITY_RANK[right.severity] - SEVERITY_RANK[left.severity]
    if (bySeverity !== 0) return bySeverity
    return left.page_number - right.page_number
  })
}

export function FixKit({
  report,
  language,
  active,
  onSelect,
  onLanguage,
}: {
  report: AnalysisReport
  language: Language
  active: number
  onSelect: (index: number) => void
  onLanguage: (next: Language) => void
}) {
  const toast = useToast()
  const ordered = useMemo(() => orderFindings(report.findings), [report.findings])
  const finding = ordered[Math.min(active, ordered.length - 1)] ?? null
  const tone = levelTone(report.risk.risk_level)
  const [copied, setCopied] = useState<"" | "clause" | "email">("")

  const copy = async (kind: "clause" | "email", text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(kind)
      toast.success(
        kind === "clause" ? "Counter-clause copied." : "Email draft copied and ready to send.",
        { title: "Copied" },
      )
      window.setTimeout(() => setCopied(""), 1800)
    } catch {
      toast.error("Your browser blocked clipboard access. Select the text and copy manually.")
    }
  }

  return (
    <aside className="flex min-h-[720px] flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/[0.035]">
      <div className="border-b border-white/8 p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="mono-label text-white/30">Lease health</p>
            <div className="mt-2 flex items-end gap-2">
              <span className={`text-4xl font-semibold tracking-[-0.06em] tone-${tone}`}>
                {report.risk.overall_score}
              </span>
              <span className="mb-1 text-xs text-white/30">/ 100</span>
            </div>
            <p className="mt-1.5 text-[11px] font-semibold text-white/60">
              {LEVEL_LABEL[report.risk.risk_level]} · {scoreVerdict(report.risk.risk_level)}
            </p>
          </div>
          <ScoreRing score={report.risk.overall_score} tone={tone} />
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <Stat label="Violations" value={report.risk.violation_count} tone="red" />
          <Stat label="Balanced" value={report.risk.compliant_count} tone="mint" />
          <Stat label="Clauses" value={report.engine.clause_count} tone="grey" />
        </div>

        {report.risk.category_scores.length > 0 && (
          <div className="mt-4 space-y-1.5">
            {report.risk.category_scores.map((category) => (
              <div key={category.category} className="flex items-center gap-2">
                <span className="w-[7.5rem] shrink-0 truncate text-[10px] text-white/35">
                  {CATEGORY_LABELS[category.category]}
                </span>
                <span className="h-1 flex-1 overflow-hidden rounded-full bg-white/8">
                  <span
                    className={`block h-full rounded-full ${
                      category.score >= 60
                        ? "bg-red"
                        : category.score >= 30
                          ? "bg-amber"
                          : "bg-mint"
                    }`}
                    style={{ width: `${Math.max(4, category.score)}%` }}
                  />
                </span>
                <span className="w-6 text-right font-mono text-[9px] text-white/25">
                  {category.score}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-b border-white/8 px-4 py-2.5">
        <p className="mono-label text-white/30">Findings</p>
        <div className="segmented compact" aria-label="Explanation language">
          <button
            type="button"
            className={language === "en" ? "active" : ""}
            onClick={() => onLanguage("en")}
          >
            EN
          </button>
          <button
            type="button"
            className={language === "ta" ? "active" : ""}
            onClick={() => onLanguage("ta")}
          >
            தமிழ்
          </button>
        </div>
      </div>

      <div className="max-h-52 shrink-0 overflow-y-auto border-b border-white/8 scroll-thin">
        {ordered.map((item, index) => (
          <button
            key={item.clause_id}
            type="button"
            className={`finding-row ${active === index ? "active" : ""}`}
            onClick={() => onSelect(index)}
          >
            <span className={`risk-dot ${item.risk_color === "grey" ? "safe" : item.risk_color}`} />
            <span className="min-w-0 flex-1 truncate text-left text-[11.5px] text-white/65">
              {item.headline || item.heading}
            </span>
            <span className="shrink-0 font-mono text-[9px] uppercase tracking-wider text-white/25">
              p.{item.page_number}
            </span>
          </button>
        ))}
        {ordered.length === 0 && (
          <p className="px-4 py-6 text-center text-xs text-white/30">
            No clauses were detected in this document.
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-5 scroll-thin">
        <AnimatePresence mode="wait">
          {finding ? (
            <motion.div
              key={`${finding.clause_id}-${language}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className={`risk-badge ${finding.risk_color}`}>{finding.severity}</span>
                <span className="text-[10px] text-white/28">
                  {CATEGORY_LABELS[finding.category]} · clause {finding.clause_id}
                </span>
              </div>
              <h2 className="mt-3 text-xl font-semibold leading-tight tracking-[-0.035em] text-white">
                {finding.headline || finding.heading}
              </h2>

              <p className="mt-3 text-sm leading-6 text-white/55">
                {finding.fix
                  ? language === "ta"
                    ? finding.fix.explanation_ta
                    : finding.fix.explanation_en
                  : finding.status === "compliant"
                    ? "This clause sits within the statutory benchmark for Tamil Nadu."
                    : "LeaseLens could not extract a comparable fact from this clause."}
              </p>

              {finding.violations.length > 0 && (
                <div className="mt-5 rounded-xl border border-white/8 bg-black/20 p-4">
                  <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/35">
                    <ShieldAlert size={13} className="text-red" /> What the agreement breaks
                  </div>
                  <ul className="mt-2.5 space-y-2">
                    {finding.violations.map((violation) => (
                      <li
                        key={`${violation.rule_id}-${violation.message}`}
                        className="flex gap-2 text-[11.5px] leading-5 text-white/48"
                      >
                        <span className="mt-1.5 size-1 shrink-0 rounded-full bg-red" />
                        <span>{violation.message}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {finding.statute_references.length > 0 && (
                <div className="mt-3 rounded-xl border border-white/8 bg-black/20 p-4">
                  <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/35">
                    <Scale size={13} className="text-cobalt" /> Legal context
                  </div>
                  {finding.statute_references.slice(0, 2).map((reference) => (
                    <div key={`${reference.section}-${reference.heading}`} className="mt-2.5">
                      <p className="text-[11px] font-semibold text-white/65">
                        S.{reference.section} · {reference.heading}
                      </p>
                      <p className="mt-1 text-[11px] leading-5 text-white/38">“{reference.quote}”</p>
                    </div>
                  ))}
                  <p className="mt-2.5 text-[10px] leading-4 text-white/25">
                    {report.statute.short_name}
                    {report.statute.as_at ? ` · as at ${report.statute.as_at}` : ""}. Informational —
                    confirm with an advocate.
                  </p>
                </div>
              )}

              {finding.fix && (
                <div className="mt-3 rounded-xl border border-cobalt/20 bg-cobalt/[0.07] p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-cobalt">
                      <Sparkles size={13} /> Suggested counter-clause
                    </div>
                    <button
                      type="button"
                      className="copy-button"
                      onClick={() => copy("clause", finding.fix!.counter_clause)}
                    >
                      {copied === "clause" ? <Check size={12} /> : <Clipboard size={12} />}
                      {copied === "clause" ? "Copied" : "Copy"}
                    </button>
                  </div>
                  <p className="mt-3 text-[11.5px] leading-5 text-white/60">
                    “{finding.fix.counter_clause}”
                  </p>
                  {finding.fix.negotiation_tips.length > 0 && (
                    <ul className="mt-3 space-y-1.5 border-t border-white/8 pt-3">
                      {finding.fix.negotiation_tips.slice(0, 3).map((tip) => (
                        <li key={tip} className="flex gap-2 text-[11px] leading-5 text-white/38">
                          <span className="mt-1.5 size-1 shrink-0 rounded-full bg-cobalt" />
                          {tip}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {finding.raw_text && (
                <details className="mt-3 rounded-xl border border-white/8 bg-black/15 p-3">
                  <summary className="cursor-pointer text-[10px] uppercase tracking-[0.14em] text-white/30">
                    Clause as written
                  </summary>
                  <p className="mt-2 whitespace-pre-line text-[11px] leading-5 text-white/38">
                    {finding.raw_text}
                  </p>
                </details>
              )}
            </motion.div>
          ) : (
            <p className="text-xs text-white/30">Select a finding to see the details.</p>
          )}
        </AnimatePresence>
      </div>

      <div className="space-y-2 border-t border-white/8 p-4">
        <button
          className="primary-button w-full"
          type="button"
          disabled={!finding?.fix && !report.summary_email}
          onClick={() =>
            copy(
              "email",
              finding?.fix?.email_body ||
                `${report.summary_email?.subject ?? ""}\n\n${report.summary_email?.body ?? ""}`,
            )
          }
        >
          {copied === "email" ? <Check size={16} /> : <Mail size={16} />}
          {copied === "email" ? "Email copied" : "Copy message to landlord"}
        </button>
        <p className="flex items-center justify-center gap-1.5 text-[10px] text-white/22">
          <FileDown size={11} /> Download the marked-up PDF from the document pane
          <Languages size={11} /> English + தமிழ்
        </p>
      </div>
    </aside>
  )
}

function Stat({ label, value, tone }: { label: string; value: number; tone: "red" | "mint" | "grey" }) {
  return (
    <div className="rounded-lg border border-white/8 bg-black/20 py-1.5">
      <p className={`text-base font-semibold tone-${tone}`}>{value}</p>
      <p className="text-[9px] uppercase tracking-[0.1em] text-white/25">{label}</p>
    </div>
  )
}

function ScoreRing({ score, tone }: { score: number; tone: "red" | "amber" | "mint" }) {
  const stroke = tone === "red" ? "#ef5b64" : tone === "amber" ? "#f5a623" : "#26c995"
  const circumference = 2 * Math.PI * 26
  return (
    <div className="relative grid size-16 place-items-center">
      <svg viewBox="0 0 64 64" className="absolute inset-0 -rotate-90">
        <circle cx="32" cy="32" r="26" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="4" />
        <motion.circle
          cx="32"
          cy="32"
          r="26"
          fill="none"
          stroke={stroke}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference - (circumference * score) / 100 }}
          transition={{ duration: 0.9, ease: "easeOut" }}
        />
      </svg>
      <span className="font-mono text-[10px] text-white/45">{score}</span>
    </div>
  )
}
