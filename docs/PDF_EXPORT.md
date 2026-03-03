# PDF export

This project supports PDF export via **WeasyPrint**.

WeasyPrint is a Python library, but **PDF generation depends on native system libraries** (Cairo / Pango / GDK-PixBuf). If these libraries are missing, the backend will return:

- HTTP `424 Failed Dependency`

with an actionable error message.

## How the backend finds native libraries

- On **Windows**, the backend uses `os.add_dll_directory(...)` to add one or more directories to the DLL search path at runtime.
- The directories can be configured with the environment variable:

`INTENT_WEASYPRINT_DLL_DIRS`

Use a semicolon-separated list of paths.

Example:

```powershell
$env:INTENT_WEASYPRINT_DLL_DIRS = "C:\Program Files\GTK3-Runtime Win64\bin"
```

## Windows

### Recommended installation (no PATH pollution)

Install the GTK runtime:

```powershell
winget install -e --id tschoonj.GTKForWindows
```

The installer provides DLLs in:

- `C:\Program Files\GTK3-Runtime Win64\bin`

The repo `start-backend.ps1` sets `INTENT_WEASYPRINT_DLL_DIRS` automatically if it detects that directory.

### Troubleshooting

- If PDF export still returns `424`, verify that the GTK runtime folder exists and contains DLLs:

```powershell
Test-Path "C:\Program Files\GTK3-Runtime Win64\bin"
```

- If you installed GTK elsewhere, set `INTENT_WEASYPRINT_DLL_DIRS` manually.

## Linux (Debian/Ubuntu)

Install native dependencies:

```bash
sudo apt-get update
sudo apt-get install -y \
  libcairo2 \
  libpango-1.0-0 libpangoft2-1.0-0 \
  libgdk-pixbuf-2.0-0 \
  libffi8 \
  shared-mime-info
```

Then install Python dependencies and start the backend.

## macOS

Install native dependencies with Homebrew:

```bash
brew install cairo pango gdk-pixbuf libffi
```

Then install Python dependencies and start the backend.

## References

- WeasyPrint installation: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation
- WeasyPrint troubleshooting: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#troubleshooting
