import {
  Clock3,
  Cookie,
  Database,
  Fingerprint,
  KeyRound,
  Lock,
  ServerOff,
  ShieldCheck,
  Trash2,
  UserCheck,
} from "lucide-react"
import { useAuth } from "../lib/auth"
import { useConsent } from "../lib/consent"
import { Link } from "../lib/router"
import { supabaseHost } from "../lib/supabase"

const DATA_ROWS = [
  {
    what: "The PDF you upload",
    where: "API process memory only",
    how: "Dropped when the session expires (1 hour) or the server restarts. No temporary files are written.",
  },
  {
    what: "The highlighted PDF",
    where: "API process memory only",
    how: "Rendered on demand and cached against the same session. Downloading it is what creates a copy on your disk.",
  },
  {
    what: "Clause text of the agreement",
    where: "Your browser tab",
    how: "Streamed to the page as part of the report, and stripped before a review is saved anywhere.",
  },
  {
    what: "A saved review",
    where: "Your Supabase project, or this browser in demo mode",
    how: "Score, findings, explanations and counter-clauses. Delete it from History at any time.",
  },
  {
    what: "Your email address",
    where: "Supabase Auth",
    how: "Used for sign-in only. Never included in a report or shared with the analysis pipeline.",
  },
  {
    what: "Server logs",
    where: "Your deployment's stdout",
    how: "Request line, timing and outcome. Clause text is not logged unless the operator explicitly sets LOG_RAW_TEXT.",
  },
]

const COOKIES = [
  {
    name: "leaselens_consent",
    purpose: "Remembers this choice so the banner doesn't reappear.",
    life: "180 days",
    category: "Necessary",
  },
  {
    name: "sb-…-auth-token",
    purpose: "Your Supabase sign-in session. Refreshed automatically, erased on sign out.",
    life: "Until sign-out",
    category: "Necessary",
  },
  {
    name: "leaselens.sound.enabled",
    purpose: "Whether interface sound effects are on.",
    life: "Until cleared",
    category: "Preferences",
  },
  {
    name: "leaselens.language",
    purpose: "Your English / தமிழ் choice for explanations.",
    life: "Until cleared",
    category: "Preferences",
  },
  {
    name: "leaselens.reviews.*",
    purpose: "Your saved reviews, only when the app runs without Supabase.",
    life: "Until cleared",
    category: "Functional",
  },
]

