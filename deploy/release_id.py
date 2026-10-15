import hashlib
import os
from pathlib import Path
import re

commit = Path('release-commit.txt').read_text().strip()
build = os.environ['BUILD_NUMBER']
if not re.fullmatch('[0-9a-f]{40}', commit) or not build.isdecimal():
    raise ValueError('Expected checked-out full commit and Jenkins build number')
job = hashlib.sha256(os.environ['JOB_NAME'].encode()).hexdigest()[:8]
print(f'b{build}-{commit[:12]}-{job}')
