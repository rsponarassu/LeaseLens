/**
 * Cookie and storage consent.
 *
 * Three categories, and the third is honest about being empty today:
 *  - essential   - the Supabase session cookie and the record of this choice.
 *  - preferences - your sound setting and language, kept in localStorage.
 *  - analytics   - off, because this build ships no third-party analytics.
 *
 * Nothing outside `essential` is written until you choose. Choosing
 * "Essential only" also clears preference keys that are already on the device.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"

export const CONSENT_VERSION = 1
const STORAGE_KEY = "leaselens.consent.v1"
const COOKIE_NAME = "leaselens_consent"
const COOKIE_MAX_AGE = 60 * 60 * 24 * 180 // 180 days

export interface ConsentRecord {
  version: number
  decided: boolean
  essential: true
  preferences: boolean
  analytics: boolean
  decidedAt: string | null
}

const UNDECIDED: ConsentRecord = {
  version: CONSENT_VERSION,
  decided: false,
  essential: true,
  preferences: false,
  analytics: false,
  decidedAt: null,
}

function writeCookie(record: ConsentRecord) {
  try {
    const value = `v${record.version}:p${record.preferences ? 1 : 0}:a${record.analytics ? 1 : 0}`
    document.cookie = `${COOKIE_NAME}=${value}; Max-Age=${COOKIE_MAX_AGE}; Path=/; SameSite=Lax`
  } catch {
    /* cookies blocked: the localStorage copy is still authoritative */
  }
}

function clearCookie() {
  document.cookie = `${COOKIE_NAME}=; Max-Age=0; Path=/; SameSite=Lax`
}

function readConsent(): ConsentRecord {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return UNDECIDED
    const parsed = JSON.parse(raw) as Partial<ConsentRecord>
    if (parsed.version !== CONSENT_VERSION || !parsed.decided) return UNDECIDED
    return {
      ...UNDECIDED,
      decided: true,
      preferences: Boolean(parsed.preferences),
      analytics: Boolean(parsed.analytics),
      decidedAt: parsed.decidedAt ?? null,
    }
  } catch {
    return UNDECIDED
  }
}

/** Keys that only exist when the user allowed preference storage. */
const PREFERENCE_KEYS = ["leaselens.sound.enabled", "leaselens.language", "leaselens.lastView"]

function purgePreferences() {
  for (const key of PREFERENCE_KEYS) {
    try {
      window.localStorage.removeItem(key)
    } catch {
      /* ignore */
    }
  }
}

interface ConsentValue {
  consent: ConsentRecord
  /** True once the visitor has answered; gates the banner. */
  decided: boolean
  preferencesOpen: boolean
  acceptAll: () => void
  essentialOnly: () => void
  save: (choices: { preferences: boolean; analytics: boolean }) => void
  openPreferences: () => void
  closePreferences: () => void
  reset: () => void
}

const ConsentContext = createContext<ConsentValue | null>(null)

export function ConsentProvider({ children }: { children: ReactNode }) {
  const [consent, setConsent] = useState<ConsentRecord>(readConsent)
  const [preferencesOpen, setPreferencesOpen] = useState(false)

  const persist = useCallback((choices: { preferences: boolean; analytics: boolean }) => {
    const next: ConsentRecord = {
      version: CONSENT_VERSION,
      decided: true,
      essential: true,
      preferences: choices.preferences,
      analytics: choices.analytics,
      decidedAt: new Date().toISOString(),
    }
    setConsent(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      /* storage disabled entirely: consent applies to this session only */
    }
    writeCookie(next)
    if (!choices.preferences) purgePreferences()
    setPreferencesOpen(false)
  }, [])

  useEffect(() => {
    // A visitor who blocked localStorage entirely still gets the cookie write
    // replayed, so the server-side record matches what they saw.
    if (consent.decided) writeCookie(consent)
  }, [consent])

  const value = useMemo<ConsentValue>(
    () => ({
      consent,
      decided: consent.decided,
      preferencesOpen,
      acceptAll: () => persist({ preferences: true, analytics: true }),
      essentialOnly: () => persist({ preferences: false, analytics: false }),
      save: persist,
      openPreferences: () => setPreferencesOpen(true),
      closePreferences: () => setPreferencesOpen(false),
      reset: () => {
        setConsent(UNDECIDED)
        try {
          window.localStorage.removeItem(STORAGE_KEY)
        } catch {
          /* ignore */
        }
        clearCookie()
        purgePreferences()
      },
    }),
    [consent, preferencesOpen, persist],
  )

  return <ConsentContext.Provider value={value}>{children}</ConsentContext.Provider>
}

export function useConsent(): ConsentValue {
  const value = useContext(ConsentContext)
  if (!value) throw new Error("useConsent must be used inside <ConsentProvider>")
  return value
}
