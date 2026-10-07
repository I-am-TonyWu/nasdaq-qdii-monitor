"""Compile and run source-only native layout/remote safety tests on Windows."""
import os
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
output = ROOT / 'outputs' / 'desktop-v050' / ('native-' + uuid.uuid4().hex[:8])
output.mkdir(parents=True)
compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
exe = output / 'DesktopTests.exe'
sources = [ROOT / 'desktop' / name for name in ('Runtime.cs', 'TrayApp.cs', 'SettingsWindow.cs', 'RemoteAccess.cs', 'DesktopTests.cs')]
refs = ['System.Windows.Forms', 'System.Drawing', 'System.Web.Extensions', 'System.IO.Compression', 'System.IO.Compression.FileSystem', 'System.Security', 'System.Management']
# The synthetic renderer uses a virtualized 96-DPI process; each test scales
# that baseline explicitly. The released EXE's real DPI behavior is checked
# separately by opening it on the host display with Computer Use.
args = [str(compiler), '/nologo', '/codepage:65001', '/utf8output', '/platform:x64', '/target:exe', '/main:NasdaqQDII.DesktopTests', f'/out:{exe}']
args += [f'/reference:{name}.dll' for name in refs] + [str(p) for p in sources]
subprocess.run(args, check=True, cwd=ROOT)
result = subprocess.run([str(exe), str(output)], cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace', timeout=120)
(output / 'results.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
print(result.stdout, result.stderr)
print(output)
raise SystemExit(result.returncode)
