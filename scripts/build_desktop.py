"""Build the Windows tray EXE from this checkout and its locked Python environment."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.4.5'
DEV = {'pip', 'pytest', '_pytest', 'pluggy', 'iniconfig', 'pygments'}


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy_tree(source, destination, skip_site=False, skip_dev=False):
    def ignore(directory, names):
        excluded = []
        for name in names:
            low = name.lower()
            if low == '__pycache__' or low.endswith(('.pyc', '.pyo')):
                excluded.append(name)
            elif skip_site and Path(directory) == source and low == 'site-packages':
                excluded.append(name)
            elif skip_dev and Path(directory) == source and (
                low in DEV or low.split('-', 1)[0] in DEV
            ):
                excluded.append(name)
        return excluded
    shutil.copytree(source, destination, ignore=ignore)


def run(args, **kwargs):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', **kwargs)
    if result.stdout.strip():
        print(result.stdout.strip(), flush=True)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {args[0]}\n{result.stderr}')
    return result


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--recompile':
        stage = Path(sys.argv[2]).resolve()
        if not stage.is_relative_to(ROOT / '.desktop-build'):
            raise ValueError('Recompile stage must be in this project .desktop-build')
        manifest = json.loads((stage / 'payload/payload-manifest.json').read_text(encoding='utf-8'))
        for rel, digest in manifest.items():
            if sha256(stage / 'payload' / rel) != digest:
                raise ValueError('Staged runtime modified: ' + rel)
            if rel.startswith(('app/', 'web/', 'templates/', 'config/', 'desktop/')) and (ROOT / rel).exists():
                if sha256(ROOT / rel) != digest:
                    raise ValueError('Source changed; run a full build: ' + rel)
        compile_release(stage)
        return
    stage = ROOT / '.desktop-build' / uuid.uuid4().hex
    payload = stage / 'payload'
    payload.mkdir(parents=True)
    python = payload / 'python'
    python.mkdir()
    base = Path(sys.base_prefix)
    site = Path(sysconfig.get_path('purelib'))
    print('Bundling private Python runtime and application…', flush=True)
    for name in ('python.exe', 'pythonw.exe', 'python312.dll', 'python3.dll',
                 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt'):
        source = base / name
        if source.exists():
            shutil.copy2(source, python / name)
        elif name in ('python.exe', 'pythonw.exe', 'python312.dll', 'LICENSE.txt'):
            raise FileNotFoundError(source)
    copy_tree(base / 'DLLs', python / 'DLLs')
    copy_tree(base / 'Lib', python / 'Lib', skip_site=True)
    copy_tree(site, python / 'Lib' / 'site-packages', skip_dev=True)
    (python / 'python312._pth').write_text('.\nDLLs\nLib\nLib/site-packages\n..\n', encoding='utf-8')
    for directory in ('app', 'web', 'templates'):
        copy_tree(ROOT / directory, payload / directory)
    (payload / 'config').mkdir()
    for name in ('fund_rules.json', 'source_registry.json'):
        shutil.copy2(ROOT / 'config' / name, payload / 'config' / name)
    for name in ('requirements.txt', 'requirements.lock', 'config.example.json'):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, payload / name)
    (payload / 'desktop').mkdir()
    for name in ('install-tasks.ps1', 'README.zh-CN.md', 'README.en.md'):
        shutil.copy2(ROOT / 'desktop' / name, payload / 'desktop' / name)
    dependencies = []
    for dist in importlib.metadata.distributions(path=[str(site)]):
        name = dist.metadata.get('Name', '')
        if name.lower().replace('-', '_') not in DEV:
            dependencies.append({'name': name, 'version': dist.version,
                                 'license': dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See bundled package license'})
    dependencies.sort(key=lambda d: d['name'].lower())
    (payload / 'dependencies.json').write_text(json.dumps(dependencies, ensure_ascii=False, indent=2), encoding='utf-8')
    (payload / 'THIRD_PARTY.md').write_text(
        '# Third-party components\n\nPython license: python/LICENSE.txt. '
        'Dependency versions: dependencies.json. Python package notices/licenses '
        'are retained in python/Lib/site-packages, including dist-info directories. '
        'Vendored web assets retain their original license headers and notices.\n'
        'The program uses Microsoft .NET Framework supplied with Windows.\n', encoding='utf-8')
    print('Testing relocated, isolated Python imports…', flush=True)
    run([python / 'python.exe', '-B', '-X', 'utf8', '-c',
         'import sys, fastapi, uvicorn, akshare, pandas, numpy, requests, bs4, curl_cffi, exchange_calendars, tzdata; '
         'assert sys.flags.isolated == 1 and sys.flags.no_site == 1; '
         'print("Private runtime import check passed: " + sys.version.split()[0])'], cwd=payload)
    files = sorted(p for p in payload.rglob('*') if p.is_file())
    forbidden = ('config.local.json', 'manual_channels.json', '.env', 'latest.json', 'monitor.sqlite3')
    for file in files:
        rel = file.relative_to(payload).as_posix()
        if file.name in forbidden or rel.startswith(('data/', 'logs/', 'outputs/', '.venv/')):
            raise ValueError(f'Private file in package: {rel}')
    manifest = {p.relative_to(payload).as_posix(): sha256(p) for p in files}
    (payload / 'payload-manifest.json').write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')
    archive = stage / 'payload.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
        for file in sorted(p for p in payload.rglob('*') if p.is_file()):
            info = zipfile.ZipInfo(file.relative_to(payload).as_posix(), (2026, 10, 7, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zip_file.writestr(info, file.read_bytes())
    identifier = sha256(archive)
    (stage / 'payload.id').write_text(identifier, encoding='ascii')
    compile_release(stage)


def compile_release(stage):
    payload = stage / 'payload'
    archive = stage / 'payload.zip'
    identifier = sha256(archive)
    if identifier != (stage / 'payload.id').read_text(encoding='ascii'):
        raise ValueError('Staged archive checksum mismatch')
    manifest = json.loads((payload / 'payload-manifest.json').read_text(encoding='utf-8'))
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
    common = [compiler, '/nologo', '/codepage:65001', '/utf8output', '/platform:x64', '/optimize+', '/debug-',
              '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
              '/reference:System.Web.Extensions.dll', '/reference:System.IO.Compression.dll',
              '/reference:System.IO.Compression.FileSystem.dll', '/reference:System.Security.dll',
              '/reference:System.Management.dll']
    sources = [ROOT / 'desktop' / name for name in ('Runtime.cs', 'TrayApp.cs')]
    assets = stage / 'BuildAssets.exe'
    run(common + ['/target:exe', '/main:NasdaqQDII.BuildAssets', f'/out:{assets}'] + sources + [ROOT / 'desktop' / 'BuildAssets.cs'])
    icon = stage / 'app.ico'
    run([assets, icon])
    release = ROOT / 'outputs' / 'releases' / f'NasdaqQDII-{VERSION}'
    release.mkdir(parents=True, exist_ok=True)
    executable = release / 'NasdaqQDII.exe'
    print(f'Compiling Windows EXE ({archive.stat().st_size / 1048576:.1f} MiB runtime)…', flush=True)
    run(common + ['/target:winexe', '/main:NasdaqQDII.Program', f'/out:{executable}',
                  f'/win32icon:{icon}', f'/win32manifest:{ROOT / "desktop" / "app.manifest"}',
                  f'/resource:{archive},payload.zip', f'/resource:{stage / "payload.id"},payload.id'] + sources)
    for name in ('README.zh-CN.md', 'README.en.md'):
        shutil.copy2(ROOT / 'desktop' / name, release / name)
    for name in ('dependencies.json', 'THIRD_PARTY.md'):
        shutil.copy2(payload / name, release / name)
    distribution_files = [executable] + [release / name for name in ('README.zh-CN.md', 'README.en.md', 'dependencies.json', 'THIRD_PARTY.md')]
    (release / 'SHA256SUMS.txt').write_text(''.join(f'{sha256(file)}  {file.name}\n' for file in distribution_files), encoding='utf-8')
    portable_zip = release.parent / f'NasdaqQDII-{VERSION}-Windows-x64.zip'
    with zipfile.ZipFile(portable_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
        for file in distribution_files + [release / 'SHA256SUMS.txt']:
            zip_file.write(file, f'NasdaqQDII-{VERSION}/{file.name}')
    (release.parent / f'NasdaqQDII-{VERSION}-Windows-x64.zip.sha256').write_text(f'{sha256(portable_zip)}  {portable_zip.name}\n', encoding='utf-8')
    result = {'version': VERSION, 'executable': str(executable), 'zip': str(portable_zip),
              'exe_sha256': sha256(executable), 'zip_sha256': sha256(portable_zip),
              'payload_sha256': identifier, 'payload_files': len(manifest),
              'payload_uncompressed_bytes': sum(p.stat().st_size for p in payload.rglob('*') if p.is_file()),
              'executable_bytes': executable.stat().st_size, 'staging': str(stage)}
    (stage / 'build-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
