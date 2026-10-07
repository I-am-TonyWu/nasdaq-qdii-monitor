from pathlib import Path
from datetime import datetime, timezone
import hashlib
from fastapi import FastAPI,HTTPException,Query
from fastapi.responses import FileResponse,JSONResponse,HTMLResponse
from fastapi.staticfiles import StaticFiles
from .settings import ROOT,HOME,DATA
from .storage import latest,history,get_snapshot
from .presentation import for_display

app=FastAPI(title='Nasdaq & QDII Monitor',docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def safe_headers(request, call_next):
    if request.method not in ('GET','HEAD'):
        return JSONResponse({'detail':'只读服务'},status_code=405)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'self'; base-uri 'self'"
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api') else 'no-cache'
    return response

@app.get('/')
def index():
    return FileResponse(ROOT/'web'/'index.html')

@app.get('/api/health')
def health():
    snapshot=latest()
    return {'status':'ok','application':'nasdaq-qdii-monitor','version':'0.5.0',
            'home_id':hashlib.sha256(str(HOME).lower().encode('utf-8')).hexdigest()[:24],
            'has_snapshot':bool(snapshot),'readonly':True}

@app.get('/api/snapshot')
def snapshot():
    result=latest()
    if not result:
        raise HTTPException(503,'尚无采集快照，请在本机运行采集')
    return for_display(result)

@app.get('/api/history')
def snapshot_history(limit:int=Query(30,ge=1,le=100)):
    return history(limit)

@app.get('/api/valuation-view')
def valuation_view(metric:str=Query('ttm',pattern='^(ttm|forward|pb|VXN|VIX|FGI)$'),
                   dataset:str=Query('reference',pattern='^(official|reference|publisher)$'),
                   years:int=Query(1,ge=0,le=20),snapshot_id:str|None=Query(None,pattern='^[0-9a-f]{20}$')):
    from .valuation_views import view
    if dataset=='publisher' and metric!='forward':raise HTTPException(422,'此源站序列仅提供Forward PE')
    if years not in (0,1,3,5,10,20):raise HTTPException(422,'不支持此估值区间')
    result=get_snapshot(snapshot_id) if snapshot_id else latest()
    if not result:raise HTTPException(503,'尚无采集快照')
    return view(for_display(result),metric,dataset,years)

@app.get('/api/history/{snapshot_id}')
def historical_snapshot(snapshot_id:str):
    if len(snapshot_id)!=20 or not all(c in '0123456789abcdef' for c in snapshot_id):
        raise HTTPException(404,'快照不存在')
    result=get_snapshot(snapshot_id)
    if not result:
        raise HTTPException(404,'快照不存在')
    return result

@app.get('/api/report-preview')
def report_preview():
    from .reports import render
    snapshot=latest()
    if not snapshot:
        raise HTTPException(503,'尚无快照')
    # Deterministic read-only render, no persistence or send operation.
    return HTMLResponse(render(for_display(snapshot))[1])

app.mount('/assets',StaticFiles(directory=ROOT/'web'),name='assets')
