import asyncio
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

IMAGE = 'gamedev-runner:1'
PHASER_IMAGE = 'gamedev-phaser-runner:1'


class RunnerError(RuntimeError):
    pass


def container_options(name, staged):
    return ['--name', name, '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '128',
            '--memory', '768m', '--cpus', '1', '--user', f'{os.getuid() or 1000}:{os.getgid() or 1000}',
            '--env', 'HOME=/tmp', '--tmpfs', '/tmp:rw,nosuid,nodev,size=192m', '--shm-size', '128m',
            '--mount', f'type=bind,source={staged},target=/workspace']


@contextmanager
def staging_directory():
    from .executor_records import ACTIVE_EXECUTION
    directory = Path(tempfile.mkdtemp(prefix='gamedev-runner-',
        dir='/private/tmp' if os.uname().sysname == 'Darwin' else None)).resolve()
    try:
        yield directory
    finally:
        scope = ACTIVE_EXECUTION.get()
        pending = scope and scope[0].store.one('''SELECT id FROM executor_attempts
            WHERE stage_path=? AND cleanup!='removed' LIMIT 1''', (str(directory),))
        # Keep files mounted by an unconfirmed container for restart recovery.
        if not pending and directory.exists():
            shutil.rmtree(directory)


class Runner:
    async def available(self):
        process = None
        try:
            process = await asyncio.create_subprocess_exec('docker', 'image', 'inspect', IMAGE,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            return await asyncio.wait_for(process.wait(), 10) == 0
        except (OSError, asyncio.TimeoutError):
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            return False

    async def _probe(self, *args):
        process = None
        try:
            process = await asyncio.create_subprocess_exec('docker', *args,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            return await asyncio.wait_for(process.wait(), 4) == 0
        except (OSError, asyncio.TimeoutError):
            return False
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()

    async def diagnostics(self):
        if not shutil.which('docker'):
            return {'cli': False, 'daemon': None, 'image': None}
        if not await self._probe('info'):
            return {'cli': True, 'daemon': False, 'image': None}
        return {'cli': True, 'daemon': True, 'image': await self._probe('image', 'inspect', IMAGE)}

    async def run(self, workspace: Path, run_id: str):
        # Docker Desktop cannot read macOS Documents without extra privacy permission.
        # Stage only this candidate in the OS temporary directory; never mount the repository or secrets.
        from .project_files import manifest, source_digest
        from .artifacts import BUILD_MANIFEST
        project_digest=source_digest(workspace) if manifest(workspace) is not None else None
        for name in ('dist', 'evidence.json', BUILD_MANIFEST):
            target = workspace / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        with staging_directory() as directory:
            staged = Path(directory).resolve()
            shutil.copytree(workspace, staged, dirs_exist_ok=True)
            evidence = await self._execute(staged, run_id)
            if project_digest is not None and (source_digest(staged)!=project_digest or source_digest(workspace)!=project_digest):
                evidence.update(passed=False,error='验证期间源码或素材发生变化，必须重新执行验证')
            if (staged / 'dist').is_dir():
                shutil.copytree(staged / 'dist', workspace / 'dist')
            screenshot = staged / 'phaser-smoke.png'
            if screenshot.is_file() and not screenshot.is_symlink() and screenshot.stat().st_size <= 10 * 1024 * 1024:
                shutil.copyfile(screenshot, workspace / screenshot.name)
            if manifest(workspace) is not None and evidence.get('passed') is True:
                from .artifacts import capture_artifacts
                evidence.update(capture_artifacts(workspace))
            (workspace / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
            return evidence

    async def _execute(self, staged: Path, run_id: str):
        from .project_files import manifest
        from .template_registry import get_template
        project = manifest(staged)
        image = PHASER_IMAGE if project is not None and get_template(project.template_id, project.template_version).engine == 'phaser' else IMAGE
        from .executor_records import ACTIVE_EXECUTION
        if scope := ACTIVE_EXECUTION.get():
            from .managed_build import run_build
            return await run_build(staged, image, scope)
        name = 'gamedev-' + run_id
        args = ['docker', 'run', '--rm', *container_options(name, staged), image]
        process = None
        try:
            process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            output, _ = await asyncio.wait_for(process.communicate(), 150)
            evidence_path = staged / 'evidence.json'
            evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
            evidence['exit_code'] = process.returncode
            evidence['log'] = output.decode(errors='replace')[-12000:]
            evidence['passed'] = process.returncode == 0 and evidence.get('passed') is True
            evidence['runner'] = image
            return evidence
        except FileNotFoundError:
            raise RunnerError('找不到 Docker。请安装并启动 Docker，然后构建 runner 镜像。') from None
        except asyncio.TimeoutError:
            raise RunnerError('构建或测试超过 150 秒，容器已终止。') from None
        finally:
            if process and process.returncode is None:
                cleanup = await asyncio.create_subprocess_exec('docker', 'rm', '-f', name,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await cleanup.wait()
                # A client can remain stuck waiting for a mount request even when no container was created.
                if process.returncode is None:
                    process.terminate()
                await process.wait()
