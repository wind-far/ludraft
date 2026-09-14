"""Kill a real owning process, restart the app, and verify scoped Docker cleanup.

No model requests, host mounts, or exposed ports. Uses the pinned CLI image with
a fixed idle Node process; this tests recovery, not model generation or gameplay.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio.db import Store, uid
from studio.executor_records import ACTIVE_EXECUTION, ExecutorRecords
from studio.files import copy_source
from studio.opengame_executor import create_args, docker, verified_image
from studio.runner import Runner


async def create_idle(records, image, *, foreign=False):
    row = records.begin(image)
    labels = records.labels(row)
    if foreign:
        labels['com.ludraft.owner'] = 'foreign-fixture-owner'
    args = create_args(image, row['container_name'], labels)
    args[-1:-1] = ['--entrypoint', 'node']
    records.state(row['id'], 'creating')
    cid = (await docker(*args, '-e', 'setInterval(()=>{},1000)', timeout=30)).decode().strip()
    records.state(row['id'], 'created')
    await docker('start', cid)
    records.state(row['id'], 'running')
    return row, cid


async def worker(root, with_build=False):
    store = Store(root)
    records = ExecutorRecords(store)
    with records.lease():
        row, cid = await create_idle(records, await verified_image())
        readiness = {'id': row['id'], 'container_id': cid}
        if with_build:
            copy_source(ROOT / 'templates/phaser/tower_defense', root / 'candidate')
            ACTIVE_EXECUTION.set((records, row['id']))
            build = asyncio.create_task(Runner().run(root / 'candidate', 'recovery-fixture'))
            for _ in range(200):
                rows = records.store.query("SELECT * FROM executor_attempts WHERE kind='build'")
                if rows:
                    child = rows[0]
                    ids = (await docker('ps', '-q', '--no-trunc', '--filter',
                                        'name=^/' + child['container_name'] + '$')).decode().split()
                    if ids:
                        readiness.update(build_id=child['id'], build_container_id=ids[0], stage_path=child['stage_path'])
                        break
                if build.done():
                    await build
                    raise RuntimeError('Build finished before observing running container')
                await asyncio.sleep(0.05)
            else:
                raise RuntimeError('Build container was not observed running')
        print(json.dumps(readiness), flush=True)
        await asyncio.Future()


async def main(root):
    from studio.app import create_app
    root.mkdir(parents=True)
    child = None
    cleanup_ids = []
    stores = []
    output = {'scope': 'real CLI and diagnostic build resource recovery; no model or gameplay validation',
              'real_model_calls': 0, 'checks': {}}
    try:
        image = await verified_image()
        output['image_id'] = image
        foreign_store = Store(root / 'other-instance')
        stores.append(foreign_store)
        foreign_records = ExecutorRecords(foreign_store)
        _, other_cid = await create_idle(foreign_records, image)
        cleanup_ids.append(other_cid)
        child = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).resolve()),
            '--worker', str(root / 'interrupted'), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        readiness = json.loads(await asyncio.wait_for(child.stdout.readline(), 40))
        cleanup_ids.append(readiness['container_id'])
        before = json.loads(await docker('container', 'inspect', readiness['container_id']))[0]
        assert before['State']['Running']
        output['checks']['observed_running_before_kill'] = True
        child.kill()
        await child.wait()
        after = json.loads(await docker('container', 'inspect', readiness['container_id']))[0]
        assert after['State']['Running']
        output['checks']['container_survived_owner_process_kill'] = True
        app = create_app(root / 'interrupted')
        async with app.router.lifespan_context(app):
            records = app.state.workflow.opengame.records
            row = records.get(readiness['id'])
            assert row['state'] == 'interrupted' and row['cleanup'] == 'removed'
            remaining = await docker('ps', '-aq', '--filter', 'id=' + readiness['container_id'])
            assert not remaining.strip()
            output['checks']['app_startup_removed_owned_orphan'] = True
            output['checks']['interrupted_status_persisted'] = True
            assert json.loads(await docker('container', 'inspect', other_cid))[0]['State']['Running']
            output['checks']['other_data_root_container_preserved'] = True
            assert (await app.state.workflow.opengame.recover())['can_start']
            output['checks']['repeat_recovery_idempotent'] = True
            output['execution_summary'] = records.summary()

        child = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).resolve()),
            '--worker', str(root / 'interrupted-build'), '--with-build',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        readiness = json.loads(await asyncio.wait_for(child.stdout.readline(), 40))
        cleanup_ids.extend([readiness['container_id'], readiness['build_container_id']])
        assert json.loads(await docker('container', 'inspect', readiness['build_container_id']))[0]['State']['Running']
        child.kill()
        await child.wait()
        assert json.loads(await docker('container', 'inspect', readiness['build_container_id']))[0]['State']['Running']
        output['checks']['real_build_survived_owner_process_kill'] = True
        stage = Path(readiness['stage_path'])
        assert stage.is_dir()
        app = create_app(root / 'interrupted-build')
        async with app.router.lifespan_context(app):
            records = app.state.workflow.opengame.records
            for field in ('id', 'build_id'):
                row = records.get(readiness[field])
                assert row['state'] == 'interrupted' and row['cleanup'] == 'removed'
            for field in ('container_id', 'build_container_id'):
                assert not (await docker('ps', '-aq', '--filter', 'id=' + readiness[field])).strip()
            assert records.get(readiness['build_id'])['parent_id'] == readiness['id']
            assert not stage.exists()
            assert (root / 'interrupted-build/candidate/src/config.ts').is_file()
            output['checks']['startup_removed_cli_and_build_orphans'] = True
            output['checks']['startup_removed_only_owned_staging'] = True
            output['build_execution_summary'] = records.summary()

        mismatch_store = Store(root / 'mismatch')
        stores.append(mismatch_store)
        mismatch_records = ExecutorRecords(mismatch_store)
        row, mismatch_cid = await create_idle(mismatch_records, image, foreign=True)
        cleanup_ids.append(mismatch_cid)
        with mismatch_records.lease():
            result = await mismatch_records.recover(docker)
        assert result['pending_cleanup'] == 1 and not result['can_start']
        assert json.loads(await docker('container', 'inspect', mismatch_cid))[0]['State']['Running']
        output['checks']['mismatched_owner_preserved_and_blocks_execution'] = True
        output['passed'] = all(output['checks'].values())
    finally:
        if child and child.returncode is None:
            child.kill()
            await child.wait()
        failures = []
        for cid in cleanup_ids:
            present = await docker('ps', '-aq', '--filter', 'id=' + cid)
            if present.strip():
                await docker('rm', '-f', cid)
            if (await docker('ps', '-aq', '--filter', 'id=' + cid)).strip():
                failures.append(cid)
        output['probe_containers_remaining'] = failures
        for store in stores:
            store.con.close()
        (root / 'recovery.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    assert output.get('passed') and not output['probe_containers_remaining']
    print(json.dumps({'passed': True, 'report': str(root / 'recovery.json'), 'checks': output['checks']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--with-build', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    asyncio.run(worker(args.worker, args.with_build) if args.worker else main(
        (args.output or ROOT / '.studio/executor-recovery-integration' / uid()).resolve()))
