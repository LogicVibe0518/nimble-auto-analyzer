import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ThinkingOrb } from 'thinking-orbs'
import { ArrowDownToLine, ArrowRight, ArrowUpRight, Check, ChevronDown, CircleAlert, ExternalLink, RefreshCw } from 'lucide-react'
import { createAnalysis, fetchConfig, fetchJob, reportUrl, fetchHistory, fetchBenchmarks, type SavedAnalysis, type BenchmarkResults as BenchmarkData, type Config, type Job, type Report } from './lib/api'

type View = 'research' | 'history' | 'benchmarks' | 'notes'
type Urls = { client_url: string; competitor_1_url: string; competitor_2_url: string }
const fields: { key: keyof Urls; label: string; role: string; placeholder: string }[] = [
  { key: 'client_url', label: 'Your website', role: 'The starting point', placeholder: 'https://your-website.com' },
  { key: 'competitor_1_url', label: 'Competitor one', role: 'A different perspective', placeholder: 'https://competitor-one.com' },
  { key: 'competitor_2_url', label: 'Competitor two', role: 'The wider picture', placeholder: 'https://competitor-two.com' },
]
const phases = ['Acquire', 'Interpret', 'Verify', 'Export']
function phaseFor(stage: string) {
  const value = stage.toLowerCase()
  if (value.includes('render') || value.includes('report ready')) return 3
  if (value.includes('verif')) return 2
  if (value.includes('generat') || value.includes('grounded')) return 1
  return 0
}
function host(url: string) { try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url } }
function validUrls(urls: Urls) {
  try {
    const parsed = Object.values(urls).map(value => new URL(value.trim()))
    return parsed.every(url => ['http:', 'https:'].includes(url.protocol) && url.hostname && !url.username && !url.password && !url.hash)
      && new Set(parsed.map(url => { url.hash = ''; return url.href })).size === 3
  } catch { return false }
}
function SourceLink({ url }: { url: string }) {
  try {
    const target = new URL(url)
    if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password) return <span>{url}</span>
    return <a href={target.href} target="_blank" rel="noreferrer">{host(url)} <ExternalLink size={12} /></a>
  } catch { return <span>{url}</span> }
}

