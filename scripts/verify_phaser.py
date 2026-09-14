"""Build and exercise the fixed Phaser template, without calling a model."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studio.db import uid
from studio.files import copy_source
from studio.runner import Runner, RunnerError


async def verify(output):
    candidate = output.resolve() / uid()
    copy_source(ROOT / 'templates/phaser/tower_defense', candidate)
    try:
        evidence = await Runner().run(candidate, uid())
    except (RunnerError, ValueError, OSError) as error:
        print(json.dumps({'passed': False, 'workspace': str(candidate), 'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({'passed': evidence.get('passed') is True,
                      'scope': evidence.get('scope'), 'gameplay_verified': False,
                      'workspace': str(candidate), 'checks': evidence.get('checks'),
                      'error': evidence.get('error')}, ensure_ascii=False, indent=2))
    return 0 if evidence.get('passed') is True else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='固定 Phaser 工程接入检查；不调用模型，不发布版本')
    parser.add_argument('--output', type=Path, default=ROOT / '.studio/phaser-integration')
    args = parser.parse_args()
    raise SystemExit(asyncio.run(verify(args.output)))
