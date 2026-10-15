"""Export one Cloud-built image for isolated tests before registry publication.

Only a clean Git archive is sent to Build Cloud. Runtime credentials are bound
in a later Jenkins stage, and registry auth stays outside the build context.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

REPOSITORY = 'ardzix/file_manager'
ENDPOINT = 'arnatechid/default'


def command(args, *, visible=False):
    result = subprocess.run(args, text=True, capture_output=not visible, timeout=1800)
    if result.returncode:
        raise RuntimeError('Docker Build Cloud failed; no local fallback or production update was started')
    return result.stdout or ''


def extract_source(archive_path, source):
    source.mkdir(mode=0o700)
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk() or not (source/member.name).resolve().is_relative_to(source.resolve()):
                raise RuntimeError('Unsafe source archive')
        archive.extractall(source)
    if (source/'.env').exists() or list(source.rglob('*.pem')) or list(source.rglob('*.key')):
        raise RuntimeError('Runtime credentials cannot enter the cloud build context')


def main():
    private = Path('.release-private').resolve()
    commit = Path('release-commit.txt').read_text().strip()
    release = Path('release-id.txt').read_text().strip()
    if not re.fullmatch('[0-9a-f]{40}', commit) or not re.fullmatch(r'b[0-9]+-'+commit[:12]+r'-[0-9a-f]{8}', release):
        raise RuntimeError('Invalid release identity')
    mode = os.environ.get('USE_DOCKER_CLOUD', 'true').lower()
    if mode not in ('true', 'false'):
        raise RuntimeError('USE_DOCKER_CLOUD must be true or false')
    record = {'commit': commit, 'platform': 'linux/amd64', 'tag': REPOSITORY+':'+release,
              'build_backend': 'docker-build-cloud' if mode == 'true' else 'manager-local'}
    if mode == 'true':
        if os.environ.get('DOCKER_CLOUD_BUILDER_ENDPOINT') != ENDPOINT:
            raise RuntimeError('Use the existing approved Arnatech cloud endpoint')
        docker_config = private/'docker'
        docker_config.mkdir(mode=0o700)
        config = json.loads((private/'registry.json').read_text())
        config['cliPluginsExtraDirs'] = [str(Path.home()/'.docker/cli-plugins')]
        config_path = docker_config/'config.json'
        config_path.write_text(json.dumps(config))
        config_path.chmod(0o600)
        os.environ['DOCKER_CONFIG'] = str(docker_config)
        os.environ['BUILDX_CONFIG'] = str(private/'buildx')
        command(['docker', 'buildx', 'version'], visible=True)
        builder = command(['docker', 'buildx', 'create', '--driver', 'cloud', ENDPOINT]).strip()
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+', builder):
            raise RuntimeError('Cloud builder identity could not be resolved')
        command(['docker', 'buildx', 'inspect', '--bootstrap', builder], visible=True)
        source = private/'cloud-source'
        extract_source('storage-source.tar', source)
        image_tar = private/'runtime-image.tar'
        # The installed Cloud driver supports --load but rejects a direct tar
        # destination. Save that same loaded image; do not rebuild on the agent.
        try:
            command(['docker', 'buildx', 'build', '--builder', builder, '--platform', 'linux/amd64',
                     '--label', 'org.opencontainers.image.revision='+commit, '--tag', record['tag'],
                     '--load', str(source)], visible=True)
            command(['docker', 'image', 'save', '--output', str(image_tar), record['tag']])
        finally:
            subprocess.run(['docker', 'image', 'rm', record['tag']], capture_output=True, timeout=60)
        with image_tar.open('rb') as stream:
            checksum = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                checksum.update(chunk)
            record['archive_sha256'] = checksum.hexdigest()
        record['builder_endpoint'] = ENDPOINT
    path = private/'cloud-build.json'
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