export function App() {
  const [view, setView] = useState<View>('research')
  const [urls, setUrls] = useState<Urls>({ client_url: '', competitor_1_url: '', competitor_2_url: '' })
  const [config, setConfig] = useState<Config | null>(null)
  const [selectedModel, setSelectedModel] = useState('')
  const [job, setJob] = useState<Job | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pollError, setPollError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const modelOptions = config?.models ?? []
  const chosenModel = selectedModel || config?.model || ''
  const modelAvailable = modelOptions.some(option => option.id === chosenModel)
  const modelPrice = modelOptions.find(option => option.id === chosenModel)
  const reportRef = useRef<HTMLElement>(null)
  const active = job?.status === 'queued' || job?.status === 'running'
  const busy = submitting || active
  const phase = phaseFor(job?.stage ?? '')
  const orb = !busy ? 'breathing' : (['searching', 'solving', 'working', 'composing'] as const)[phase]

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    async function check() {
      try { const next = await fetchConfig(); if (!cancelled) setConfig(next) }
      catch { if (!cancelled) setConfig(null) }
      finally { if (!cancelled) timer = setTimeout(check, 5000) }
    }
    void check()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [])

  useEffect(() => {
    if (!active || !job) return
    const id = job.id
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    async function check() {
      try {
        const next = await fetchJob(id)
        if (cancelled) return
        setJob(next)
        setPollError(null)
        if (next.status === 'queued' || next.status === 'running') timer = setTimeout(check, 1800)
      } catch (e) {
        if (!cancelled) setPollError(e instanceof Error ? e.message : 'Connection interrupted')
      }
    }
    void check()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [job?.id, active, retry])

  useEffect(() => {
    if (job?.status === 'complete' && view === 'research') reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [job?.status, view])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !validUrls(urls) || !config?.has_api_key || !modelAvailable) return
    setError(null); setPollError(null); setSubmitting(true); setJob(null)
    try {
      setJob(await createAnalysis({
        model: chosenModel, client_url: urls.client_url.trim(), competitor_1_url: urls.competitor_1_url.trim(), competitor_2_url: urls.competitor_2_url.trim(),
      }))
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to start analysis') }
    finally { setSubmitting(false) }
  }

  return <div className="studio">
    <a className="skip-link" href="#main">Skip to workspace</a>
    <header className="masthead">
      <a className="wordmark" href="#main" onClick={() => setView('research')} aria-label="Nimble research home"><span className="brand-mark" aria-hidden="true">n</span>nimble<span className="wordmark-label">research studio</span></a>
      <nav aria-label="Workspace">
        {(['research', 'history', 'benchmarks', 'notes'] as const).map(item => <button type="button" key={item} onClick={() => setView(item)} aria-current={view === item ? 'page' : undefined}>{item === 'research' ? 'Workspace' : item === 'notes' ? 'Field notes' : item === 'history' ? 'Saved reports' : 'Benchmarks'}</button>)}
      </nav>
      <span className="connection"><span className={config ? 'dot connected' : 'dot'} />{config ? 'Local API connected' : 'API disconnected'}</span>
    </header>

    <main id="main">
      {view === 'research' && <>
        <section className="intro">
          <div><div className="eyebrow">A closer look at your competition</div><h1>Find the space<br/>to <em>stand apart.</em></h1><p>Three pages. A shared frame of reference.<br/>Discover content opportunities you can trace to their source.</p></div>
          <div className="instrument" aria-label="Analysis status">
            <div className="instrument-top"><span className="eyebrow">Analysis engine</span><span className="instrument-code">N / 01</span></div>
            <div className="orb-mount"><ThinkingOrb state={orb} size={64} theme="dark" speed={.8} /></div>
            <div className="instrument-bottom"><span className="dot" /><span>{busy ? job?.stage ?? 'Submitting request' : job?.status === 'complete' ? 'Report assembled' : 'Ready when you are'}</span></div>
          </div>
        </section>

        <form className="research-form" onSubmit={submit}>
          <div className="section-line"><h2><span>01</span> Set your reference points</h2><span className="quiet">One page per website</span></div>
          <div className="site-grid">
            {fields.map((field, index) => <div className="site-column" key={field.key}>
              <div className="site-index"><span>{String(index + 1).padStart(2, '0')}</span><span>{index === 0 ? 'CLIENT' : 'COMPARISON'}</span></div>
              <label htmlFor={field.key}>{field.label}</label><p>{field.role}</p>
              <div className="site-input"><input id={field.key} type="url" value={urls[field.key]} required disabled={busy} placeholder={field.placeholder} onChange={event => setUrls(current => ({ ...current, [field.key]: event.target.value }))} autoComplete="off" spellCheck={false} /><ArrowUpRight size={16} aria-hidden="true" /></div>
            </div>)}
          </div>
          <div className="model-row">
            <div><label htmlFor="analysis-model">Choose your model</label><p id="model-help" className="quiet">This selection applies to your next report. Benchmarks compare models separately.</p></div>
            <div className="model-control"><select id="analysis-model" value={chosenModel} disabled={busy || !modelOptions.length} onChange={event => setSelectedModel(event.target.value)} aria-describedby="model-help model-price">
              {!modelAvailable && <option value={chosenModel}>{chosenModel || 'Waiting for model catalog'}</option>}
              {modelOptions.map(option => <option key={option.id} value={option.id}>{option.id}{option.id === config?.model ? ' · default' : ''}</option>)}
            </select><p className="quiet" id="model-price">{modelPrice?.input_per_million != null && modelPrice.output_per_million != null ? `Saved catalog: $${modelPrice.input_per_million.toLocaleString(undefined, { maximumFractionDigits: 4 })} input / $${modelPrice.output_per_million.toLocaleString(undefined, { maximumFractionDigits: 4 })} output per 1M tokens. Actual charges may differ.` : 'Pricing unavailable in the saved catalog.'} Availability depends on your OpenRouter account.</p></div>
          </div>
          <div className="launch-row">
            <div className="launch-note">{!config ? <><CircleAlert size={16} /> Connect the local backend to begin.</> : !config.has_api_key ? <><CircleAlert size={16} /> A fresh OpenRouter key is needed before your first analysis.</> : <><Check size={16} /> Ready to fetch pages and send their content to OpenRouter.</>}</div>
            <button className="launch" type="submit" disabled={!validUrls(urls) || busy || !config?.has_api_key || !modelAvailable}>{busy ? 'Research in progress' : 'Start research'}<ArrowRight size={18} /></button>
          </div>
          {config?.has_api_key && !modelAvailable && <p className="error" role="alert">The selected model is unavailable in the saved catalog. Choose another model, or restart the updated backend if no options appear.</p>}
          {error && <div className="error" role="alert">{error}</div>}
        </form>

        {job && <section className="run-status" aria-label="Analysis progress">
          <div className="section-line"><h2><span>02</span> {job.status === 'failed' ? 'Analysis stopped' : job.status === 'complete' ? 'Research complete' : 'Following the evidence'}</h2><span className="quiet">{job.status}</span></div>
          <ol className="phase-list">{phases.map((label, index) => <li key={label} className={job.status === 'complete' || (active && phase > index) ? 'done' : active && phase === index ? 'current' : ''}><span>{job.status === 'complete' || (active && phase > index) ? <Check size={14} /> : String(index + 1).padStart(2, '0')}</span>{label}</li>)}</ol>
          <p role="status" aria-live="polite">{job.stage}{job.model && <> · {job.model}</>}</p>
          {job.status === 'failed' && <div className="error" role="alert">{job.error ?? 'Analysis could not be completed.'}</div>}
          {pollError && <div className="error" role="alert">Status updates paused: {pollError}. Your job may still be running.<button type="button" className="text-button" onClick={() => { setPollError(null); setRetry(value => value + 1) }}><RefreshCw size={14} /> Reconnect</button><button type="button" className="text-button" onClick={() => { setJob(null); setPollError(null) }}>Dismiss local view</button></div>}
        </section>}

        {job?.report && <section className="report" ref={reportRef}>
          <div className="section-line"><h2><span>03</span> The research brief</h2><a className="export-button" href={reportUrl(job.id)} download><ArrowDownToLine size={16} />Download PDF</a></div>
          <div className="report-meta"><span>{job.report.model_used}</span><span>Prompt {job.report.prompt_version}</span><span>{job.report.generated_at_iso ? new Date(job.report.generated_at_iso).toLocaleString() : ''}</span></div>
          <p className="summary">{job.report.executive_summary}</p>
          <div className="report-counts"><span><strong>{job.report.keyword_gaps.length}</strong> keyword opportunities</span><span><strong>{job.report.content_strategy_insights.length}</strong> content recommendations</span><span><strong>{Object.values(job.sources ?? {}).filter(source => source.success).length}/3</strong> pages retrieved</span></div>
          <Findings report={job.report} />
          <section className="meta-section"><div><div className="eyebrow">Search result copy</div><h3>A clearer first impression.</h3><p className="quiet">A proposed rewrite for this page.</p></div><div><div className="meta-label">Current description</div><p className="old-meta">{job.report.meta_description_suggestion.current_meta || 'No description returned'}</p><div className="meta-label">Suggested description <span>{job.report.meta_description_suggestion.character_count} characters</span></div><p className="new-meta">{job.report.meta_description_suggestion.suggested_meta}</p><p className="quiet">{job.report.meta_description_suggestion.reasoning}</p></div></section>
          <section className="source-section"><h3>Sources & limitations</h3><div className="sources">{Object.entries(job.sources ?? {}).map(([label, source]) => <div className="source-row" key={label}><span>{label.replaceAll('_', ' ')}</span><SourceLink url={source.url}/><span>{source.success ? `${source.word_count ?? 0} words retrieved` : source.error_message || 'Unavailable'}</span></div>)}</div><p className="quiet">Excerpt checks confirm that words appeared in retrieved text. They do not establish that every recommendation is correct.</p>{job.report.flagged_uncertainties.length > 0 && <ul className="limitations">{job.report.flagged_uncertainties.map((note, index) => <li key={index}>{note}</li>)}</ul>}</section>
        </section>}

        {!job && <div className="workspace-foot"><span>Read the page. Question the claim. Keep the evidence.</span><button type="button" className="text-button" onClick={() => setView('notes')}>How the research works <ArrowUpRight size={14}/></button></div>}
      </>}

      {view === 'history' && <SavedReports busy={busy} onOpen={saved => { setJob(saved); setView('research') }} />}

      {view === 'benchmarks' && <section className="secondary">
        <div className="eyebrow">Evaluation notebook</div><h1>Evidence before<br/><em>preference.</em></h1><p className="secondary-intro">A model earns its place through the same cases, the same prompt, and a review of what it actually gets right.</p>
        <RecordedBenchmarks />
        <div className="section-line"><h2>Proposed pilot protocol</h2><span className="quiet">Not executed</span></div>
        <div className="protocol-grid"><div><strong>10</strong><span>frozen website triplets</span></div><div><strong>2</strong><span>available OpenRouter models</span></div><div><strong>2</strong><span>repeats per case</span></div><div><strong>40</strong><span>base model calls</span></div></div>
        <div className="evaluation-table" role="table" aria-label="Planned evaluation measures"><div className="evaluation-row table-head" role="row"><span role="columnheader">Measure</span><span role="columnheader">What it tells us</span></div>{[
          ['Valid output', 'Does the first response match the report schema? Track repaired responses separately.'],
          ['Evidence & coverage', 'Are quotes authentic, are gaps absent from the client page, and are known opportunities found?'],
          ['Recommendation quality', 'Blind human review of factual support, usefulness, specificity and unsupported assumptions.'],
          ['Time & usage', 'Median latency, individual runs, token usage and a dated cost estimate.'],
          ['Failure behaviour', 'Missing sources, prompt injection attempts, rate limits, timeouts and invalid responses.'],
        ].map(([name, detail]) => <div role="row" className="evaluation-row" key={name}><span role="cell">{name}</span><span role="cell">{detail}</span></div>)}</div>
        <p className="quiet benchmark-foot">Live benchmarks require a configured key and a confirmed run budget. No model calls are made by this page.</p>
      </section>}

      {view === 'notes' && <section className="secondary">
        <div className="eyebrow">Field notes / method</div><h1>A short path.<br/><em>A visible trail.</em></h1><p className="secondary-intro">Nimble compares the content of three supplied pages. Each step has a purpose and a limit.</p>
        <div className="method-list">{[
          ['Acquire', 'Fetch the three URLs with network restrictions, bounded downloads and robots checks. Inaccessible pages are reported as unavailable.'],
          ['Interpret', 'Send extracted text, headings and metadata to OpenRouter. The app runs on your Mac; live inference still uses an external service.'],
          ['Verify', 'Check quoted excerpts against the retrieved pages and remove unmatched findings. A matching quote is evidence of provenance, not proof of a sound recommendation.'],
          ['Deliver', 'Read the research brief, inspect the supporting excerpts and download the PDF. Completed reports are saved locally and remain available after the backend restarts. Interrupted jobs are marked failed so you can submit them again.'],
        ].map(([name, detail], index) => <article key={name}><span className="method-number">0{index + 1}</span><h2>{name}</h2><p>{detail}</p></article>)}</div>
        <div className="scope-note"><h3>The boundary of this release</h3><p>Single-page content comparison. No search-volume data, backlink index, ranking positions, full-site crawl or JavaScript browser rendering. Findings describe the supplied pages, not a whole business.</p></div>
      </section>}
    </main>
    <footer className="studio-footer"><span>NIMBLE INFORMATICS</span><span>Independent observations. Traceable sources.</span><span>LOCAL / v1.0</span></footer>
  </div>
}

