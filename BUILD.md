# No-install build

Recipients should **not** install Python. You (or GitHub Actions) build once.

## Easiest: GitHub Actions

1. Push this repo to GitHub.
2. Actions → **Build no-install binaries** → Run workflow.
3. Download artifacts:
   - `odte-scan-windows` → `odte-scan.exe`
   - `odte-scan-macos`
   - `odte-scan-linux`
4. Zip the folder and send it. Double-click the exe / binary.

Or tag a release: `git tag v1.0.0 && git push origin v1.0.0`.

## Local Windows (your PC)

```bat
pip install pyinstaller
pyinstaller --noconfirm odte-scan.spec
```

Copy `dist\odte-scan.exe` into a folder with `config.json`, `events.json`, `chain.json`.

## What the other person does

1. Unzip.
2. Edit `chain.json` with today’s 0DTE put bids (or leave the example).
3. Double-click `odte-scan.exe`.
4. Read TRADE / NO TRADE. Window stays open until Enter.

No Python. No pip. SmartScreen may warn because the exe is unsigned.

It still does not place broker orders and cannot invent a live SPX options chain.
