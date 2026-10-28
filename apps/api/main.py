"""Local API boundary: bounded workers and persistent results."""
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from typing import Literal
import json
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, HttpUrl, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from core.schemas import AnalysisRequest
from core.settings import ROOT, read_settings
from core.storage import JobStore
from core.model_catalog import available_models
from utils.pipeline import run_pipeline
from utils.safe_scraper import _validate_destination, FetchError

ORIGINS = ['http://localhost:5173', 'http://127.0.0.1:5173']
class StartRequest(BaseModel):
    client_url: HttpUrl
    competitor_1_url: HttpUrl
    competitor_2_url: HttpUrl
    model: str | None = Field(default=None, min_length=1, max_length=200)
class Job(BaseModel):
    id: str
    status: Literal['queued','running','complete','failed'] = 'queued'
    stage: str = 'Queued for analysis'
    created_at: str
    model: str | None = None
    report: dict | None = None
    sources: dict | None = None
    error: str | None = None

def error_message(exc):
    code = getattr(exc, 'code', None)
    if code == 429:
        return 'AI provider quota or rate limit reached. Check the Nimble key limit and account balance, then try again.'
    if code == 402:
        return 'OpenRouter credits or the Nimble key spending allowance are exhausted.'
    if code in (401, 403):
        return 'The AI provider rejected the Nimble key or project access. Check .env.nimble.'
    if isinstance(exc, TimeoutError) or 'timeout' in type(exc).__name__.lower():
        return 'The model request timed out. Retry the analysis.'
    if isinstance(exc, ValueError) and str(exc).startswith(('Client website could not', 'Configure a fresh')):
        return str(exc)[:250]
    return 'Analysis failed. Check network access, the selected model and the Nimble project quota.'

def create_app(database: Path | None = None) -> FastAPI:
    store = JobStore(database or ROOT / '.nimble' / 'reports.sqlite3')
    slots = BoundedSemaphore(4)
    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        app.state.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='nimble')
        yield
        app.state.executor.shutdown(wait=True)
    app = FastAPI(title='Nimble Local API', version='1.0.0', lifespan=lifespan)
    app.state.store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1','localhost','testserver'])
    app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=['GET','POST'], allow_headers=['Content-Type'])
    @app.middleware('http')
    async def local_browser_only(request: Request, call_next):
        if request.method == 'POST' and request.headers.get('origin') not in [None, *ORIGINS]:
            return JSONResponse({'detail':'This local API does not accept requests from that origin.'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response
    def run(id, request, model):
        try:
            store.update(id, status='running', stage='Fetching websites safely')
            pdf, report, sources = run_pipeline(request, lambda stage: store.update(id, stage=stage), model_name=model)
            store.update(id, pdf=pdf, status='complete', stage='Report ready', report=report.model_dump(),
                sources={key:value.model_dump(exclude={'body_text','internal_links'}) for key,value in sources.items()})
        except Exception as exc:
            print(f'Nimble job {id}: {type(exc).__name__}')
            store.update(id, status='failed', stage='Analysis failed', error=error_message(exc))
        finally:
            slots.release()
    @app.get('/')
    def root():
        return RedirectResponse('/docs')
    @app.get('/health')
    def health():
        return {'status':'ok','mode':'local','version':app.version}
    @app.get('/api/config')
    def config():
        settings = read_settings()
        return {'mode':'local','provider':settings.provider,'model':settings.model or 'Not configured',
            'has_api_key':bool(settings.api_key and settings.model),'max_parallel_jobs':2,
            'models':available_models(settings)}
    @app.post('/api/analyses', status_code=202, response_model=Job)
    def start(payload: StartRequest):
        inputs = payload.model_dump(exclude={'model'})
        urls = [str(value) for value in inputs.values()]
        if len(set(urls)) != 3:
            raise HTTPException(422, 'Enter three different URLs')
        try:
            for url in urls:
                _validate_destination(url)
        except FetchError as exc:
            raise HTTPException(422, str(exc)) from exc
        settings = read_settings()
        if not settings.api_key or not settings.model:
            raise HTTPException(503, 'Configure your fresh Nimble key and model before starting an analysis.')
        model = payload.model if payload.model is not None else settings.model
        if model not in {option['id'] for option in available_models(settings)}:
            raise HTTPException(422, 'Choose a model from the available catalog. Refresh the page if it has changed.')
        if not slots.acquire(blocking=False):
            raise HTTPException(429, 'The local queue is full. Wait for an existing analysis to finish.')
        job = Job(id=uuid.uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(), model=model)
        try:
            store.create(job.model_dump())
            app.state.executor.submit(run, job.id, AnalysisRequest(**inputs), model)
        except Exception:
            slots.release()
            raise
        return job
    @app.get('/api/analyses')
    def history():
        return [{'id':job['id'],'status':job['status'],'created_at':job['created_at'],
            'client_url':(job.get('report') or {}).get('client_url'), 'stage':job['stage']} for job in store.list()]
    @app.get('/api/analyses/{id}', response_model=Job)
    def get(id: str):
        job = store.get(id)
        if job is None:
            raise HTTPException(404, 'Unknown analysis ID')
        return job
    @app.get('/api/analyses/{id}/report.pdf')
    def pdf(id: str):
        result = store.pdf(id)
        if result is None:
            raise HTTPException(404, 'Report not ready')
        return Response(result, media_type='application/pdf', headers={'Content-Disposition':'attachment; filename="nimble-seo-report.pdf"'})
    @app.get('/api/benchmarks')
    def benchmarks():
        file = ROOT / '.nimble' / 'benchmarks' / 'latest.json'
        if not file.is_file():
            return {'recorded':False}
        try:
            data = json.loads(file.read_text())
        except (OSError, ValueError):
            raise HTTPException(503, 'The saved benchmark summary could not be read.')
        return {'recorded':True, 'summary':data.get('summary',{}), 'generated_at':data.get('generated_at'),
            'disclaimer':data.get('disclaimer'), 'attempts':len(data.get('runs',[]))}
    return app
app = create_app()