function Findings({ report }: { report: Report }) {
  const [tab, setTab] = useState<'keywords' | 'content'>('keywords')
  return <section className="findings">
    <div className="finding-tabs" role="tablist" aria-label="Report findings"><button id="keywords-tab" role="tab" type="button" aria-selected={tab === 'keywords'} aria-controls="findings-panel" onClick={() => setTab('keywords')}>Keyword opportunities <span>{report.keyword_gaps.length}</span></button><button id="content-tab" role="tab" type="button" aria-selected={tab === 'content'} aria-controls="findings-panel" onClick={() => setTab('content')}>Content recommendations <span>{report.content_strategy_insights.length}</span></button></div>
    <div id="findings-panel" role="tabpanel" aria-labelledby={`${tab}-tab`}>
      {tab === 'keywords' ? report.keyword_gaps.length ? report.keyword_gaps.map((gap, index) => <details className="finding" key={`gap-${index}`}><summary><span className="finding-index">{String(index + 1).padStart(2, '0')}</span><span className="finding-title">{gap.keyword}<small>{gap.which_competitor.replaceAll('_', ' ')}</small></span><span className="confidence">{gap.confidence} confidence</span><ChevronDown size={16}/></summary><div className="finding-body"><p>{gap.opportunity_rationale}</p><div className="meta-label">Quoted evidence</div><blockquote>{gap.source_quote}</blockquote></div></details>) : <p className="empty-copy">No keyword findings survived the excerpt checks.</p> : report.content_strategy_insights.length ? report.content_strategy_insights.map((insight, index) => <details className="finding" key={`insight-${index}`}><summary><span className="finding-index">{String(index + 1).padStart(2, '0')}</span><span className="finding-title">{insight.insight}</span><span className="confidence">{insight.confidence} confidence</span><ChevronDown size={16}/></summary><div className="finding-body"><div className="meta-label">Recommended action</div><p>{insight.recommended_action}</p>{insight.source_quote && <><div className="meta-label">Quoted evidence</div><blockquote>{insight.source_quote}</blockquote>{insight.source_url && <SourceLink url={insight.source_url}/>}</>}</div></details>) : <p className="empty-copy">No content recommendations survived the excerpt checks.</p>}
    </div>
  </section>
}

