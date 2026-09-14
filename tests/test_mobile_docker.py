"""Real Docker browser tests for four exported templates, no model calls."""
import json
import os
import zipfile
from pathlib import Path
import pytest
from scripts.evaluate import CASES,configure,template_for
from studio.files import copy_source
from studio.evaluation import archive_game
from studio.verification import run_checked
from studio.runner import Runner

pytestmark=pytest.mark.skipif(os.getenv('STUDIO_DOCKER_TESTS')!='1',reason='opt-in real Docker mobile integration')

@pytest.mark.asyncio
@pytest.mark.parametrize('case',CASES[:4],ids=lambda c:c['mode'])
async def test_exported_game_runs_without_workbench(tmp_path,case):
    candidate=tmp_path/'candidate';copy_source(template_for(case),candidate);configure(candidate,case)
    runner=Runner();evidence=await run_checked(runner,candidate,'mobile-'+case['mode'],case['mode'])
    assert evidence['passed'],evidence
    assert evidence['mobile']['status']=='passed'
    artifact=archive_game(tmp_path,'export',candidate,evidence,{'source':'authored template, no LLM'})
    standalone=tmp_path/'standalone'
    with zipfile.ZipFile(tmp_path/artifact['path']) as z:
        assert 'RUN_GAME.md' in z.namelist() and 'licenses/upstream-MIT.txt' in z.namelist()
        z.extractall(standalone)
    # Only extracted files enter an isolated container and its own static HTTP server.
    verified=await run_checked(runner,standalone,'standalone-'+case['mode'],case['mode'])
    assert verified['passed'] and verified['mobile']['status']=='passed',verified
