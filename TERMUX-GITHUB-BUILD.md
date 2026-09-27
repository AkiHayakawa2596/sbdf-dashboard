# Build the Windows portable dashboard from Termux using GitHub Actions

You can edit and push this project entirely from Android/Termux. GitHub Actions then supplies the Windows build machine and produces `SBDF-Dashboard-Portable.zip` for you.

## 1. Install Git in Termux

```bash
pkg update
pkg install git
```

Optional but useful if you want to authenticate with the GitHub CLI:

```bash
pkg install gh
```

Then authenticate:

```bash
gh auth login
```

Choose GitHub.com, HTTPS, and browser/device authentication.

## 2. Create a GitHub repository

Create an empty repository in GitHub, for example:

```text
sbdf-dashboard
```

Do not add a README during repository creation if this project already contains one.

## 3. Push this project from Termux

Open the extracted project folder in Termux. Example:

```bash
cd /storage/emulated/0/Download/sbdf-live-dashboard
```

If Termux has not been granted shared-storage access yet, run once:

```bash
termux-setup-storage
```

Initialize and push:

```bash
git init
git add .
git commit -m "Initial SBDF dashboard"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/sbdf-dashboard.git
git push -u origin main
```

Replace `YOUR-USERNAME` and the repository name with your actual values.

## 4. Run the Windows build from your phone

In GitHub:

1. Open your repository.
2. Open **Actions**.
3. Select **Build Windows Portable Dashboard**.
4. Tap **Run workflow**.
5. Keep the branch as `main` and tap **Run workflow**.

GitHub starts a `windows-latest` runner, installs Python 3.12 and the project dependencies, builds `SBDFDashboard.exe`, smoke-tests `/health`, creates the portable ZIP, and uploads it as an Actions artifact.

## 5. Download the finished portable ZIP

After the workflow succeeds:

1. Open the completed workflow run.
2. Scroll to **Artifacts**.
3. Download **SBDF-Dashboard-Windows-x64**.
4. The artifact contains `SBDF-Dashboard-Portable.zip`.

Extract that ZIP on the target Windows PC. The target PC does not need Python or pip.

## 6. Build a versioned release from Termux

You can also create a tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

A tag beginning with `v` automatically starts the Windows build. If the build succeeds, the workflow also creates a GitHub Release and attaches `SBDF-Dashboard-Portable.zip` to that release.

For the next version:

```bash
git add .
git commit -m "Update dashboard"
git push

git tag v1.0.1
git push origin v1.0.1
```

## 7. What happens in GitHub Actions

```text
Termux / Android
      |
      | git push or v* tag
      v
GitHub repository
      |
      v
GitHub Actions Windows runner
      |
      +-- Python 3.12 x64
      +-- spotfire 2.4.2
      +-- pandas / DuckDB / Flask
      +-- PyInstaller
      |
      v
SBDFDashboard.exe
      |
      +-- packaged folder
      +-- health smoke test
      v
SBDF-Dashboard-Portable.zip
      |
      +-- Actions artifact
      +-- GitHub Release asset when built from a v* tag
```

## Important notes

- The workflow builds **Windows x64**.
- `spotfire==2.4.2` has a Windows x86-64 wheel for Python 3.12, which is why the workflow pins Python 3.12 x64.
- A normal `git push` to `main` does not build automatically. This avoids wasting Actions minutes while you are editing. Use **Run workflow** when you want a build, or push a `v*` tag for a release build.
- Never commit confidential SBDF files, passwords, access tokens, or private server credentials to the GitHub repository. Keep real SBDF paths in the deployed `config.json`, or use a private repository when appropriate.
