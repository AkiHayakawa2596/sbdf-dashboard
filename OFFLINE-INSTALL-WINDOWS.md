# SBDF Dashboard — Offline Windows installation

This deployment does **not** use the custom PyInstaller executable or BAT launcher.
It runs the auditable Python source using an approved **Python 3.12 x64** installation and packages all Python dependencies as local `.whl` files.

## Prerequisite

Install an organization-approved **Python 3.12 x64** on the target Windows PC. If the PC has no internet access, have IT provide the official Python installer through the normal software-distribution process.

Check it in Command Prompt:

```cmd
py -3.12 --version
```

or:

```cmd
python --version
```

The result should be Python 3.12.x, 64-bit.

## 1. Extract the package

For example:

```text
C:\SBDF-Dashboard\
  server.py
  config.json
  requirements.txt
  requirements-lock.txt
  SHA256SUMS.txt
  wheelhouse\
  web\
  data\
```

## 2. Create a private virtual environment

Open Command Prompt in the dashboard folder:

```cmd
cd /d C:\SBDF-Dashboard
py -3.12 -m venv .venv
```

If `py` is not available but Python 3.12 is on PATH:

```cmd
python -m venv .venv
```

## 3. Install only from the local wheelhouse

Use the locked package list produced and tested by GitHub Actions:

```cmd
.venv\Scripts\python.exe -m pip install --no-index --find-links=wheelhouse -r requirements-lock.txt
```

`--no-index` prevents pip from contacting PyPI or another online package index.

## 4. Verify the installed dependencies

```cmd
.venv\Scripts\python.exe -c "from spotfire import sbdf; import duckdb, pandas, flask, requests; print('Dependencies OK')"
```

## 5. Configure your real SBDF path(s)

Edit:

```text
config.json
```

Do not put confidential server credentials into GitHub. Configure real paths on the deployed PC.

## 6. Start the dashboard

From Command Prompt:

```cmd
cd /d C:\SBDF-Dashboard
.venv\Scripts\python.exe server.py
```

Then open:

```text
http://localhost:8080
```

For another device on the same permitted LAN, use the server PC's approved LAN IP, for example:

```text
http://192.168.1.123:8080
```

## 7. Stop the dashboard

Return to the Command Prompt window running the server and press:

```text
Ctrl+C
```

## Integrity / audit

`SHA256SUMS.txt` contains hashes of all downloaded wheels plus key application files. This can help IT/security verify that the transferred files are unchanged from the GitHub Actions package.

## Security note

This packaging method is intended to be easier to inspect and approve than an unsigned custom executable. It does not bypass endpoint protection. If Python, scripts, ports, or individual packages are restricted by organizational policy, use the normal IT/security approval or allow-list process.
