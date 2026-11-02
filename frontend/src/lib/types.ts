/**
 * Wire types for the LeaseLens API.
 *
 * These mirror `app/models/*.py` on the backend. They are deliberately narrow:
 * only the fields the UI renders. Anything the server adds later is ignored
 * rather than breaking the build.
 */

export type ClauseCategory =
  | "deposit"
  | "lock_in"
  | "eviction"
  | "rent_hike"
  | "entry_rights"
  | "maintenance"
  | "general"

export type Severity = "critical" | "high" | "moderate" | "low" | "info"
export type RiskLevel = "low" | "moderate" | "elevated" | "high" | "critical"
export type RiskColor = "red" | "amber" | "green" | "grey"
export type FindingStatus = "violation" | "compliant" | "not_applicable" | "informational"
export type ExtractionMethod = "text_layer" | "ocr" | "hybrid"
export type AnalysisMode = "llm_assisted" | "offline_heuristic" | "llm_degraded"
export type StatuteVerification = "verified" | "indicative"

export const CATEGORY_LABELS: Record<ClauseCategory, string> = {
  deposit: "Security deposit",
  lock_in: "Lock-in",
  eviction: "Eviction & notice",
  rent_hike: "Rent revision",
  entry_rights: "Entry rights",
  maintenance: "Maintenance",
  general: "General",
}

export const SEVERITY_RANK: Record<Severity, number> = {
  critical: 5,
  high: 4,
  moderate: 3,
  low: 2,
  info: 1,
}

export interface BoundingBox {
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface StatuteInfo {
  act: string
  short_name: string
  act_number: string
  jurisdiction: string
  year: number
  source_url: string | null
  as_at: string | null
  note: string | null
}

export interface StatuteReference {
  act: string
  section: string
  heading: string
  quote: string
  url: string | null
  verification: StatuteVerification
}

export interface ClauseEntities {
  deposit_months?: number | null
  deposit_amount_inr?: number | null
  deposit_refund_days?: number | null
  deposit_non_refundable?: boolean | null
  deposit_forfeiture_on_early_exit?: boolean | null
  lock_in_months?: number | null
  lock_in_penalty_months?: number | null
  lock_in_penalty_inr?: number | null
  notice_period_days?: number | null
  landlord_eviction_notice_days?: number | null
  allows_immediate_eviction?: boolean | null
  eviction_grounds?: string[]
  double_rent_penalty?: boolean | null
  rent_increase_percent?: number | null
  rent_increase_frequency_months?: number | null
  rent_increase_notice_days?: number | null
  rent_increase_unilateral?: boolean | null
  rent_increase_during_fixed_term?: boolean | null
  entry_notice_hours?: number | null
  unrestricted_entry?: boolean | null
  landlord_retains_keys?: boolean | null
  entry_outside_allowed_hours?: boolean | null
  tenant_pays_structural_repairs?: boolean | null
  tenant_pays_all_repairs?: boolean | null
  landlord_repair_duty_waived?: boolean | null
  repair_deduction_allowed?: boolean | null
  essential_services_cutoff_allowed?: boolean | null
  mentions_rent_authority?: boolean | null
  agreement_unregistered?: boolean | null
  original_agreement_withheld?: boolean | null
  field_sources?: Record<string, string>
}

export interface RuleEvaluation {
  rule_id: string
  clause_id: string
  category: ClauseCategory
  status: FindingStatus
  severity: Severity
  observed_value: unknown
  threshold: unknown
  message: string
  penalty_group: string
  penalty_points: number
  is_violation: boolean
}

export interface FixItKit {
  explanation_en: string
  explanation_ta: string
  counter_clause: string
  email_subject: string
  email_body: string
  negotiation_tips: string[]
  languages: string[]
}

export interface ClauseFinding {
  clause_id: string
  heading: string
  category: ClauseCategory
  page_number: number
  bbox: number[] | null
  raw_text: string
  status: FindingStatus
  severity: Severity
  risk_color: RiskColor
  headline: string
  category_confidence: number
  extracted: ClauseEntities
  violations: RuleEvaluation[]
  compliant_rules: string[]
  statute_references: StatuteReference[]
  fix: FixItKit | null
}

export interface CategoryRisk {
  category: ClauseCategory
  score: number
  weight: number
  contribution: number
  violation_count: number
  highest_severity: Severity | null
  weight_note: string | null
}

export interface RiskBand {
  level: RiskLevel
  min_score: number
  max_score: number
  label: string
}

export interface RiskAssessment {
  overall_score: number
  risk_level: RiskLevel
  band_label: string
  headline: string
  category_scores: CategoryRisk[]
  violation_count: number
  compliant_count: number
  analysed_category_count: number
  top_drivers: string[]
  scoring_version: string
  methodology: string
}

export interface ExtractionSummary {
  file_name: string
  file_size_bytes: number
  page_count: number
  total_chars: number
  extraction_method: ExtractionMethod
  ocr_used: boolean
  mean_chars_per_page: number
  warnings: string[]
  pages: { page_number: number; chars: number; lines: number; ocr: boolean }[]
}

export interface EngineMetadata {
  analysis_mode: AnalysisMode
  llm_provider: string
  llm_model: string | null
  llm_calls: number
  llm_failures: number
  llm_latency_ms: number
  classification_source_breakdown: Record<string, number>
  clause_count: number
  duration_ms: number
  warnings: string[]
}

export interface EmailDraft {
  subject: string
  body: string
  recipient_hint: string
}

export interface AnalysisReport {
  session_id: string
  sample_id: string | null
  file_name: string
  file_size_bytes: number
  page_count: number
  created_at: string
  cache_hit: boolean
  statute: StatuteInfo
  risk: RiskAssessment
  findings: ClauseFinding[]
  extraction: ExtractionSummary
  engine: EngineMetadata
  annotated_pdf_url: string
  summary_email: EmailDraft | null
  disclaimer: string
}

export interface SampleLease {
  sample_id: string
  title: string
  tenant_persona: string
  property_description: string
  scenario: string
  expected_risk_level: RiskLevel
  pdf_url: string
  analysis: AnalysisReport
}

export interface AnalysisSummary {
  session_id: string
  sample_id: string | null
  file_name: string
  page_count: number
  overall_score: number
  risk_level: RiskLevel
  violation_count: number
  created_at: string
  top_drivers: string[]
}

export interface RuleDefinition {
  id: string
  category: ClauseCategory
  title: string
  severity: Severity
  field: string
  operator: string
  value: unknown
  value_max: number | null
  unit: string | null
  penalty_group: string | null
  applies_to: ClauseCategory[]
  tags: string[]
  explanation: string
  tamil: string
  counter_clause: string
  negotiation_tip: string | null
  statute: StatuteReference
}

export interface RuleCatalogue {
  statute: StatuteInfo
  scoring_version: string
  severity_points: Record<string, number>
  category_importance: Record<string, number>
  breadth_bonus_per_violation: number
  breadth_bonus_cap: number
  risk_bands: RiskBand[]
  rule_count: number
  rules: RuleDefinition[]
}

export interface ComponentHealth {
  status: string
  detail: Record<string, unknown>
}

export interface HealthResponse {
  status: string
  version: string
  environment: string
  uptime_seconds: number
  statute: string
  components: Record<string, ComponentHealth>
}
