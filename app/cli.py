import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from .settings import CONFIG,ROOT,HOME,DATA
from .storage import backup

def main():
    if sys.stdout is None or sys.stderr is None:
        log_directory=HOME/'logs';log_directory.mkdir(parents=True,exist_ok=True)
        task_log=open(log_directory/'scheduled.log','a',encoding='utf-8',buffering=1)
        if sys.stdout is None: sys.stdout=task_log
        if sys.stderr is None: sys.stderr=task_log
    parser=argparse.ArgumentParser(description='本机管理命令；网站仅提供只读查看')
    parser.add_argument('command',choices=['collect','funds','retry','forward','freeze','report','send','serve','backup','status','weekly'])
    parser.add_argument('--refresh-profiles',action='store_true')
    parser.add_argument('--force',action='store_true',help='人工补采时允许在自动补采时段外执行')
    parser.add_argument('--port',type=int)
    args=parser.parse_args()
    if args.command=='serve':
        import uvicorn
        uvicorn.run('app.main:app',host='127.0.0.1',port=args.port or CONFIG['port'],log_level='warning')
        return
    # OS-held file lock; crashes release the lock automatically. No stale-lock deletion.
    import msvcrt
    lock=open(DATA/'task.lock','a+b')
    lock.seek(0)
    if lock.read(1)==b'':
        lock.write(b'0');lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:
        print('另一个管理任务正在运行，本次跳过。')
        return
    try:
        if args.command in ('collect','funds'):
            from .pipeline import collect
            s=collect(args.refresh_profiles,funds_only=args.command=='funds')
            print(json.dumps({'snapshot':s['id'],'fresh':s['fresh_count'],'fund_rows':len(s['funds']),'shares':sum(len(f['shares']) for f in s['funds']),'issues':s['issues']},ensure_ascii=False))
        elif args.command=='retry':
            from .pipeline import retry_delayed
            from .calendar import now_iso
            print(json.dumps({'task':'retry','at':now_iso(),**retry_delayed(force=args.force)},ensure_ascii=False))
        elif args.command=='forward':
            from .pipeline import refresh_forward_display
            s=refresh_forward_display();item=s['valuation_publisher']['forward']
            print(json.dumps({'snapshot':s['id'],'source':item['source'],'value':item.get('value'),
                             'date':item.get('date'),'samples':len(item['history']),'status':item['status'],
                             'percentile_5y':item.get('percentile'),'score':s['score']['value']},ensure_ascii=False))
        elif args.command in ('freeze','report'):
            from .reports import freeze_report
            day,s,_,_=freeze_report()
            print(f'早报预览已保存：data/reports/{day}.html；快照 {s["id"]}')
        elif args.command=='send':
            from .reports import send_report
            print(send_report())
        elif args.command=='backup':
            print(backup())
        elif args.command=='status':
            from .storage import latest
            s=latest()
            print(json.dumps({'has_snapshot':bool(s),'id':s.get('id') if s else None,'mail_configured':bool(CONFIG.get('worker_url'))},ensure_ascii=False))
        elif args.command=='weekly':
            from .storage import latest
            from .valuation_views import archive_weekly
            print(archive_weekly(latest()))
    finally:
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()

if __name__=='__main__':
    main()
