@echo off
setlocal
cd /d "%~dp0"
title Atlas - Intelligence Workspace

echo A iniciar o Atlas...
echo.
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>nul
if errorlevel 1 goto try_python
py -3 "%~dp0launch.py"
goto finished

:try_python
where python >nul 2>nul
if errorlevel 1 goto missing
python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>nul
if errorlevel 1 goto missing
python "%~dp0launch.py"
goto finished

:missing
echo O Atlas precisa de Python 3.12 ou superior.
echo Instale em https://www.python.org/downloads/
echo Durante a instalacao, marque "Add Python to PATH".
echo Depois, volte a clicar neste ficheiro.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:finished
if not errorlevel 1 exit /b 0
echo.
echo O Atlas terminou com um erro. Leia a mensagem acima.
pause
exit /b 1
