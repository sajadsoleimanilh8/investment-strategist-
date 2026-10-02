/**
 * The API's shapes, mirrored.
 *
 * Hand-written rather than generated: the surface is small, and a type that
 * says what the client actually uses is more useful than one that restates
 * every field of every model. Anything wrong here shows up immediately in
 * `npm run build`, which is the point.
 */

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Me {
  id: number;
  email: string | null;
  telegram_id: number | null;
  locale: string;
  risk_profile: string | null;
  onboarded: boolean;
}

export interface ExpenseBreakdown {
  housing: number;
  food: number;
  transportation: number;
  education: number;
  bills: number;
  entertainment: number;
  shopping: number;
  other: number;
}

export const EXPENSE_CATEGORIES: (keyof ExpenseBreakdown)[] = [
  "housing", "food", "transportation", "bills",
  "education", "entertainment", "shopping", "other",
];

export interface FinancialProfileIn {
  monthly_income: number;
  income_type: string;
  expenses: ExpenseBreakdown;
  current_savings: number;
  debt: number;
  monthly_debt_payment: number;
  emergency_fund: number;
  risk_profile: string;
  planned_budget?: ExpenseBreakdown | null;
}

export interface Goal {
  id: number;
  name: string;
  target_amount: number;
  current_amount: number;
  deadline: string | null;
  priority: number;
  is_active: boolean;
  progress_pct: number;
  estimated_completion: string | null;
}

export interface FinancialTwin {
  income: number;
  /** Carried so the profile form can seed itself from what it was given
   * rather than defaulting, which is what used to reset it on every save. */
  income_type: string;
  expenses: ExpenseBreakdown;
  /** Null until the user sets one. The baseline the budget-stability
   * component is measured against; without it that component scores the
   * neutral 12/20 rather than anything the user did. */
  planned_budget: ExpenseBreakdown | null;
  monthly_expenses: number;
  essential_monthly_expenses: number;
  monthly_savings: number;
  current_savings: number;
  debt: number;
  monthly_debt_payment: number;
  emergency_fund: number;
  savings_rate: number;
  emergency_months: number;
  risk_profile: string;
}

export interface HealthComponent {
  name: string;
  points: number;
  max_points: number;
  detail: string;
}

export interface HealthScore {
  total: number;
  components: HealthComponent[];
}

export interface FinancialDNA {
  saving_discipline: string;
  emergency_readiness: string;
  debt_management: string;
  goal_discipline: string;
  budget_stability: string;
  financial_knowledge: string;
}

export interface TrendReport {
  symbol: string;
  latest_price: number;
  change_1d_pct: number;
  change_7d_pct: number;
  change_30d_pct: number;
  volatility_label: string;
  trend: string;
  disclaimer: string;
}

export interface MarketAsset {
  symbol: string;
  display_name: string;
  asset_class: string;
  trend: TrendReport | null;
}

export interface Summary {
  onboarded: boolean;
  twin: FinancialTwin | null;
  health: HealthScore | null;
  dna: FinancialDNA | null;
  goals: Goal[];
  watchlist: TrendReport[];
  topics_completed: number;
  market_disclaimer: string;
}

export interface ScenarioComparison {
  label: string;
  monthly_savings: number;
  projected_savings_end: number;
  goal_completion_pct: number | null;
  estimated_goal_date: string | null;
  emergency_months: number;
  health_score: number;
}

export interface SimulationOut {
  current: ScenarioComparison;
  scenario: ScenarioComparison;
  deltas: Record<string, number>;
  disclaimer: string;
}

export interface DecisionOut {
  purchase_price: number;
  savings_before: number;
  savings_after: number;
  emergency_months_before: number;
  emergency_months_after: number;
  health_score_before: number;
  health_score_after: number;
  affordable: boolean;
  disclaimer: string;
}

export interface TopicSummary {
  key: string;
  title: string;
  completed: boolean;
  quiz_score: number | null;
}

export interface TopicListOut {
  items: TopicSummary[];
  completed_count: number;
}

export interface Topic {
  key: string;
  title: string;
  explanation: string;
  example: string;
  common_mistake: string;
  quiz: { question: string; options: string[] };
  completed: boolean;
  quiz_score: number | null;
}

export interface QuizResult {
  correct: boolean;
  correct_idx: number;
  explanation: string;
  score: number;
  completed: boolean;
}

export interface AskResponse {
  text: string;
  /** local | hybrid | deterministic — shown so the user knows what answered. */
  source: string;
  used_context: Record<string, unknown>;
  disclaimer_applied: boolean;
}

export interface TelegramStatus {
  linked: boolean;
  telegram_id: number | null;
}

export interface LinkCode {
  /** Grouped for reading: ABCD-EFGH-JKMN. The bot accepts it either way. */
  code: string;
  expires_at: string;
  ttl_minutes: number;
  /** Null when the deployment has not been told the bot's username. */
  deep_link: string | null;
}

export interface ExpensePeriod {
  /** YYYY-MM. */
  period: string;
  expenses: ExpenseBreakdown;
  total: number;
  /** Housing, food, transportation and bills. */
  essential_total: number;
}

export interface ExpenseHistory {
  /** The window asked for, so "nothing recently" and "nothing ever" differ. */
  months: number;
  /** Oldest first. Only months that have records: a gap is a gap, not a zero. */
  periods: ExpensePeriod[];
}
