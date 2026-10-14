@echo off
cd /d %~dp0
call .venv\Scripts\activate.bat
python tests\test_engines.py || (echo Regression test FAILED - do not use & pause & exit /b 1)
streamlit run app.py --server.headless false --browser.gatherUsageStats false
