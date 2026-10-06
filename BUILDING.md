# Building The Windows EXE

Run this from the project folder:

```powershell
.\build_exe.ps1
```

The portable app is created at:

```text
dist\DataComparisonVideoMaker\DataComparisonVideoMaker.exe
```

Copy the whole `dist\DataComparisonVideoMaker` folder to another Windows PC. Keep
the `_internal`, `projects`, and `exports` folders beside the executable.

This build is portable for Windows machines with the same CPU architecture. Build
on Windows to create a Windows `.exe`.
