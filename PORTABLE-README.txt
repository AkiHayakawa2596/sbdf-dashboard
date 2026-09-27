SBDF MULTI-DATA EXPLORER - PORTABLE WINDOWS DEPLOYMENT
======================================================

TARGET / END-USER PC
--------------------
No Python installation is required.
No pip command is run.
No virtual environment is created.
No internet connection is required by the launcher itself.

1. Extract the entire SBDF-Dashboard folder.
2. Edit config.json if needed.
3. Double-click "Start Dashboard.bat".
4. The browser opens http://localhost:8080/.

For mobile/LAN access, open this from a phone on the same network:
  http://<PC-IP>:8080/

The first time Windows sees the server executable, Windows Firewall may ask
whether to allow network access. Allow the application on the appropriate
trusted/private network if phones or other PCs need to connect.

IMPORTANT
---------
Keep the whole folder together. Do not copy only SBDFDashboard.exe because
its bundled runtime files are stored in the _internal directory.

config.json is intentionally outside the executable so you can change SBDF
paths/URLs without rebuilding the application.

data\ is also external so generated CSV and Parquet files persist beside the
application.

NETWORK SHARES
--------------
If an SBDF path points to a UNC/network share, the Windows account running the
dashboard must already have permission to read that share.

BUILD / DEVELOPMENT PC ONLY
---------------------------
To produce a new portable distribution:
  1. Install Python on the build PC.
  2. Run build_portable.bat.
  3. Deploy dist\SBDF-Dashboard-Portable.zip or dist\SBDF-Dashboard\.

The build script installs Python packages only on the build PC. Those packages
are bundled into the deployed folder by PyInstaller.


ANDROID / TERMUX BUILD OPTION
-----------------------------
If you do not have a Windows build PC, push the source project to GitHub and run the included GitHub Actions workflow:

  .github/workflows/build-windows-portable.yml

It builds and smoke-tests the Windows x64 portable package on GitHub's Windows runner. See TERMUX-GITHUB-BUILD.md in the source project for the full instructions.
