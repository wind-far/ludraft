"""Start the management UI/API and isolated game preview on loopback only."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from studio.app import create_app, create_preview_app

async def main():
    servers = [uvicorn.Server(uvicorn.Config(create_app(), host='127.0.0.1', port=8080, timeout_graceful_shutdown=3)),
               uvicorn.Server(uvicorn.Config(create_preview_app(), host='127.0.0.1', port=8081, timeout_graceful_shutdown=3))]
    await asyncio.gather(*(server.serve() for server in servers))

if __name__ == '__main__':
    asyncio.run(main())