export function Security() {
  const { openPreferences, consent } = useConsent()
  const { mode } = useAuth()
  const host = supabaseHost()

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <header className="border-b border-white/8 pb-6">
        <p className="mono-label flex items-center gap-2 text-cobalt">
          <ShieldCheck size={12} /> Security &amp; privacy
        </p>
        <h1 className="mt-3 text-balance text-3xl font-semibold leading-tight tracking-[-0.05em] text-white sm:text-4xl">
          Your lease is read, not kept
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-white/45">
          A rental agreement contains your address, your rent and your landlord's name. LeaseLens is
          built so the document passes through the analyser and disappears, while the findings you
          need stay available to you.
        </p>
      </header>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <Promise
          icon={ServerOff}
          title="Never written to disk"
          copy="Uploads are parsed in memory. The API has no upload directory, no temp file and no object store."
        />
        <Promise
          icon={Clock3}
          title="One hour, then gone"
          copy="The in-memory session that powers highlighting expires after 60 minutes by default, or immediately on restart."
        />
        <Promise
          icon={Trash2}
          title="You delete, it's deleted"
          copy="Every saved review has a delete control, and 'Clear all' removes the whole history in one request."
        />
      </div>

      <section className="mt-10">
        <h2 className="section-title">Where each piece of data lives</h2>
        <div className="mt-3 overflow-hidden rounded-xl border border-white/8">
          {DATA_ROWS.map((row) => (
            <div
              key={row.what}
              className="grid gap-1 border-b border-white/5 bg-white/[0.02] px-4 py-3 last:border-0 sm:grid-cols-[1fr_1.1fr_1.6fr] sm:gap-4"
            >
              <p className="text-[12px] font-medium text-white/75">{row.what}</p>
              <p className="font-mono text-[10.5px] text-cobalt/80">{row.where}</p>
              <p className="text-[11px] leading-5 text-white/38">{row.how}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="section-title">Accounts</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="info-card">
            <Fingerprint size={18} className="text-cobalt" />
            <p className="mt-3 text-sm font-semibold text-white">Row-level security by default</p>
            <p className="mt-1.5 text-[11.5px] leading-5 text-white/40">
              Saved reviews carry a <code className="font-mono text-[10px] text-white/55">user_id</code>{" "}
              and the database policy only returns rows where{" "}
              <code className="font-mono text-[10px] text-white/55">auth.uid()</code> matches. The
              public anon key cannot read another tenant's history.
            </p>
          </div>
          <div className="info-card">
            <KeyRound size={18} className="text-cobalt" />
            <p className="mt-3 text-sm font-semibold text-white">
              {mode === "cloud" ? "Passwords never reach this app" : "Demo mode, clearly labelled"}
            </p>
            <p className="mt-1.5 text-[11.5px] leading-5 text-white/40">
              {mode === "cloud"
                ? `Credentials are handled by Supabase Auth${host ? ` (${host})` : ""}. LeaseLens never sees or stores a password hash, and Google sign-in uses OAuth so no password is shared at all.`
                : "No Supabase keys are configured, so the profile lives in this browser's storage and no password is checked or transmitted. That is fine for a demo and wrong for real data."}
            </p>
          </div>
          <div className="info-card">
            <Lock size={18} className="text-cobalt" />
            <p className="mt-3 text-sm font-semibold text-white">Encrypted in transit</p>
            <p className="mt-1.5 text-[11.5px] leading-5 text-white/40">
              The browser talks to the API and to Supabase over HTTPS. Responses for a generated PDF
              are marked <code className="font-mono text-[10px] text-white/55">private, no-store</code>{" "}
              so a shared computer cannot replay them from cache.
            </p>
          </div>
          <div className="info-card">
            <UserCheck size={18} className="text-cobalt" />
            <p className="mt-3 text-sm font-semibold text-white">What stays outside the app</p>
            <p className="mt-1.5 text-[11.5px] leading-5 text-white/40">
              If the operator enables an LLM provider, the clause text needed for classification is
              sent to that provider under their data terms. Scores and verdicts are always computed
              locally by rules.yaml, never by the model.
            </p>
          </div>
        </div>
      </section>

      <section className="mt-10">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="section-title">Cookies and local storage</h2>
          <button className="ghost-button" onClick={openPreferences}>
            <Cookie size={13} /> Manage preferences
          </button>
        </div>
        <p className="mt-2 text-xs leading-5 text-white/40">
          Nothing outside the "Necessary" rows is written until you choose. Choosing "Essential only"
          clears the preference keys from this device.
        </p>
        <div className="mt-3 overflow-hidden rounded-xl border border-white/8">
          <div className="hidden grid-cols-[1.4fr_1.6fr_.7fr_.7fr] gap-3 border-b border-white/8 bg-white/[0.03] px-4 py-2 text-[9.5px] uppercase tracking-[0.14em] text-white/30 sm:grid">
            <span>Name</span>
            <span>Purpose</span>
            <span>Lifetime</span>
            <span>Type</span>
          </div>
          {COOKIES.map((row) => (
            <div
              key={row.name}
              className="grid gap-1 border-b border-white/5 px-4 py-2.5 last:border-0 sm:grid-cols-[1.4fr_1.6fr_.7fr_.7fr] sm:items-center sm:gap-3"
            >
              <span className="truncate font-mono text-[10.5px] text-white/60">{row.name}</span>
              <span className="text-[11px] leading-4 text-white/38">{row.purpose}</span>
              <span className="text-[10.5px] text-white/30">{row.life}</span>
              <span
                className={`w-fit rounded-full px-2 py-0.5 text-[9px] uppercase tracking-wider ${
                  row.category === "Necessary"
                    ? "bg-mint/10 text-mint/80"
                    : row.category === "Preferences"
                      ? "bg-amber/10 text-amber/80"
                      : "bg-white/8 text-white/45"
                }`}
              >
                {row.category}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[10.5px] text-white/25">
          Your current choice: preferences {consent.preferences ? "allowed" : "not allowed"},
          analytics {consent.analytics ? "allowed" : "not allowed"}.
        </p>
      </section>

      <section className="mt-10">
        <h2 className="section-title">Your controls</h2>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {[
            ["Delete one review", "History → the bin icon on any row. Removes the report and its findings."],
            ["Delete everything", "History → Clear all. One request, no soft delete left behind."],
            ["Drop the live session", "Sign out, or wait an hour; the server forgets the document either way."],
            ["Change cookie consent", "Cookie preferences in the account menu, or the button above."],
            ["Stop saving reviews", "Use the app signed out, or delete each review once you have your PDF."],
            ["Audit a verdict", "Every finding names a rule id; GET /api/v1/rules/{id} returns its statute and quote."],
          ].map(([title, copy]) => (
            <li key={title} className="flex gap-2.5 rounded-xl border border-white/8 bg-white/[0.02] p-3">
              <Database size={14} className="mt-0.5 shrink-0 text-cobalt" />
              <span>
                <span className="block text-[12px] font-medium text-white/75">{title}</span>
                <span className="mt-1 block text-[11px] leading-5 text-white/38">{copy}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-10 rounded-xl border border-white/8 bg-white/[0.02] p-4">
        <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-white/45">
          Honest limitations
        </h2>
        <ul className="mt-2 space-y-1.5 text-[11.5px] leading-5 text-white/40">
          <li>
            · Removing a review does not remove entries from your deployment's access logs. Retention
            there is the operator's policy, not something a browser can change.
          </li>
          <li>
            · An operator with shell access to the server can read a document while its one-hour
            session is alive. Memory-only is a strong default, not encryption at rest.
          </li>
          <li>
            · LeaseLens is informational. Before you act on a finding — especially an eviction or a
            deposit dispute — confirm it with a qualified advocate.
          </li>
        </ul>
      </section>

      <footer className="mt-8 flex flex-wrap items-center gap-4 border-t border-white/8 pt-5 text-[11px] text-white/30">
        <Link to="/app/guide" className="hover:text-white">
          ← Back to the guidelines
        </Link>
        <button className="hover:text-white" onClick={openPreferences}>
          Cookie preferences
        </button>
        <span>Report a wrong citation with the rule id from the finding.</span>
      </footer>
    </div>
  )
}

function Promise({
  icon: Icon,
  title,
  copy,
}: {
  icon: typeof ServerOff
  title: string
  copy: string
}) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.02] p-4">
      <Icon size={18} className="text-mint" />
      <p className="mt-2.5 text-[12.5px] font-semibold text-white/80">{title}</p>
      <p className="mt-1.5 text-[11px] leading-5 text-white/38">{copy}</p>
    </div>
  )
}
