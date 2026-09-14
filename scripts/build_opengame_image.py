"""Build a fixed CLI bundle with Linux dependencies; no user credentials in context."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studio.opengame import CLI_SHA256, UPSTREAM_COMMIT


def build(args):
    upstream = args.upstream.resolve()
    commit = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != UPSTREAM_COMMIT:
        raise ValueError('OpenGame commit differs from the reviewed baseline')
    if hashlib.sha256((upstream / 'dist/cli.js').read_bytes()).hexdigest() != CLI_SHA256:
        raise ValueError('CLI bundle differs from the verified build')
    base = json.loads(subprocess.check_output(['docker', 'image', 'inspect', 'gamedev-runner:1']))[0]
    record = {'commit': commit, 'cli_sha256': CLI_SHA256, 'base_image': base['Id'],
              'architecture': base['Architecture'], 'bundle_source': 'previously verified host build; Linux runtime dependencies installed from upstream lockfile'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='opengame-image-', dir='/private/tmp' if sys.platform == 'darwin' else None) as temp:
        context = Path(temp)
        archive = context / 'source.tar'
        subprocess.run(['git', '-C', str(upstream), 'archive', '--format=tar', '-o', str(archive), commit], check=True)
        source = context / 'upstream'; source.mkdir()
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter='data')
        archive.unlink()
        shutil.copytree(upstream / 'dist', source / 'dist', dirs_exist_ok=True)
        for name in ('Dockerfile', 'bridge.mjs'):
            shutil.copyfile(ROOT / 'runner/opengame' / name, context / name)
        cache = context / 'npm-cache'; cache.mkdir()
        if args.npm_cache:
            # Only npm's content-addressed public-package cache, never npmrc,
            # auth files, environment variables, logs or the user's home.
            shutil.copytree(args.npm_cache.resolve() / '_cacache', cache / '_cacache')
        record['bridge_sha256'] = hashlib.sha256((context / 'bridge.mjs').read_bytes()).hexdigest()
        (context / 'manifest.json').write_text(json.dumps(record, indent=2))
        result = subprocess.run(['docker', 'build', '--progress=plain', '--build-arg',
                                 'BRIDGE_SHA=' + record['bridge_sha256'], '-t', 'gamedev-opengame-runner:1', str(context)])
        record['build_exit_code'] = result.returncode
        if result.returncode == 0:
            built = json.loads(subprocess.check_output(['docker', 'image', 'inspect', 'gamedev-opengame-runner:1']))[0]
            record['image_id'] = built['Id']
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
        return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.studio/opengame-image-build.json')
    parser.add_argument('--npm-cache', type=Path)
    raise SystemExit(build(parser.parse_args()))
