import importlib.util
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('storage_cloud',Path(__file__).resolve().parents[1]/'cloud_build.py')
cloud=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


class CloudIsolationTests(unittest.TestCase):
    def test_cloud_failure_stops_without_trying_local_docker_build(self):
        with patch.object(cloud.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','synthetic')) as run:
            with self.assertRaisesRegex(RuntimeError,'no local fallback'):
                cloud.command(['docker','buildx','version'])
            self.assertEqual(run.call_count,1)

    def test_archive_cannot_escape_source_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with tarfile.open(root/'source.tar','w') as archive:
                archive.addfile(tarfile.TarInfo('../runtime.env'))
            with self.assertRaisesRegex(RuntimeError,'Unsafe'):
                cloud.extract_source(root/'source.tar',root/'source')

    def test_verification_key_cannot_enter_cloud_context(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with tarfile.open(root/'source.tar','w') as archive:
                archive.addfile(tarfile.TarInfo('public.pem'))
            with self.assertRaisesRegex(RuntimeError,'credentials'):
                cloud.extract_source(root/'source.tar',root/'source')
