import { motion } from "framer-motion"
import {
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from "lucide-react"
import { useEffect, useState } from "react"
import type { FormEvent } from "react"
import { Brand } from "./Brand"
import { useAuth } from "../lib/auth"
import { Link } from "../lib/router"
import { useSound } from "../lib/sound"
import { googleProviderEnabled } from "../lib/supabase"
import { useToast } from "../lib/toast"

type Mode = "signin" | "signup"

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

export function Login({ onSuccess }: { onSuccess: () => void }) {
  const { signIn, signUp, signInWithGoogle, sendPasswordReset, configured } = useAuth()
  const toast = useToast()
  const { play } = useSound()

  const [mode, setMode] = useState<Mode>("signin")
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [busy, setBusy] = useState<"" | "email" | "google" | "reset">("")
  const [googleReady, setGoogleReady] = useState(false)

  // The Google button only earns its place once the provider is switched on in
  // the Supabase project. Offering it otherwise wastes a full page navigation
  // on a dead end, so ask the project first and hide it if the answer is no.
  useEffect(() => {
    if (!configured) return
    let alive = true
    void googleProviderEnabled().then((enabled) => {
      if (alive) setGoogleReady(enabled)
    })
    return () => {
      alive = false
    }
  }, [configured])

  const switchMode = (next: Mode) => {
    setMode(next)
    setError("")
    setNotice("")
    play("tap")
  }

  const fail = (message: string) => {
    setError(message)
    toast.error(message, { title: mode === "signin" ? "Could not sign you in" : "Could not create the account" })
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setNotice("")

    if (!EMAIL_RE.test(email.trim())) return fail("Enter a valid email address.")
    if (password.length < 8) return fail("Use a password of at least 8 characters.")

    setError("")
    setBusy("email")
    try {
      if (mode === "signin") {
        await signIn(email.trim().toLowerCase(), password)
        toast.success(`Signed in as ${email.trim().toLowerCase()}.`, { title: "Welcome back" })
        onSuccess()
      } else {
        const result = await signUp(email.trim().toLowerCase(), password, name.trim() || undefined)
        if (result.needsConfirmation) {
          setNotice(`Confirm your address: we sent a link to ${email.trim()}.`)
          toast.info("Check your inbox to activate the account.", { title: "One more step" })
        } else {
          toast.success("Your account is ready.", { title: "Account created" })
          onSuccess()
        }
      }
    } catch (cause) {
      fail((cause as Error).message)
    } finally {
      setBusy("")
    }
  }

  const google = async () => {
    setError("")
    setBusy("google")
    try {
      await signInWithGoogle()
    } catch (cause) {
      fail((cause as Error).message)
      setBusy("")
    }
  }

  const reset = async () => {
    if (!EMAIL_RE.test(email.trim())) return fail("Enter your email first, then tap reset.")
    setBusy("reset")
    try {
      await sendPasswordReset(email.trim().toLowerCase())
      toast.info("If that address has an account, a reset link is on its way.", { title: "Reset sent" })
    } catch (cause) {
      fail((cause as Error).message)
    } finally {
      setBusy("")
    }
  }

  return (
    <motion.section
      className="relative min-h-screen overflow-hidden p-5 md:p-8"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, y: -12 }}
    >
      <div className="mesh absolute inset-0" />
      <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between">
        <Brand size="md" />
        <div className="hidden items-center gap-2 text-xs text-white/45 sm:flex">
          <ShieldCheck size={14} className="text-mint" /> Your documents stay private
        </div>
      </header>

      <div className="relative z-10 mx-auto grid min-h-[calc(100vh-100px)] max-w-7xl items-center gap-12 py-10 lg:grid-cols-[1.1fr_.9fr]">
        <div className="hidden max-w-xl lg:block">
          <div className="mb-8 flex items-center gap-4">
            <img
              src={`${import.meta.env.BASE_URL}brand/leaselens-mark.png`}
              alt=""
              className="logo-glow size-20 rounded-3xl"
            />
            <div>
              <p className="mono-label text-cobalt">Tamil Nadu tenancy law</p>
              <p className="mt-1.5 max-w-[16rem] text-xs leading-5 text-white/40">
                25 statutory benchmarks · deterministic verdicts · English and தமிழ்
              </p>
            </div>
          </div>
          <h1 className="text-balance text-[clamp(3rem,5.4vw,5.6rem)] font-semibold leading-[0.92] tracking-[-0.075em] text-white">
            Know what your lease{" "}
            <span className="text-white/28">really says.</span>
          </h1>
          <div className="mt-10 flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-white/10 pt-6 text-sm text-white/42">
            <span>Plain language</span>
            <span className="size-1 rounded-full bg-cobalt" />
            <span>Local law</span>
            <span className="size-1 rounded-full bg-amber" />
            <span>Actionable fixes</span>
          </div>
        </div>

        <motion.div
          className="auth-card mx-auto w-full max-w-md"
          initial={{ opacity: 0, y: 18 }}
          animate={error ? { opacity: 1, y: 0, x: [0, -7, 7, -4, 0] } : { opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
        >
          <div className="segmented mb-6">
            {(
              [
                ["signin", "Sign in"],
                ["signup", "Create account"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={mode === value ? "active" : ""}
                onClick={() => switchMode(value)}
                aria-pressed={mode === value}
              >
                {label}
              </button>
            ))}
          </div>

          <h2 className="text-2xl font-semibold tracking-[-0.045em] text-white">
            {mode === "signin" ? "Welcome back" : "Start your first review"}
          </h2>
          <p className="mt-1.5 text-sm leading-6 text-white/45">
            {mode === "signin"
              ? "Your past reviews and documents are waiting."
              : "Create an account to keep a private history of every lease you check."}
          </p>

          {!configured && (
            <div className="mt-5 rounded-xl border border-amber/25 bg-amber/[0.07] p-3 text-[11.5px] leading-5 text-amber/90">
              <strong className="font-semibold">Demo mode.</strong> Supabase keys are not
              configured, so this profile is stored on this device only and the password is not
              checked. Add <code className="font-mono">VITE_SUPABASE_URL</code> and{" "}
              <code className="font-mono">VITE_SUPABASE_ANON_KEY</code> to enable real accounts.
            </div>
          )}

          {configured && googleReady && (
            <>
              <button
                type="button"
                className="social-button mt-5 w-full"
                onClick={google}
                disabled={busy !== ""}
              >
                {busy === "google" ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <GoogleGlyph />
                )}
                Continue with Google
              </button>
              <div className="my-5 flex items-center gap-3 text-[10px] uppercase tracking-[0.18em] text-white/25">
                <span className="h-px flex-1 bg-white/10" /> or use email{" "}
                <span className="h-px flex-1 bg-white/10" />
              </div>
            </>
          )}

          <form onSubmit={submit} noValidate className={configured ? "" : "mt-5"}>
            {mode === "signup" && (
              <>
                <label className="field-label" htmlFor="name">
                  Name <span className="text-white/25">(optional)</span>
                </label>
                <input
                  id="name"
                  className="field"
                  type="text"
                  autoComplete="name"
                  placeholder="Maya Raman"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
                <div className="h-4" />
              </>
            )}

            <label className="field-label" htmlFor="email">
              Email address
            </label>
            <div className="relative">
              <Mail size={15} className="field-icon" />
              <input
                id="email"
                className="field pl-10!"
                type="email"
                inputMode="email"
                placeholder="you@example.com"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>

            <div className="mt-4 flex items-center justify-between">
              <label className="field-label" htmlFor="password">
                Password
              </label>
              {mode === "signin" && configured && (
                <button
                  type="button"
                  className="text-[11px] text-white/40 hover:text-white disabled:opacity-50"
                  onClick={reset}
                  disabled={busy !== ""}
                >
                  {busy === "reset" ? "Sending…" : "Forgot password?"}
                </button>
              )}
            </div>
            <div className="relative">
              <LockKeyhole size={15} className="field-icon" />
              <input
                id="password"
                className="field pl-10! pr-11!"
                type={visible ? "text" : "password"}
                placeholder={mode === "signup" ? "At least 8 characters" : "Your password"}
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white"
                onClick={() => setVisible((value) => !value)}
                aria-label={visible ? "Hide password" : "Show password"}
              >
                {visible ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>

            <div className="min-h-9 pt-2" aria-live="polite">
              {error && <p className="text-[11.5px] leading-4 text-red">{error}</p>}
              {!error && notice && (
                <p className="flex items-start gap-1.5 text-[11.5px] leading-4 text-mint">
                  <CheckCircle2 size={13} className="mt-px shrink-0" /> {notice}
                </p>
              )}
            </div>

            <button className="primary-button w-full" type="submit" disabled={busy !== ""}>
              {busy === "email" ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <>
                  {mode === "signin" ? "Enter workspace" : "Create my account"} <ArrowRight size={17} />
                </>
              )}
            </button>
          </form>

          <p className="mt-5 text-center text-[11px] leading-5 text-white/28">
            By continuing you agree to our{" "}
            <Link to="/app/security" className="text-white/55 underline-offset-2 hover:underline">
              privacy and security terms
            </Link>
            . LeaseLens gives legal information, not legal advice.
          </p>
        </motion.div>
      </div>
    </motion.section>
  )
}

function GoogleGlyph() {
  return (
    <svg viewBox="0 0 48 48" width="16" height="16" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6.1C12.3 13.3 17.6 9.5 24 9.5Z"
      />
      <path
        fill="#4285F4"
        d="M46.1 24.5c0-1.6-.1-2.8-.4-4.1H24v8.4h12.6c-.3 2.1-1.6 5.2-4.6 7.3l7.6 5.9c4.5-4.2 6.5-10.2 6.5-17.5Z"
      />
      <path
        fill="#FBBC05"
        d="M10.4 28.7A14.6 14.6 0 0 1 9.6 24c0-1.6.3-3.2.8-4.7l-7.8-6.1A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.8l7.8-6.1Z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.5 0 11.9-2.1 15.6-5.9l-7.6-5.9c-2 1.4-4.7 2.4-8 2.4-6.4 0-11.7-3.8-13.6-9.9l-7.8 6.1C6.5 42.6 14.6 48 24 48Z"
      />
    </svg>
  )
}
