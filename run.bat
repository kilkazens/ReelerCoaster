@echo off
chcp 65001 >nul
title ReelerCoaster 🎢 - Автонарезка Reels & Shorts

echo ========================================================
echo    🎢  ReelerCoaster AI Studio
echo    Автоматическая нарезка видео на Reels/Shorts/TikTok
echo ========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [!] Виртуальное окружение не найдено. Создаём...
    python -m venv .venv
    echo [*] Установка зависимостей...
    .\.venv\Scripts\pip install -r requirements.txt
)

echo [*] Запуск веб-сервера...
echo [*] Откройте в браузере: http://localhost:8000
echo.
.\.venv\Scripts\python.exe main.py --port 8000
pause
