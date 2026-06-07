@echo off
uv run pyinstaller BiliSpectrumPlayer.spec -y
if %errorlevel% neq 0 exit /b %errorlevel%

set DIST=dist\BiliSpectrumPlayer\_internal\PySide6
if exist "%DIST%" (
    echo Cleaning unnecessary Qt6 DLLs...
    del /q "%DIST%\Qt6Quick*.dll" 2>nul
    del /q "%DIST%\Qt6Qml*.dll" 2>nul
    del /q "%DIST%\Qt6Pdf*.dll" 2>nul
    del /q "%DIST%\Qt6VirtualKeyboard*.dll" 2>nul
    del /q "%DIST%\Qt6OpenGL*.dll" 2>nul
    del /q "%DIST%\Qt6WebChannel*.dll" 2>nul
    del /q "%DIST%\Qt6WebSockets*.dll" 2>nul
    del /q "%DIST%\opengl32sw.dll" 2>nul
    echo Done.
)
echo Build complete: dist\BiliSpectrumPlayer\
