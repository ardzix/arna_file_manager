"""Write a private stage-scoped registry config; no credential output."""
import base64
import json
import os
from pathlib import Path

folder = Path('.release-private')
folder.mkdir(mode=0o700, exist_ok=True)
auth = base64.b64encode((os.environ['STORAGE_REGISTRY_USER'] + ':' + os.environ['STORAGE_REGISTRY_TOKEN']).encode()).decode()
with os.fdopen(os.open(folder/'registry.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as stream:
    json.dump({'auths': {'https://index.docker.io/v1/': {'auth': auth}}}, stream)
