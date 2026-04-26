@echo off
echo ==========================================
echo   JARVIS Setup - Installing Dependencies
echo ==========================================
echo.

pip install faster-whisper pyaudio numpy Pillow requests pygame SpeechRecognition

echo.
echo If pyaudio failed, run these instead:
echo   pip install pipwin
echo   pipwin install pyaudio
echo.
echo ==========================================
echo   Testing Groq Connection...
echo ==========================================

python -c "import requests; r = requests.post('https://api.groq.com/openai/v1/chat/completions', headers={'Authorization': 'Bearer YOUR_GROQ_KEY_HERE', 'Content-Type': 'application/json'}, json={'model': 'llama-3.3-70b-versatile', 'messages': [{'role': 'user', 'content': 'Say hello'}], 'max_tokens': 10}); print('Groq OK!' if r.status_code == 200 else f'Groq Error: {r.status_code}')"

echo.
echo ==========================================
echo   Downloading Whisper model (first time only)...
echo ==========================================

python -c "from faster_whisper import WhisperModel; m = WhisperModel('base', device='cpu', compute_type='int8'); print('Whisper model ready!')"

echo.
echo ==========================================
echo   Testing Pygame audio...
echo ==========================================

python -c "import pygame; pygame.mixer.init(); print('Pygame mixer OK!')"

echo.
echo ==========================================
echo   All done! Now open Claude Code and paste
echo   the JARVIS_CLAUDE_CODE_PROMPT.md contents.
echo ==========================================
pause
