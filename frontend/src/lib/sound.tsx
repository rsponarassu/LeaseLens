/**
 * UI sound effects.
 *
 * Synthesised with the Web Audio API rather than shipped as audio files: a
 * 4-note kit would otherwise cost more bandwidth than the whole font stack,
 * and this way the tone can follow the theme. One AudioContext is reused for
 * the life of the page (creating one per sound leaks contexts in Safari) and
 * is resumed lazily on the first user gesture, which is what the autoplay
 * policy actually requires.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"
import type { ReactNode } from "react"
import { useConsent } from "./consent"

export type SoundKind = "tap" | "success" | "error" | "notify"

const STORAGE_KEY = "leaselens.sound.enabled"

interface SoundValue {
  enabled: boolean
  setEnabled: (next: boolean) => void
  toggle: () => void
  play: (kind: SoundKind) => void
}

const SoundContext = createContext<SoundValue | null>(null)

interface Tone {
  type: OscillatorType
  /** [from, to] frequency in Hz. */
  sweep: [number, number]
  duration: number
  gain: number
  delay?: number
}

const KIT: Record<SoundKind, Tone[]> = {
  // Short, dry click for navigation and selection.
  tap: [{ type: "triangle", sweep: [220, 165], duration: 0.1, gain: 0.02 }],
  // Rising major third: unambiguous "it worked".
  success: [
    { type: "sine", sweep: [523.25, 659.25], duration: 0.16, gain: 0.035 },
    { type: "sine", sweep: [783.99, 1046.5], duration: 0.22, gain: 0.022, delay: 0.09 },
  ],
  // Two falling low tones: reads as "no" without being alarming.
  error: [
    { type: "sawtooth", sweep: [220, 170], duration: 0.14, gain: 0.026 },
    { type: "sawtooth", sweep: [170, 120], duration: 0.18, gain: 0.022, delay: 0.13 },
  ],
  // Single soft bell for background notices.
  notify: [
    { type: "sine", sweep: [880, 880], duration: 0.12, gain: 0.02 },
    { type: "sine", sweep: [1318.5, 1318.5], duration: 0.14, gain: 0.01, delay: 0.05 },
  ],
}

function readPreference(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== "false"
  } catch {
    return true
  }
}

export function SoundProvider({ children }: { children: ReactNode }) {
  const { consent } = useConsent()
  const [enabled, setEnabledState] = useState(readPreference)
  const contextRef = useRef<AudioContext | null>(null)
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled

  // The choice is a preference, not a necessity: honour it in memory even when
  // the visitor declined preference storage, but only write it once allowed.
  useEffect(() => {
    if (!consent.preferences) return
    try {
      window.localStorage.setItem(STORAGE_KEY, String(enabled))
    } catch {
      /* private mode: preference simply does not persist */
    }
  }, [enabled, consent.preferences])

  const play = useCallback((kind: SoundKind) => {
    if (!enabledRef.current) return
    const AudioContextClass =
      window.AudioContext ??
      (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!AudioContextClass) return

    if (!contextRef.current) contextRef.current = new AudioContextClass()
    const context = contextRef.current
    if (context.state === "suspended") void context.resume()

    const now = context.currentTime
    for (const tone of KIT[kind]) {
      const start = now + (tone.delay ?? 0)
      const oscillator = context.createOscillator()
      const gain = context.createGain()
      oscillator.connect(gain)
      gain.connect(context.destination)

      oscillator.type = tone.type
      oscillator.frequency.setValueAtTime(tone.sweep[0], start)
      if (tone.sweep[0] !== tone.sweep[1]) {
        oscillator.frequency.exponentialRampToValueAtTime(tone.sweep[1], start + tone.duration)
      }

      // Ramp in/out to avoid the click a hard start would produce.
      gain.gain.setValueAtTime(0.0001, start)
      gain.gain.exponentialRampToValueAtTime(tone.gain, start + 0.012)
      gain.gain.exponentialRampToValueAtTime(0.0001, start + tone.duration)

      oscillator.start(start)
      oscillator.stop(start + tone.duration + 0.02)
    }
  }, [])

  const setEnabled = useCallback((next: boolean) => setEnabledState(next), [])
  const toggle = useCallback(() => setEnabledState((value) => !value), [])

  const value = useMemo(
    () => ({ enabled, setEnabled, toggle, play }),
    [enabled, setEnabled, toggle, play],
  )

  useEffect(() => {
    return () => {
      void contextRef.current?.close()
      contextRef.current = null
    }
  }, [])

  return <SoundContext.Provider value={value}>{children}</SoundContext.Provider>
}

export function useSound(): SoundValue {
  const value = useContext(SoundContext)
  if (!value) throw new Error("useSound must be used inside <SoundProvider>")
  return value
}
