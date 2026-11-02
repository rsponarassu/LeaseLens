/**
 * Supabase client.
 *
 * The anon key is intentionally public: every table is protected by row-level
 * security, so the key alone grants nothing beyond what `auth.uid()` allows.
 * The service-role key must never appear in this bundle.
 *
 * When the two variables are absent the app still runs — accounts and history
 * fall back to on-device storage, clearly labelled in the UI.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js"

const url = (import.meta.env.VITE_SUPABASE_URL ?? "").trim()
const anonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY ?? "").trim()

export const supabaseConfigured = Boolean(url && anonKey)

export const supabase: SupabaseClient | null = supabaseConfigured
  ? createClient(url, anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        flowType: "pkce",
      },
    })
  : null

/** Host shown on the security page, e.g. `xyzcompany.supabase.co`. */
export function supabaseHost(): string | null {
  if (!url) return null
  try {
    return new URL(url).host
  } catch {
    return null
  }
}

export const REVIEWS_TABLE = "lease_reviews"

/**
 * Is Google OAuth actually switched on for this project?
 *
 * With `skipBrowserRedirect` the client can detect a disabled provider, but the
 * honest answer is to not offer the button at all: `/auth/v1/settings` is a
 * public endpoint that lists the enabled providers, so the login card asks it
 * once instead of leaving a control that leads nowhere. A failed probe keeps
 * the button, because a network hiccup is not evidence that Google is off.
 */
export async function googleProviderEnabled(): Promise<boolean> {
  if (!url) return false
  try {
    const response = await fetch(`${url}/auth/v1/settings`, { headers: { apikey: anonKey } })
    if (!response.ok) return true
    const settings = (await response.json()) as { external?: { google?: boolean } }
    return settings.external?.google === true
  } catch {
    return true
  }
}
