@echo off
cd /d "C:\Users\jinyo\Desktop\claude_2603"
echo 대시보드를 시작합니다...
timeout /t 2 /nobreak >nul
start "" "http://localhost:8501"
streamlit run dashboard.py
pause
