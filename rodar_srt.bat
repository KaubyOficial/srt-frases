@echo off
cd /d "%~dp0"
echo ============================================
echo  ETAPA 1 — Dividir Roteiro
echo ============================================
python dividir_roteiro.py
if errorlevel 1 (
    echo.
    echo ERRO na etapa 1. Abortando.
    pause
    exit /b 1
)
echo.
echo ============================================
echo  ETAPA 2 — SRT Processor v1.2
echo ============================================
python srt_processor_v1.2.py
pause
