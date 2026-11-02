/**
 * The review currently open in the workspace.
 *
 * App-level rather than page-level because History, Review and the document
 * pane all need it, and the "origin" decides where the source PDF comes from:
 * a File the browser still holds, a demo lease URL, or a saved report whose
 * server session may already have expired.
 */

import { createContext, useContext, useMemo, useState } from "react"
import type { ReactNode } from "react"
import type { AnalysisReport } from "./types"

export type ReviewOrigin =
  | { kind: "upload"; file: File }
  | { kind: "sample"; sampleId: string }
  | { kind: "history" }

interface ReviewValue {
  report: AnalysisReport | null
  origin: ReviewOrigin | null
  open: (report: AnalysisReport, origin: ReviewOrigin) => void
  clear: () => void
}

const ReviewContext = createContext<ReviewValue | null>(null)

export function ReviewProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ report: AnalysisReport | null; origin: ReviewOrigin | null }>(
    { report: null, origin: null },
  )

  const value = useMemo<ReviewValue>(
    () => ({
      report: state.report,
      origin: state.origin,
      open: (report, origin) => setState({ report, origin }),
      clear: () => setState({ report: null, origin: null }),
    }),
    [state],
  )

  return <ReviewContext.Provider value={value}>{children}</ReviewContext.Provider>
}

export function useReview(): ReviewValue {
  const value = useContext(ReviewContext)
  if (!value) throw new Error("useReview must be used inside <ReviewProvider>")
  return value
}
