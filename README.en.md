# Nasdaq QDII Monitor

A Windows-local Nasdaq-100 and RMB QDII observation dashboard with a tray launcher, scheduled collection, SQLite snapshots and a read-only website.

[Download v0.5.0 for Windows](https://github.com/I-am-TonyWu/nasdaq-qdii-monitor/releases/tag/v0.5.0) · [中文](README.md) · [Program manual](desktop/README.en.md)

## Run the program

1. Download and extract `NasdaqQDII-0.5.0-Windows-x64.zip` from Releases.
2. Double-click `NasdaqQDII.exe`. It prepares its bundled runtime, collects data, and opens your default browser after a snapshot is available.
3. Use the tray menu for collection, fund refresh, missing-data retries, database backups, and automatic-task settings.

Requires Windows 10/11 x64 and .NET Framework 4.8. Python is bundled; no development tools are required for normal use. Cached data can be viewed offline. Initial collection requires working providers and network access.

The six views cover market overview, valuation and sentiment, relative style/technical indicators, macro assets, funds/channels, and history. Instruments include NDX, NDXTMC, QQQ, VTV, CGDV, KO, BRK.A and Russell 2000. Fund quotas are separated by distributor/direct channels and share-class scope.

The observation score weights Forward PE / VXN / CNN FGI at 50% / 30% / 20%. It uses the publisher's current five-year forward percentile, a three-year VXN percentile, and current FGI. Missing components disable the complete score. This rule has not been backtested and does not execute trades.

The server binds to `127.0.0.1:8765` and has read-only website routes. Management commands and scheduled tasks run locally. Email tasks create previews by default. Application runtimes and working data are stored separately. See the program manual for upgrades and complete data migration.

## Private remote access

Settings → Remote access configures a dedicated Cloudflare Tunnel, DNS record and mailbox-only Access application. Cloudflared is bundled; remote access is disabled by default. Account details, emails and credentials are never bundled. The configured default hostname is `nasdaq.tonywu.link`; live cloud setup is deferred for this release by the local user.

The same current-user DPAPI-protected API token stored by codex-web can be reused if it has Tunnel Edit, DNS Edit, Zone Read and Access Apps/Policies Edit for the relevant resources. Each tunnel keeps a separate runtime token. Existing codex-web resources are not modified. See [remote setup](docs/REMOTE_ACCESS.md).

Releases retain [v0.4.5](https://github.com/I-am-TonyWu/nasdaq-qdii-monitor/releases/tag/v0.4.5) and subsequent versions as separate tags and assets.

## Source setup and build

Python 3.12 on Windows x64:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1 collect
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1 serve
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
powershell -ExecutionPolicy Bypass -File .\scripts\build-desktop.ps1
```

The build uses the Windows C# compiler and bundles a private Python runtime. Clean-checkout unit tests use constructed fixtures. Four integration checks require a locally collected snapshot and are skipped when it is absent.

EXE verification additionally needs a built EXE and a local snapshot. Browser checks use Node.js, Playwright and Microsoft Edge. Set `NASDAQ_NODE` and `NASDAQ_PLAYWRIGHT` to custom paths if needed. Verification uses isolated data, ports and temporary scheduled tasks, without upstream collection or email sending.

## Data and release scope

The public repository and release assets exclude market histories, provider caches, personal channel confirmations, local account configuration, secrets, and chat data. `config.local.json` and `config/manual_channels.json` are ignored. Fund rules have announcement dates and are rechecked during collection; bundled quotas are historical evidence rather than a guarantee of current availability.

Provider data permissions are separate from software component licenses. Dollar Liquidity data is used for personal display; no valuation export or public redistribution is provided. Methods and series are kept separate, without fabricated history. See [data sources](docs/DATA_SOURCES.md), [release validation](docs/RELEASE-v0.5.0.md), and [third-party notices](THIRD_PARTY.md).

This version adds native settings layout and remote protection checks, alongside backend, EXE and desktop/mobile browser verification. Other physical PCs, reboot/login recovery and prolonged operation have not been independently verified.
