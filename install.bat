@echo off
REM Installs the video-learning commands for every terminal (CMD, PowerShell, Windows Terminal).
REM Usage:  install.bat            (subtitle-based transcripts + Claude study tools)
REM         install.bat whisper    (also installs faster-whisper for videos without subtitles)
setlocal
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul || set "PY=py"
%PY% --version >nul 2>nul || (
    echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    exit /b 1
)

set "TARGET=."
if /i "%~1"=="whisper" set "TARGET=.[whisper]"

echo Installing video-learning...
%PY% -m pip install --upgrade -e "%TARGET%" || exit /b 1

echo.
echo Checking PATH...
%PY% -m video_learning.pathfix || exit /b 1

echo.
echo All set. In a NEW terminal window try:
echo     video-transcript --help
echo     video-study --help
echo     video-quiz --help
if not defined ANTHROPIC_API_KEY (
    echo.
    echo video-study needs an Anthropic API key. Set it once with:
    echo     setx ANTHROPIC_API_KEY "sk-ant-..."
)
endlocal
