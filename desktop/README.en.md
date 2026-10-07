# Nasdaq QDII Monitor for Windows — v0.4.5

Double-click **NasdaqQDII.exe**. The program installs its private runtime, creates desktop and Start Menu shortcuts, starts a loopback-only service, and opens your default browser. Python and Node.js are included or unnecessary; no separate installation is needed. Requires Windows 10/11 x64 and the built-in .NET Framework 4.8.

The tray menu opens the dashboard and runs collection, fund refresh, missing-data retry, and a consistent SQLite database backup. Closing Settings leaves the tray running. Exit stops only a service started by this program; an attached existing project service stays running.

When first launched from the project's release folder, the program discovers the parent project and reuses its data and local configuration. Existing scheduled tasks are preserved. On a new computer it creates `%LOCALAPPDATA%\NasdaqQDII\workspace`, collects data online, and opens the site when a snapshot exists. Cached data remains readable offline. Failed providers remain visibly missing instead of being filled with synthetic data.

To select an existing data home explicitly:

```powershell
.\NasdaqQDII.exe --home "D:\NasdaqMonitorData"
```

Use **Settings → Enable / repair automatic tasks** to configure the eight current-user Windows scheduled tasks. They run at Beijing time (UTC+8): collection at login, 06:30, 06:45, 12:30; retry every 30 minutes from 07:15 to 17:15; freeze at 06:55; report preview at 07:00; funds at 09:10, 14:30, 20:30; database backup at 07:10; weekly archive on Saturdays at 12:30. Running legacy service tasks are retained. Other same-home tasks are exported to XML before replacement. Tasks owned by other data homes are refused. Reports are local previews; this program does not expose email sending.

The Windows-login checkbox controls the tray's Run registry entry. It does not remove an enabled service task. Exiting the tray does not disable scheduled collectors.

The stable launcher is `%LOCALAPPDATA%\NasdaqQDII\app\NasdaqQDII.exe`. Versioned runtimes and program logs are in the neighboring `releases` and `logs` folders. Data is stored separately in the selected home. Exit before opening a newer EXE; upgrade preserves the selected home and keeps the previous launcher. Repair scheduled tasks after upgrades so collectors use the new runtime.

Database Backup uses SQLite's consistent backup API and writes to `data/backups`. For complete migration, stop the tray and collectors, then copy the entire selected home, including `data`, optional `config.local.json`, and optional `config/manual_channels.json`.

This generic package excludes downloaded market data, provider caches, personal channel confirmations, secrets, and chat content. Existing provider usage terms still apply. The dashboard remains a personal observation tool. The server listens on `127.0.0.1` and exposes read-only website routes.

For port conflicts, change the port in Settings; unrelated processes are never terminated. Inspect logs and retry for startup errors. Check network/proxy settings for failed collection. Verify files against `SHA256SUMS.txt`. The executable is not code-signed.
