import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('storage_release',root/'deploy/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
spec = importlib.util.spec_from_file_location('storage_runtime_env',root/'config/runtime_env.py')
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


class ReleaseGuardsTests(unittest.TestCase):
    def config(self):
        return {'SECRET_KEY':'synthetic-only-secret','DB_NAME':'synthetic','DB_USER':'postgres',
            'DB_PASSWORD':'synthetic-only','DB_HOST':'postgres','ALLOWED_HOSTS':'storage.arnatech.id',
            'SSO_INTROSPECTION_CLIENT_ID':'synthetic-inspector',
            'SSO_INTROSPECTION_CLIENT_SECRET':'synthetic-only','S3_ACCESS_KEY_ID':'synthetic-only','S3_SECRET_ACCESS_KEY':'synthetic-only','S3_BUCKET_NAME':'synthetic-bucket','S3_ENDPOINT_URL':'https://s3.test'}

    def test_partial_env_cannot_replace_existing_complete_configuration(self):
        original=self.config()
        with self.assertRaises(RuntimeError):
            release.validate_configuration({'SSO_INTROSPECTION_CLIENT_ID':'new'},original)
        original['MAX_UPLOAD_SIZE_MB']='1024'
        with self.assertRaises(RuntimeError):release.validate_configuration(self.config(),original)

    def test_config_preserves_db_binding_and_rejects_wrong_sso_or_demo_seed(self):
        for field,value in [('DB_HOST','other'),('DB_PASSWORD','other'),('DEBUG','true'),
                            ('SEED_DEMO_DATA','true'),('JWT_AUDIENCE','arna-commerce')]:
            with self.subTest(field=field):
                with self.assertRaises(RuntimeError):release.validate_configuration({**self.config(),field:value},self.config())
        result=release.validate_configuration(self.config(),self.config())
        self.assertEqual(result['PUBLIC_KEY_PATH'],'/run/secrets/storage_sso_public')

    def test_only_exact_registry_digest_is_accepted(self):
        self.assertTrue(release.digest_valid('ardzix/file_manager@sha256:'+'a'*64))
        for value in ('ardzix/file_manager:latest','ardzix/arna_sso@sha256:'+'a'*64,'ardzix/file_manager@sha256:bad'):
            self.assertFalse(release.digest_valid(value))

    def test_object_store_credentials_and_bucket_are_preserved(self):
        for field in ('S3_ACCESS_KEY_ID','S3_SECRET_ACCESS_KEY','S3_BUCKET_NAME','S3_ENDPOINT_URL'):
            with self.subTest(field=field):
                with self.assertRaises(RuntimeError):release.validate_configuration({**self.config(),field:'other'},self.config())

    def test_failed_migration_record_cannot_start_service_update(self):
        with patch.object(release,'artifact',return_value={'migration':'failed'}),patch.object(release,'run') as command:
            with self.assertRaises(RuntimeError):release.roll('a'*40,Path('/synthetic'))
            command.assert_not_called()

    def test_one_off_nonzero_exit_is_not_migration_success(self):
        with patch.object(release,'run',side_effect=['task-id',json.dumps([{'ID':'task-id','Status':{'State':'failed','ContainerStatus':{'ExitCode':1}}}])]):
            with self.assertRaises(RuntimeError):release.wait_task('synthetic',seconds=1)

    def test_unknown_live_mount_stops_update_instead_of_dropping_it(self):
        record={'migration':'complete_exit_0','status':'migrated','digest':'ardzix/file_manager@sha256:'+'a'*64}
        state={'Version':{'Index':1},'Spec':{'TaskTemplate':{'ContainerSpec':{'Mounts':[{'Target':'/customer-data'}]}}}}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/'previous-service.json').write_text(json.dumps(state))
            with patch.object(release,'artifact',return_value=record),patch.object(release,'service_info',return_value=state),patch.object(release,'run') as command:
                with self.assertRaises(RuntimeError):release.roll('a'*40,path)
                command.assert_not_called()

    def test_runtime_secret_overrides_stale_env_as_one_complete_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'secret.json'
            path.write_text(json.dumps({'DB_HOST':'synthetic-new','EXTRA_FEATURE':'on'}))
            with patch.dict(os.environ,{'STORAGE_RUNTIME_SECRET_PATH':str(path),'DB_HOST':'synthetic-old'}):
                self.assertTrue(loader.load_runtime_env())
                self.assertEqual(os.environ['DB_HOST'],'synthetic-new')
                self.assertEqual(os.environ['EXTRA_FEATURE'],'on')

    def test_malformed_runtime_secret_never_partially_changes_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'secret.json'
            path.write_text(json.dumps({'DB_HOST':'new','BAD':None}))
            with patch.dict(os.environ,{'STORAGE_RUNTIME_SECRET_PATH':str(path),'DB_HOST':'old'}):
                with self.assertRaises(RuntimeError):loader.load_runtime_env()
                self.assertEqual(os.environ['DB_HOST'],'old')

    def test_all_old_values_removed_before_mounting_private_runtime(self):
        state={'Env':['DB_PASSWORD=synthetic-secret','S3_SECRET_ACCESS_KEY=synthetic-s3','DEBUG=false']}
        record={'secrets':{'runtime':'release-config','public':'release-key'}}
        args=release.secret_update_args(state,record)
        self.assertNotIn('synthetic-secret',' '.join(args))
        self.assertNotIn('synthetic-s3',' '.join(args))
        self.assertEqual(args.count('--env-rm'),3)
        self.assertEqual(args.count('--env-add'),1)
        self.assertIn('STORAGE_RUNTIME_SECRET_PATH=/run/secrets/storage_runtime',args)

    def test_verify_rejects_inline_credentials_even_with_correct_secret_mounts(self):
        record={'secrets':{'runtime':'release-config','public':'release-key'}}
        state={'Env':['STORAGE_RUNTIME_SECRET_PATH=/run/secrets/storage_runtime'],
               'Secrets':[{'SecretName':name,'File':{'Name':target,'Mode':0o400}}
                          for name,target in [('release-config','storage_runtime'),('release-key','storage_sso_public')]]}
        release.verify_runtime_spec(state,record)
        for bad in ({**state,'Env':state['Env']+['DB_PASSWORD=synthetic']},
                    {**state,'Secrets':state['Secrets'][:1]},
                    {**state,'Mounts':[{'Target':'/app/.env'}]}):
            with self.assertRaises(RuntimeError):release.verify_runtime_spec(bad,record)

    def test_next_release_compares_private_existing_db_and_s3_not_only_pointer(self):
        pointer={'Env':['STORAGE_RUNTIME_SECRET_PATH=/run/secrets/storage_runtime']}
        with patch.object(release,'run',return_value=json.dumps(self.config())):
            previous=release.baseline_configuration(pointer,'synthetic-container')
        self.assertEqual(previous,self.config())
        with self.assertRaises(RuntimeError):
            release.validate_configuration({**self.config(),'DB_PASSWORD':'changed'},previous)

    def test_cloud_archive_mismatch_stops_before_docker_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/'cloud-build.json').write_text(json.dumps({'commit':'a'*40,'platform':'linux/amd64',
                'tag':'synthetic','build_backend':'docker-build-cloud','builder_endpoint':'arnatechid/default',
                'archive_sha256':'0'*64}))
            (path/'runtime-image.tar').write_bytes(b'synthetic-tampered')
            with patch.object(release,'run') as command:
                with self.assertRaises(RuntimeError):release.prepare_image(path,path,'a'*40,'synthetic')
                command.assert_not_called()

    def test_unknown_cloud_backend_never_falls_back_to_local_build(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/'cloud-build.json').write_text(json.dumps({'commit':'a'*40,'platform':'linux/amd64',
                'tag':'synthetic','build_backend':'cloud-failed'}))
            with patch.object(release,'run') as command:
                with self.assertRaises(RuntimeError):release.prepare_image(path,path,'a'*40,'synthetic')
                command.assert_not_called()

    def test_cloud_image_from_different_revision_cannot_be_tested_or_published(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/'runtime-image.tar').write_bytes(b'synthetic')
            (path/'cloud-build.json').write_text(json.dumps({'commit':'a'*40,'platform':'linux/amd64',
                'tag':'synthetic','build_backend':'docker-build-cloud','builder_endpoint':'arnatechid/default',
                'archive_sha256':hashlib.sha256(b'synthetic').hexdigest()}))
            wrong=[{'Architecture':'amd64','Id':'synthetic','Config':{'Labels':{'org.opencontainers.image.revision':'b'*40}}}]
            with patch.object(release,'run',side_effect=['',json.dumps(wrong)]) as command:
                with self.assertRaises(RuntimeError):release.prepare_image(path,path,'a'*40,'synthetic')
                self.assertEqual(command.call_count,2)
