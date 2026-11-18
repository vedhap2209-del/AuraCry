@echo off
python -m venv .venv 2>nul
call .venv\Scripts\activate
pip install -r backend\requirements.txt
python run.py
