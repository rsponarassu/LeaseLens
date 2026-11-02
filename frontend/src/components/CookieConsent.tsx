import { AnimatePresence, motion } from "framer-motion"
import { Cookie, ShieldCheck } from "lucide-react"
import { useState } from "react"
import { useConsent } from "../lib/consent"
import { Link } from "../lib/router"
import { useToast } from "../lib/toast"

/**
 * Consent banner.
 *
 * Shown until the visitor answers, and reopenable from the security page and
 * the account menu. "Essential only" is a real choice: it clears the preference
 * keys that are already on the device.
 */
export function CookieConsent() {
  const { decided, consent, acceptAll, essentialOnly, save, preferencesOpen, openPreferences, closePreferences } =
    useConsent()
  const toast = useToast()
  const [preferences, setPreferences] = useState(consent.preferences)
  const [analytics, setAnalytics] = useState(consent.analytics)

  const visible = !decided || preferencesOpen

  const choose = (label: string, action: () => void) => {
    action()
    toast.success(label, { title: "Cookie preferences saved", sound: false })
  }

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="fixed inset-x-0 bottom-0 z-[65] p-3 sm:p-4"
          initial={{ y: 120, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 120, opacity: 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 34 }}
          role="dialog"
          aria-modal="false"
          aria-label="Cookie preferences"
        >
          <div className="consent-card mx-auto max-w-4xl">
            <div className="flex items-start gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/[0.05] text-cobalt">
                <Cookie size={17} />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-white">
                  {preferencesOpen ? "Choose what you allow" : "Your lease, your call"}
                </p>
                <p className="mt-1 text-[12px] leading-5 text-white/50">
                  We use strictly necessary storage to keep you signed in and to remember this
                  choice. Preference storage (sound, language) and analytics are optional.{" "}
                  <Link to="/app/security" className="text-cobalt underline-offset-2 hover:underline">
                    What we never store
                  </Link>
                  .
                </p>
              </div>
            </div>

            {preferencesOpen ? (
              <div className="mt-4 grid gap-2">
                <Row
                  title="Strictly necessary"
                  detail="Sign-in session and this consent record. Always on."
                  checked
                  disabled
                />
                <Row
                  title="Preferences"
                  detail="Sound on/off and your language choice, stored on this device."
                  checked={preferences}
                  onChange={setPreferences}
                />
                <Row
                  title="Analytics"
                  detail="Anonymous usage counts. Not enabled in this build — you can still say no."
                  checked={analytics}
                  onChange={setAnalytics}
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    className="primary-button h-10! px-4! text-xs!"
                    type="button"
                    onClick={() => choose("Your preferences were applied.", () => save({ preferences, analytics }))}
                  >
                    Save preferences
                  </button>
                  <button className="ghost-button" type="button" onClick={closePreferences}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <button
                  className="primary-button h-10! px-4! text-xs!"
                  type="button"
                  onClick={() => choose("All optional storage enabled.", acceptAll)}
                >
                  <ShieldCheck size={15} /> Accept all
                </button>
                <button
                  className="ghost-button"
                  type="button"
                  onClick={() => choose("Optional storage disabled and cleared.", essentialOnly)}
                >
                  Essential only
                </button>
                <button className="ghost-button" type="button" onClick={openPreferences}>
                  Choose individually
                </button>
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Row({
  title,
  detail,
  checked,
  disabled = false,
  onChange,
}: {
  title: string
  detail: string
  checked: boolean
  disabled?: boolean
  onChange?: (next: boolean) => void
}) {
  return (
    <label
      className={`flex cursor-pointer items-start justify-between gap-4 rounded-xl border border-white/8 bg-black/20 p-3 ${
        disabled ? "cursor-default opacity-80" : ""
      }`}
    >
      <span className="min-w-0">
        <span className="block text-xs font-semibold text-white">{title}</span>
        <span className="mt-0.5 block text-[11px] leading-4 text-white/40">{detail}</span>
      </span>
      <span className={`switch ${checked ? "on" : ""}`} aria-hidden="true">
        <span />
        <input
          type="checkbox"
          className="sr-only"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.checked)}
        />
      </span>
    </label>
  )
}
