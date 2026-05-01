@echo off
setlocal
cd /d "%~dp0"

echo Cleaning old builds...
echo Do not run the exe from build/. Use dist/GridGemmaPro/GridGemmaPro.exe
taskkill /F /IM GridGemmaPro.exe 2>nul
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q GridGemmaPro.spec 2>nul
if exist build (
  echo.
  echo Could not delete build\. Close any running GridGemmaPro.exe windows and try again.
  pause
  exit /b 1
)
if exist dist (
  echo.
  echo Could not delete dist\. Close any running GridGemmaPro.exe windows and try again.
  pause
  exit /b 1
)

echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Dependency installation failed.
  echo If llama-cpp-python fails to install, install Microsoft C++ Build Tools or use a Python version with a compatible prebuilt wheel.
  pause
  exit /b 1
)

echo Building GridGemma Pro...
python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name GridGemmaPro ^
  --icon=assets/gridgemma.ico ^
  --version-file version_info.txt ^
  --add-data "assets;assets" ^
  --add-data "models;models" ^
  --collect-all customtkinter ^
  --collect-all matplotlib ^
  --collect-all llama_cpp ^
  --collect-submodules scipy ^
  app.py
if errorlevel 1 (
  echo.
  echo Build failed. Check the PyInstaller output above and build\GridGemmaPro\warn-GridGemmaPro.txt if present.
  pause
  exit /b 1
)

if exist dist\GridGemmaPro (
  if not exist dist\GridGemmaPro\models mkdir dist\GridGemmaPro\models
  if not exist dist\GridGemmaPro\assets mkdir dist\GridGemmaPro\assets
  xcopy /E /I /Y models dist\GridGemmaPro\models >nul
  xcopy /E /I /Y assets dist\GridGemmaPro\assets >nul
)

echo.
echo Build finished.
echo Final app:
echo dist\GridGemmaPro\GridGemmaPro.exe
echo.
echo DO NOT run anything from build\.
echo Run only:
echo dist\GridGemmaPro\GridGemmaPro.exe
pause