function SavedReports({ onOpen, busy }: { onOpen: (job: Job) => void; busy: boolean }) {
  const [rows, setRows] = useState<SavedAnalysis[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true
    fetchHistory().then(result => { if (active) setRows(result) }).catch(() => { if (active) setError('Could not load saved reports. Check the backend connection.') }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  async function open(id: string) {
    try { onOpen(await fetchJob(id)) } catch { setError('This report could not be opened. Check the backend connection.') }
  }
  return <section className="secondary"><div className="eyebrow">Your research archive</div><h1>Keep the<br/><em>useful findings.</em></h1><p className="secondary-intro">The latest 30 analyses saved on this Mac. Downloads remain available after a restart.</p>{busy && <p className="quiet">Wait for the current analysis to finish before opening another report.</p>}{error && <p role="alert" className="error">{error}</p>}{loading ? <p role="status">Loading saved reports…</p> : !rows.length ? <p className="empty-copy">No analyses saved yet.</p> : <div className="saved-list">{rows.map(row => <button disabled={busy} className="saved-row" type="button" key={row.id} onClick={() => void open(row.id)}><span>{row.client_url ? host(row.client_url) : 'Analysis'}<small>{new Date(row.created_at).toLocaleString()}</small></span><span>{row.status}</span><ArrowUpRight size={16}/></button>)}</div>}</section>
}

function RecordedBenchmarks() {
  const [data, setData] = useState<BenchmarkData | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let active = true
    fetchBenchmarks().then(result => { if (active) setData(result) }).catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [])
  if (error) return <p className="error" role="alert">Could not load saved benchmark results. Check the backend connection.</p>
  if (!data) return <p className="quiet" role="status">Checking saved benchmark results…</p>
  if (!data.recorded) return <div className="benchmark-status"><div className="empty-symbol">—</div><div><h2>No live comparison recorded</h2><p>The existing offline check validates one synthetic fixture. It does not measure a model's SEO quality.</p></div></div>
  return <section className="recorded-benchmarks"><h2>Latest saved comparison</h2><p className="quiet">{data.disclaimer}</p><div className="benchmark-table-wrap"><table><thead><tr><th>Model</th><th>Valid reports</th><th>First pass</th><th>Repairs</th><th>Median time</th><th>Reported cost</th></tr></thead><tbody>{Object.entries(data.summary ?? {}).map(([model, result]) => <tr key={model}><th>{model}</th><td>{result.successes}/{result.attempts}</td><td>{result.first_pass_valid}</td><td>{result.repairs}</td><td>{result.median_seconds == null ? '—' : `${result.median_seconds.toFixed(2)} s`}</td><td>{result.reported_cost_credits == null ? 'Unavailable' : `${result.reported_cost_credits.toFixed(4)} credits${result.cost_complete ? '' : ' (partial)'}`}</td></tr>)}</tbody></table></div><p className="quiet">Recorded {data.generated_at ? new Date(data.generated_at).toLocaleString() : 'date unavailable'}. Quality still requires review of the underlying cases and outputs.</p></section>
}
