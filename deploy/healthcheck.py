"""Local readiness without credentials or provider side effects."""
import json
from urllib.request import Request, urlopen

request = Request('http://127.0.0.1:8001/health/ready', headers={'Host':'storage.arnatech.id'})
with urlopen(request, timeout=4) as response:
    assert response.status == 200 and json.load(response)['status'] == 'ok'
