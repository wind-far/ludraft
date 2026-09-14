"""Real fixed-engine integration only; these tests do not evaluate model quality."""
import json
import os
from pathlib import Path
import pytest
from studio.files import copy_source
from studio.runner import Runner, PHASER_IMAGE
from studio.db import uid
from studio.artifacts import binding_errors
from studio.verification import evidence_errors

pytestmark=pytest.mark.skipif(os.getenv('STUDIO_PHASER_TESTS')!='1',reason='opt-in real Phaser Docker integration')
TEMPLATE=Path(__file__).resolve().parents[1]/'templates/phaser/tower_defense'

@pytest.mark.asyncio
async def test_fixed_tower_template_uses_trusted_build_recipe(tmp_path):
    root=tmp_path/'candidate';copy_source(TEMPLATE,root)
    # Candidate build configuration must never execute inside the trusted runner.
    package=json.loads((root/'package.json').read_text())
    package['scripts']['build']='touch /workspace/untrusted-script-ran'
    (root/'package.json').write_text(json.dumps(package))
    (root/'vite.config.js').write_text("throw new Error('Untrusted Vite config executed');")
    (root/'postcss.config.js').write_text("throw new Error('Untrusted PostCSS config executed');")
    evidence=await Runner().run(root,uid())
    assert evidence['passed'], evidence
    assert evidence['runner']==PHASER_IMAGE
    assert evidence['scope']=='phaser-integration-smoke' and evidence['gameplay_verified'] is False
    assert not (root/'untrusted-script-ran').exists()
    assert binding_errors(root,evidence)==[]
    assert (root/'dist/assets/asset-pack.json').is_file()
    # Integration smoke is insufficient to publish a game as fully verified.
    assert evidence_errors(evidence, 'tower_defense')

@pytest.mark.asyncio
async def test_phaser_typescript_error_does_not_leave_a_verified_build(tmp_path):
    root=tmp_path/'candidate';copy_source(TEMPLATE,root)
    (root/'src/config.ts').write_text('export const invalid = ;')
    evidence=await Runner().run(root,uid())
    assert evidence['passed'] is False and evidence['build'] is False
    assert not (root/'ludraft.artifacts.json').exists()
