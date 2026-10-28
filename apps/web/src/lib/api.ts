export type Source = {
  url: string; success: boolean; title: string | null; meta_description: string | null;
  word_count: number | null; status_code: number | null; error_message: string | null;
  headings: Record<string, string[]>; scraper_used: string;
}
export type KeywordGap = { keyword: string; which_competitor: string; source_quote: string; opportunity_rationale: string; confidence: string }
export type Insight = { source_url?: string | null; insight: string; source_quote: string | null; recommended_action: string; confidence: string }
export type Report = {
  client_url: string; competitor_urls: string[]; executive_summary: string;
  keyword_gaps: KeywordGap[];
  content_strategy_insights: Insight[];
  meta_description_suggestion: { current_meta: string | null; suggested_meta: string; character_count: number; reasoning: string; keywords_targeted: string[] };
  flagged_uncertainties: string[]; generated_at_iso: string; model_used: string; prompt_version: string;
}
export type Job = {
  id: string; status: 'queued' | 'running' | 'complete' | 'failed';
  stage: string; created_at: string; model?: string | null; report: Report | null;
  sources: Record<string, Source> | null; error: string | null
}
export type ModelOption = { id: string; input_per_million: number | null; output_per_million: number | null }
export type Config = { models?: ModelOption[]; mode: string; model: string; has_api_key: boolean; max_parallel_jobs: number }

async function decode<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body) } catch { /* return status */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
export async function fetchConfig(): Promise<Config> { return decode(await fetch('/api/config')) }
export async function createAnalysis(urls: { client_url: string; competitor_1_url: string; competitor_2_url: string; model: string }): Promise<Job> {
  return decode(await fetch('/api/analyses', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(urls) }))
}
export async function fetchJob(id: string): Promise<Job> { return decode(await fetch(`/api/analyses/${encodeURIComponent(id)}`, {cache: 'no-store'})) }
export function reportUrl(id: string): string { return `/api/analyses/${encodeURIComponent(id)}/report.pdf` }

export type SavedAnalysis = { id: string; status: string; created_at: string; client_url: string | null; stage: string }
export type BenchmarkSummary = { reported_cost_credits?: number | null; cost_complete?: boolean; attempts: number; successes: number; first_pass_valid: number; repairs: number; median_seconds: number | null; mean_grounding_rate: number | null }
export type BenchmarkResults = { recorded: boolean; summary?: Record<string, BenchmarkSummary>; generated_at?: string; disclaimer?: string }
export async function fetchHistory(): Promise<SavedAnalysis[]> { return decode(await fetch('/api/analyses', {cache:'no-store'})) }
export async function fetchBenchmarks(): Promise<BenchmarkResults> { return decode(await fetch('/api/benchmarks', {cache:'no-store'})) }
