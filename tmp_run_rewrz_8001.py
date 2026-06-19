import os
import sys
sys.path.insert(0, os.getcwd())
from uvicorn import run
run('rewrz.main:app', host='127.0.0.1', port=8001, reload=False)
