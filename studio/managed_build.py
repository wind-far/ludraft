"""Tracked diagnostic build under an active OpenGame resource lease."""
import asyncio
import json
import re

from .runner import RunnerError, container_options


async def run_build(staged, image, scope):
    from .opengame_executor import docker
    records, parent_id = scope
    try:
        image_id = json.loads(await docker('image', 'inspect', image))[0]['Id']
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id):
            raise ValueError
    except Exception:
        raise RunnerError('无法确认固定构建镜像，请检查 Docker 和镜像') from None
    row = records.begin(image_id, parent_id=parent_id, stage_path=staged)
    labels = {**records.labels(row), 'com.ludraft.role': 'opengame-build'}
    options = container_options(row['container_name'], staged)
    options += [part for key, value in labels.items() for part in ('--label', key + '=' + value)]
    process = creation = None
    log = bytearray()

    async def read_log():
        total = 0
        while chunk := await process.stdout.read(65536):
            total += len(chunk)
            if total > 16 * 1024 * 1024:
                raise RunnerError('构建日志超过限制')
            log.extend(chunk)
            del log[:-12000]

    async def cleanup():
        if creation is not None:
            try:
                await creation
                records.store.execute('UPDATE executor_attempts SET create_ack=1 WHERE id=?', (row['id'],))
            except Exception as exc:
                if not getattr(exc, 'uncertain', True):
                    records.store.execute('UPDATE executor_attempts SET create_ack=1 WHERE id=?', (row['id'],))
        try:
            await records.recover(docker, only={row['id']})
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()

    try:
        with (staged / '.ludraft-stage.json').open('x') as marker:
            json.dump({'owner': records.owner, 'id': row['id']}, marker)
        records.state(row['id'], 'creating')
        creation = asyncio.create_task(docker('create', *options, image_id, timeout=30))
        await asyncio.shield(creation)
        records.state(row['id'], 'created')
        process = await asyncio.create_subprocess_exec('docker', 'start', '-a', row['container_name'],
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        records.state(row['id'], 'running')
        async with asyncio.timeout(150):
            await asyncio.gather(read_log(), process.wait())
        path = staged / 'evidence.json'
        evidence = json.loads(path.read_text()) if path.exists() else {}
        evidence.update(exit_code=process.returncode, log=log.decode(errors='replace'), runner=image,
                        runner_image_id=image_id, build_execution_id=row['id'])
        evidence['passed'] = process.returncode == 0 and evidence.get('passed') is True
        records.state(row['id'], 'succeeded' if evidence['passed'] else 'failed')
    except asyncio.CancelledError:
        records.state(row['id'], 'cancelled')
        raise
    except TimeoutError:
        records.state(row['id'], 'failed')
        raise RunnerError('构建或测试超过 150 秒，资源清理结果保存在执行记录中') from None
    except Exception as exc:
        records.state(row['id'], 'failed')
        if isinstance(exc, RunnerError):
            raise
        raise RunnerError('受管构建未完成，请检查执行环境和资源记录') from None
    finally:
        finishing = asyncio.create_task(cleanup())
        while not finishing.done():
            try:
                await asyncio.shield(finishing)
            except asyncio.CancelledError:
                continue
        await finishing
    if records.get(row['id'])['cleanup'] != 'removed':
        raise RunnerError('构建资源尚未确认清理，本轮不能交付')
    return evidence
