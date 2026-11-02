/**
 * Accounts.
 *
 * Two backends behind one interface:
 *  - Supabase Auth when VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are set.
 *  - A local profile for the same device otherwise, so the product is demoable
 *    before any keys exist. The UI says which one is in use; it never pretends
 *    that a device-local profile is a real account.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import type { User } from "@supabase/supabase-js"
import { supabase, supabaseConfigured } from "./supabase"

const LOCAL_USER_KEY = "leaselens.local.user"

export type AuthMode = "cloud" | "device"
export type AuthStatus = "booting" | "authenticated" | "anonymous"

export interface Account {
  id: string
  email: string
  name: string | null
  provider: "email" | "google" | "local"
}

export class AuthError extends Error {
  readonly code: string

  constructor(message: string, code = "auth_error") {
    super(message)
    this.name = "AuthError"
    this.code = code
  }
}

function translate(message: string): string {
  const text = message.toLowerCase()
  if (text.includes("invalid login credentials")) return "That email and password don't match an account."
  if (text.includes("email not confirmed")) return "Confirm your email first — the link is in your inbox."
  if (text.includes("already registered") || text.includes("already been registered"))
    return "An account with this email already exists. Sign in instead."
  if (text.includes("password should be")) return "Use a password of at least 8 characters."
  if (text.includes("rate limit") || text.includes("too many"))
    return "Too many attempts. Wait a minute and try again."
  if (text.includes("provider is not enabled"))
    return "Google sign-in isn't enabled in your Supabase project yet."
  if (text.includes("unable to validate email")) return "That email address doesn't look valid."
  return message
}

function toAccount(user: User): Account {
  const provider = user.app_metadata?.provider ?? "email"
  return {
    id: user.id,
    email: user.email ?? "",
    name: (user.user_metadata?.full_name as string | undefined) ?? null,
    provider: provider === "google" ? "google" : "email",
  }
}

function localId(email: string): string {
  let hash = 0
  for (let index = 0; index < email.length; index += 1) {
    hash = (hash * 31 + email.charCodeAt(index)) | 0
  }
  return `local-${Math.abs(hash).toString(36)}`
}

function readLocalAccount(): Account | null {
  try {
    const raw = window.localStorage.getItem(LOCAL_USER_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<Account>
    if (!parsed.id || !parsed.email) return null
    return { id: parsed.id, email: parsed.email, name: parsed.name ?? null, provider: "local" }
  } catch {
    return null
  }
}

export interface SignUpResult {
  /** True when Supabase requires the emailed link before the account can sign in. */
  needsConfirmation: boolean
}

interface AuthValue {
  status: AuthStatus
  user: Account | null
  mode: AuthMode
  configured: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, name?: string) => Promise<SignUpResult>
  signInWithGoogle: () => Promise<void>
  sendPasswordReset: (email: string) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("booting")
  const [user, setUser] = useState<Account | null>(null)
  const mode: AuthMode = supabaseConfigured ? "cloud" : "device"

  useEffect(() => {
    if (!supabase) {
      const stored = readLocalAccount()
      setUser(stored)
      setStatus(stored ? "authenticated" : "anonymous")
      return
    }

    let alive = true
    void supabase.auth.getSession().then(({ data }) => {
      if (!alive) return
      const session = data.session
      setUser(session ? toAccount(session.user) : null)
      setStatus(session ? "authenticated" : "anonymous")
    })

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session ? toAccount(session.user) : null)
      setStatus(session ? "authenticated" : "anonymous")
    })

    return () => {
      alive = false
      subscription.subscription.unsubscribe()
    }
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    if (!supabase) {
      // Device mode: there is no password to check, because there is no account.
      const account: Account = {
        id: localId(email),
        email,
        name: null,
        provider: "local",
      }
      window.localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(account))
      setUser(account)
      setStatus("authenticated")
      return
    }

    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw new AuthError(translate(error.message), error.code ?? "sign_in_failed")
  }, [])

  const signUp = useCallback(async (email: string, password: string, name?: string) => {
    if (!supabase) {
      const account: Account = {
        id: localId(email),
        email,
        name: name ?? null,
        provider: "local",
      }
      window.localStorage.setItem(LOCAL_USER_KEY, JSON.stringify(account))
      setUser(account)
      setStatus("authenticated")
      return { needsConfirmation: false }
    }

    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: name?.trim() || null } },
    })
    if (error) throw new AuthError(translate(error.message), error.code ?? "sign_up_failed")
    return { needsConfirmation: !data.session }
  }, [])

  const signInWithGoogle = useCallback(async () => {
    if (!supabase) {
      throw new AuthError(
        "Google sign-in needs a Supabase project. Add your keys to enable it.",
        "not_configured",
      )
    }
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        // Navigate ourselves. The default redirect cannot be awaited, so a
        // project with the provider switched off dumps the user on a raw JSON
        // error page instead of telling them what happened.
        skipBrowserRedirect: true,
        redirectTo: `${window.location.origin}${window.location.pathname}#/app/review`,
        queryParams: { prompt: "select_account" },
      },
    })
    if (error) throw new AuthError(translate(error.message), "oauth_failed")
    if (!data?.url) {
      throw new AuthError("Google sign-in could not be started. Use email instead.", "oauth_failed")
    }
    window.location.assign(data.url)
  }, [])

  const sendPasswordReset = useCallback(async (email: string) => {
    if (!supabase) {
      throw new AuthError(
        "Password reset needs a Supabase project. Add your keys to enable it.",
        "not_configured",
      )
    }
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}${window.location.pathname}#/login`,
    })
    if (error) throw new AuthError(translate(error.message), "reset_failed")
  }, [])

  const signOut = useCallback(async () => {
    if (supabase) await supabase.auth.signOut()
    try {
      window.localStorage.removeItem(LOCAL_USER_KEY)
    } catch {
      /* ignore */
    }
    setUser(null)
    setStatus("anonymous")
  }, [])

  const value = useMemo<AuthValue>(
    () => ({
      status,
      user,
      mode,
      configured: supabaseConfigured,
      signIn,
      signUp,
      signInWithGoogle,
      sendPasswordReset,
      signOut,
    }),
    [status, user, mode, signIn, signUp, signInWithGoogle, sendPasswordReset, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>")
  return value
}
