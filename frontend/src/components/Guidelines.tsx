import { motion } from "framer-motion"
import {
  BookOpen,
  CheckCircle2,
  ChevronDown,
  FileText,
  Gauge,
  Languages,
  Loader2,
  Lock,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react"
import { useEffect, useState } from "react"
import { listRules } from "../lib/api"
import { Link } from "../lib/router"
import { CATEGORY_LABELS } from "../lib/types"
import type { ClauseCategory, RuleCatalogue, RuleDefinition } from "../lib/types"

const STEPS = [
  {
    icon: FileText,
    title: "1 · Upload",
    copy: "Drop a PDF of the agreement. Text-layer PDFs are ideal; scanned pages fall back to OCR when Tesseract is installed on the server.",
  },
  {
    icon: ScanSearch,
    title: "2 · Segment",
    copy: "The document is split into numbered or headed clauses, keeping the page and bounding box of every clause so it can be highlighted later.",
  },
  {
    icon: Gauge,
    title: "3 · Decide",
    copy: "Each clause is classified and reduced to typed facts — 10 months' deposit, 45-day refund. Python compares those facts with the rule base. The model never picks the verdict.",
  },
  {
    icon: Sparkles,
    title: "4 · Fix",
    copy: "Every violation gets a plain-English and Tamil explanation, a counter-clause, and an email you can send without rewriting anything.",
  },
]

const BEST_PRACTICE = [
  "Use the original PDF, not a photo or a screenshot — the text layer is what keeps the numbers accurate.",
  "Keep it under 15 MB. If your scan is bigger, compress it or split the pages.",
  "Remove the password before uploading. LeaseLens cannot read encrypted files and will reject them.",
  "One agreement per file. Two leases in one PDF confuse the clause splitter.",
  "Check email drafts before sending: names and rent come from the document, and the draft is a starting point, not a legal notice.",
]

const FAQ = [
  {
    q: "Is the risk score legal advice?",
    a: "No. The score is a transparent tally of statutory benchmarks, produced by code you can audit through GET /api/v1/rules. It tells you what is worth negotiating, not what a court would decide.",
  },
  {
    q: "Why does a clause say “not applicable”?",
    a: "The agreement did not state the fact the benchmark checks — for example a deposit clause that never mentions the refund window. Missing information is not a violation, but it is usually worth demanding in writing.",
  },
  {
    q: "What happens to my PDF?",
    a: "It is parsed in memory. Nothing is written to disk by the API, and the in-memory copy is dropped when the session expires (one hour by default). Saved reviews keep the findings, with the clause text stripped.",
  },
  {
    q: "Can I use this for a commercial lease?",
    a: "The rule base encodes residential tenancy benchmarks from the Tamil Nadu Act. Commercial agreements fall outside it, and the findings should be treated as indicative only.",
  },
  {
    q: "The highlighted PDF says the session expired. Why?",
    a: "Highlight sessions live in RAM, so a server restart or the one-hour TTL removes them. Your saved review keeps every finding and counter-clause; re-upload the file to regenerate the marked-up copy.",
  },
]

function describe(rule: RuleDefinition): string {
  const unit = rule.unit ? ` ${rule.unit}` : ""
  const value = rule.value === null || rule.value === undefined ? "" : String(rule.value)
  switch (rule.operator) {
    case "greater_than":
      return `more than ${value}${unit}`
    case "greater_or_equal":
      return `at least ${value}${unit}`
    case "less_than":
      return `less than ${value}${unit}`
    case "less_or_equal":
      return `at most ${value}${unit}`
    case "equals":
      return `equal to ${value}${unit}`
    case "not_equals":
      return `not equal to ${value}${unit}`
    case "is_true":
      return "present"
    case "is_false":
      return "absent"
    case "is_null":
      return "not stated"
    case "is_not_null":
      return "stated"
    default:
      return `${rule.operator.replace(/_/g, " ")} ${value}${unit}`.trim()
  }
}

export function Guidelines() {
  const [catalogue, setCatalogue] = useState<RuleCatalogue | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false
    listRules()
      .then((result) => {
        if (!cancelled) setCatalogue(result)
      })
      .catch((cause: Error) => {
        if (!cancelled) setError(cause.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const grouped = (catalogue?.rules ?? []).reduce<Record<string, RuleDefinition[]>>((acc, rule) => {
    const key = rule.category
    acc[key] = [...(acc[key] ?? []), rule]
    return acc
  }, {})

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <header className="border-b border-white/8 pb-6">
        <p className="mono-label flex items-center gap-2 text-cobalt">
          <BookOpen size={12} /> User guidelines
        </p>
        <h1 className="mt-3 text-balance text-3xl font-semibold leading-tight tracking-[-0.05em] text-white sm:text-4xl">
          How to read a LeaseLens review
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-white/45">
          LeaseLens turns a rental agreement into a score, a list of findings and the wording to
          negotiate. This page explains what each number means, how to get an accurate result, and
          where the limits are.
        </p>
      </header>

      <section className="mt-8">
        <h2 className="section-title">The pipeline, in four steps</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {STEPS.map((step) => {
            const Icon = step.icon
            return (
              <motion.article key={step.title} className="info-card" whileHover={{ y: -2 }}>
                <Icon size={18} className="text-cobalt" />
                <p className="mt-3 text-sm font-semibold text-white">{step.title}</p>
                <p className="mt-1.5 text-[11.5px] leading-5 text-white/40">{step.copy}</p>
              </motion.article>
            )
          })}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="section-title">Reading the score</h2>
        <p className="mt-2 text-xs leading-5 text-white/40">
          The score is severity-led: the worst violation sets the base, additional violations add a
          capped breadth bonus, and the total is scaled by how much control the clause takes away
          from you. A clean maintenance clause cannot dilute a critical eviction term.
        </p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {(catalogue?.risk_bands ?? []).map((band) => (
            <div key={`${band.level}-${band.min_score}`} className="band-row">
              <span className={`band-dot ${band.level}`} />
              <span className="flex-1 text-xs font-medium text-white/75">{band.label}</span>
              <span className="font-mono text-[10px] text-white/30">
                {band.min_score}–{band.max_score}
              </span>
            </div>
          ))}
          {!catalogue && !error && (
            <div className="skeleton h-[52px] rounded-xl sm:col-span-2" />
          )}
          {error && (
            <p className="text-[11px] leading-5 text-amber/80 sm:col-span-2">
              Couldn't load the live band thresholds ({error}). The bands are low 0–19, moderate
              20–39, elevated 40–59, high 60–79 and critical 80–100.
            </p>
          )}
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <Legend tone="bg-red" title="Red highlight" copy="A statutory benchmark is broken. Negotiate before signing." />
          <Legend tone="bg-amber" title="Amber highlight" copy="Ambiguous, or missing a protection that matters later." />
          <Legend tone="bg-mint" title="Green highlight" copy="Within the benchmark. Nothing to change." />
        </div>
      </section>

      <section className="mt-10">
        <h2 className="section-title">Getting an accurate result</h2>
        <ul className="mt-4 space-y-2">
          {BEST_PRACTICE.map((item) => (
            <li key={item} className="flex gap-2.5 text-[12.5px] leading-6 text-white/50">
              <CheckCircle2 size={14} className="mt-1 shrink-0 text-mint" />
              {item}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-10">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 className="section-title">The benchmarks behind every verdict</h2>
          {catalogue && (
            <p className="text-[10px] text-white/25">
              {catalogue.rule_count} rules · scoring v{catalogue.scoring_version}
            </p>
          )}
        </div>
        <p className="mt-2 text-xs leading-5 text-white/40">
          {catalogue
            ? `${catalogue.statute.act} (${catalogue.statute.act_number})`
            : "Tamil Nadu Regulation of Rights and Responsibilities of Landlords and Tenants Act, 2017"}
        </p>

        {!catalogue && !error && (
          <p className="mt-4 flex items-center gap-2 text-[11px] text-white/30">
            <Loader2 size={12} className="animate-spin" /> loading the live rule base…
          </p>
        )}

        <div className="mt-4 space-y-4">
          {(Object.keys(grouped) as ClauseCategory[]).map((category) => (
            <div key={category}>
              <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-cobalt/80">
                {CATEGORY_LABELS[category]}
              </p>
              <div className="mt-2 overflow-hidden rounded-xl border border-white/8">
                {grouped[category].map((rule) => (
                  <div
                    key={rule.id}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-white/5 bg-white/[0.02] px-3 py-2 last:border-0"
                  >
                    <span className="font-mono text-[10px] text-white/30">{rule.id}</span>
                    <span className="flex-1 text-[12px] text-white/65">{rule.title}</span>
                    <span className="font-mono text-[10px] text-white/35">{describe(rule)}</span>
                    <span className={`risk-badge ${rule.severity === "critical" || rule.severity === "high" ? "high" : rule.severity === "moderate" ? "medium" : "safe"}`}>
                      {rule.severity}
                    </span>
                    <span className="w-full font-mono text-[9.5px] text-white/20">
                      S.{rule.statute.section} · {rule.statute.heading}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="section-title">What LeaseLens cannot do</h2>
        <div className="mt-3 rounded-xl border border-amber/20 bg-amber/[0.05] p-4">
          <p className="flex items-center gap-2 text-xs font-semibold text-amber">
            <TriangleAlert size={14} /> Read this before relying on a finding
          </p>
          <ul className="mt-2 space-y-1.5 text-[11.5px] leading-5 text-white/50">
            <li>· It reads the document as text. Handwriting, stamps and tables in images are missed.</li>
            <li>· It checks 25 benchmarks, not every obligation in the Act.</li>
            <li>· A "compliant" verdict means the stated number is within the limit — not that the clause is good for you.</li>
            <li>· It is not a substitute for an advocate, especially before a dispute or an eviction notice.</li>
          </ul>
        </div>
      </section>

      <section className="mt-10">
        <h2 className="section-title">Questions people ask</h2>
        <div className="mt-3 divide-y divide-white/8 overflow-hidden rounded-xl border border-white/8">
          {FAQ.map((item) => (
            <details key={item.q} className="group bg-white/[0.02] px-4 py-3">
              <summary className="flex cursor-pointer items-center justify-between gap-3 text-[12.5px] font-medium text-white/75">
                {item.q}
                <ChevronDown size={14} className="shrink-0 text-white/30 transition-transform group-open:rotate-180" />
              </summary>
              <p className="mt-2 text-[11.5px] leading-5 text-white/45">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <footer className="mt-10 flex flex-wrap items-center gap-4 border-t border-white/8 pt-5 text-[11px] text-white/30">
        <span className="flex items-center gap-1.5">
          <ShieldCheck size={12} className="text-mint" /> Privacy model
        </span>
        <Link to="/app/security" className="hover:text-white">
          What we store and what we never store →
        </Link>
        <span className="flex items-center gap-1.5">
          <Languages size={12} /> English + தமிழ்
        </span>
        <span className="flex items-center gap-1.5">
          <Lock size={12} /> HTTPS only
        </span>
      </footer>
    </div>
  )
}

function Legend({ tone, title, copy }: { tone: string; title: string; copy: string }) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.02] p-3">
      <p className="flex items-center gap-2 text-[11.5px] font-semibold text-white/75">
        <span className={`size-2 rounded-full ${tone}`} /> {title}
      </p>
      <p className="mt-1.5 text-[10.5px] leading-4 text-white/38">{copy}</p>
    </div>
  )
}
