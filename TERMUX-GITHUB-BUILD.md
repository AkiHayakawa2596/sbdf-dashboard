# Build the offline Windows wheelhouse from Termux using GitHub Actions

The project can be edited and pushed entirely from Android/Termux. GitHub Actions supplies a Windows x64 build machine and creates an offline deployment ZIP containing the dashboard source and all required Python wheels.

## Normal Termux update

From the repository folder:

```bash
git add .
git commit -m "Add offline Windows wheelhouse build"
git push
```

## Run the offline build

In GitHub:

1. Open the repository.
2. Open **Actions**.
3. Select **Build Windows Offline Wheelhouse**.
4. Tap **Run workflow**.
5. Select `main` and run it.

The workflow uses Windows x64 + Python 3.12 and:

```text
requirements.txt
      ↓
pip download --only-binary=:all:
      ↓
wheelhouse/*.whl
      ↓
clean venv
      ↓
pip install --no-index --find-links=wheelhouse
      ↓
import verification
      ↓
requirements-lock.txt
      ↓
second clean offline install
      ↓
server.py /health smoke test
      ↓
SHA256SUMS.txt
      ↓
SBDF-Dashboard-Offline-Windows-x64.zip
```

## Download the result

Open the successful workflow run and scroll to **Artifacts**.
Download:

```text
SBDF-Dashboard-Offline-Windows-x64
```

The artifact contains:

```text
SBDF-Dashboard-Offline-Windows-x64.zip
```

Move that ZIP to the approved Windows PC and follow `OFFLINE-INSTALL-WINDOWS.md`.

## Target PC requirement

The target PC needs an organization-approved **Python 3.12 x64** installation, but it does **not** need internet access for pip. All Python packages are installed from the included local `wheelhouse/`.

The deployment ZIP intentionally does not contain the custom PyInstaller `SBDFDashboard.exe` or a BAT launcher.

## Versioned release

A `v*` Git tag also starts the workflow:

```bash
git tag v1.1.0
git push origin v1.1.0
```

The offline ZIP will also be attached to that GitHub Release.
