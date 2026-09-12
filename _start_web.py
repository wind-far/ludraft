import sys
sys.path.insert(0, "d:/openclaw-multi-agent-gamedev/src")
import uvicorn
from web.app import create_app
app = create_app("d:/openclaw-multi-agent-gamedev")
uvicorn.run(app, host="127.0.0.1", port=8080)
