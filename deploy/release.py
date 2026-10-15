"""File Manager release gates on the approved manager; private configuration stays private."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tarfile
import time

BASE = Path('/root/arnatech-releases')
SOURCE = Path('/root/Project/arna_file_manager')
SERVICE = 'file_manager'
REPOSITORY = 'ardzix/file_manager'
PUBLIC_KEY_TARGET = 'storage_sso_public'
RUNTIME_TARGET = 'storage_runtime'


def private_json(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600), 'w') as stream:
        json.dump(value, stream, indent=2)
    path.chmod(0o600)


def run(args, *, input=None, timeout=120, visible=False):
    result = subprocess.run(args, input=input, capture_output=True, text=True, timeout=timeout)
    if visible:
        print(result.stdout[-18000:], flush=True)
        print(result.stderr[-14000:], flush=True)
    if result.returncode:
        raise RuntimeError('Release command failed: ' + ' '.join(args[:3]) + '; rollout gate stopped')
    return result.stdout


def service_info():
    return json.loads(run(['docker','service','inspect',SERVICE]))[0]


def containers():
    return run(['docker','ps','-q','--filter','label=com.docker.swarm.service.name='+SERVICE]).splitlines()


def digest_valid(digest):
    return bool(re.fullmatch(re.escape(REPOSITORY)+r'@sha256:[0-9a-f]{64}', digest))


def validate_configuration(values, old):
    required = ('SECRET_KEY','DB_NAME','DB_USER','DB_PASSWORD','DB_HOST','ALLOWED_HOSTS',
                'SSO_INTROSPECTION_CLIENT_ID','SSO_INTROSPECTION_CLIENT_SECRET','S3_ACCESS_KEY_ID','S3_SECRET_ACCESS_KEY','S3_BUCKET_NAME','S3_ENDPOINT_URL')
    missing=[key for key in required if not values.get(key) or values[key].startswith('<')]
    if missing:
        raise RuntimeError('Incomplete file-manager-env credential; missing configured values for: '+', '.join(missing))
    if values.get('DEBUG','false').lower() not in ('false','0') or values.get('SEED_DEMO_DATA','false').lower() not in ('false','0'):
        raise RuntimeError('Production debug and demo seeding must be disabled')
    ignored = {'PHOTOBOOTH_PRODUCT_CODES','DUMMY_ROLLOUT_TS','PUBLIC_KEY_PATH','STORAGE_RUNTIME_SECRET_PATH'}
    if any(key not in values for key in old if key not in ignored):
        raise RuntimeError('New credential omits existing runtime settings; refusing configuration loss')
    for key in ('DB_NAME','DB_USER','DB_PASSWORD','DB_HOST','DB_PORT','S3_ACCESS_KEY_ID','S3_SECRET_ACCESS_KEY','S3_BUCKET_NAME','S3_ENDPOINT_URL','S3_REGION_NAME'):
        if old.get(key) and old[key] != values.get(key):
            raise RuntimeError('Database or object-store binding changed; this release preserves existing credentials and data locations')
    if values.get('JWT_AUDIENCE','storage') != 'storage' or values.get('JWT_ISSUER','https://sso.arnatech.id') != 'https://sso.arnatech.id':
        raise RuntimeError('Wrong SSO issuer/audience for File Manager')
    if values.get('SSO_BASE_URL','https://sso.arnatech.id').rstrip('/') != 'https://sso.arnatech.id':
        raise RuntimeError('Wrong SSO backend endpoint')
    return {**values, 'PUBLIC_KEY_PATH':'/run/secrets/'+PUBLIC_KEY_TARGET}


def baseline_configuration(container_spec, container_id):
    values=dict(item.split('=',1) for item in container_spec.get('Env',[]))
    pointer=values.get('STORAGE_RUNTIME_SECRET_PATH')
    if pointer:
        if pointer!='/run/secrets/'+RUNTIME_TARGET:
            raise RuntimeError('Unexpected existing runtime secret path')
        code='from pathlib import Path;print(Path('+repr(pointer)+').read_text())'
        values=json.loads(run(['docker','exec',container_id,'python','-c',code]))
        if not isinstance(values,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in values.items()):
            raise RuntimeError('Invalid existing private runtime configuration')
    return values


def secret_update_args(container_spec, record):
    args=[]
    for mount in container_spec.get('Mounts',[]):
        if mount['Target'] not in ('/app/.env','/app/public.pem','/etc/supervisor/conf.d/supervisord.conf'):
            raise RuntimeError('Unexpected runtime mount; review rather than dropping it')
        args+=['--mount-rm',mount['Target']]
    for secret in container_spec.get('Secrets',[]):
        args+=['--secret-rm',secret['SecretName']]
    for env in container_spec.get('Env',[]):
        args+=['--env-rm',env.split('=',1)[0]]
    args+=['--env-add','STORAGE_RUNTIME_SECRET_PATH=/run/secrets/'+RUNTIME_TARGET]
    for key,target in [('runtime',RUNTIME_TARGET),('public',PUBLIC_KEY_TARGET)]:
        args+=['--secret-add','source='+record['secrets'][key]+',target='+target+',mode=0400']
    return args


def verify_runtime_spec(container_spec, record):
    if container_spec.get('Env',[])!=['STORAGE_RUNTIME_SECRET_PATH=/run/secrets/'+RUNTIME_TARGET]:
        raise RuntimeError('Runtime configuration must be mounted, not exposed as service environment')
    expected={record['secrets']['runtime']:RUNTIME_TARGET,record['secrets']['public']:PUBLIC_KEY_TARGET}
    mounted=container_spec.get('Secrets',[])
    if len(mounted)!=2 or {s['SecretName']:s.get('File',{}).get('Name') for s in mounted}!=expected:
        raise RuntimeError('Runtime secret mounts differ from the tested release')
    if any(s.get('File',{}).get('Mode')!=0o400 for s in mounted) or container_spec.get('Mounts'):
        raise RuntimeError('Runtime secrets must be mounted read-only with mode 0400 and no legacy binds')


def prepare_image(folder, source, commit, tag):
    metadata=json.loads((folder/'cloud-build.json').read_text())
    if metadata.get('commit')!=commit or metadata.get('tag')!=tag or metadata.get('platform')!='linux/amd64':
        raise RuntimeError('Build artifact does not match the selected release')
    mode=metadata.get('build_backend')
    if mode=='docker-build-cloud':
        if metadata.get('builder_endpoint')!='arnatechid/default':
            raise RuntimeError('Unapproved cloud builder')
        with (folder/'runtime-image.tar').open('rb') as stream:
            digest=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024*1024),b''):
                digest.update(chunk)
            checksum=digest.hexdigest()
        if checksum!=metadata.get('archive_sha256'):
            raise RuntimeError('Cloud image archive checksum mismatch')
        run(['docker','load','--input',str(folder/'runtime-image.tar')],timeout=300)
    elif mode=='manager-local':
        run(['docker','build','--platform','linux/amd64','--label','org.opencontainers.image.revision='+commit,'-t',tag,str(source)],timeout=1800,visible=True)
    else:
        raise RuntimeError('Unknown build backend; no implicit local fallback')
    image=json.loads(run(['docker','image','inspect',tag]))[0]
    if image['Architecture']!='amd64' or image['Config'].get('Labels',{}).get('org.opencontainers.image.revision')!=commit:
        raise RuntimeError('Built image revision/platform does not match selected release')
    return metadata,image['Id']


def wait_task(service, seconds=180):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        ids=run(['docker','service','ps','-q',service]).splitlines()
        if ids:
            task=json.loads(run(['docker','inspect',ids[0]]))[0]
            state=task['Status']
            if state['State']=='complete' and state.get('ContainerStatus',{}).get('ExitCode')==0:
                return task['ID']
            if state['State'] in ('failed','rejected','shutdown'):
                raise RuntimeError('One-off gate failed; production rollout was not started')
        time.sleep(2)
    raise RuntimeError('One-off gate timed out; production rollout was not started')


def test_image(image):
    suffix=secrets.token_hex(5)
    network='storage-ci-'+suffix
    database=network+'-pg'
    password=secrets.token_urlsafe(32)
    pg_image=json.loads(run(['docker','inspect','postgres']))[0]['Image']
    try:
        run(['docker','network','create','--internal',network])
        run(['docker','run','-d','--memory','192m','--name',database,'--network',network,
             '-e','POSTGRES_PASSWORD='+password,'-e','POSTGRES_DB=storage_device_isolated',pg_image])
        for _ in range(30):
            if subprocess.run(['docker','exec',database,'pg_isready','-U','postgres'],capture_output=True).returncode==0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Isolated PostgreSQL unavailable')
        run(['docker','run','--rm','--memory','384m','--network',network,
             '-e','STORAGE_TEST_POSTGRES_HOST='+database,'-e','STORAGE_TEST_POSTGRES_PASSWORD='+password,
             '--entrypoint','python',image,'scripts/test_device_access.py'],timeout=300,visible=True)
        run(['docker','run','--rm','--network','none','--entrypoint','python',image,
             '-m','unittest','discover','-s','deploy/tests','-v'],visible=True)
    finally:
        subprocess.run(['docker','rm','-f',database],capture_output=True)
        subprocess.run(['docker','network','rm',network],capture_output=True)


def artifact(folder, commit):
    record=json.loads((folder/'release.json').read_text())
    if record.get('commit')!=commit or record.get('tests')!='passed' or not digest_valid(record.get('digest','')):
        raise RuntimeError('Release does not identify a tested exact artifact')
    image=json.loads(run(['docker','image','inspect',record['digest']]))[0]
    if image['Architecture']!='amd64' or image['Config'].get('Labels',{}).get('org.opencontainers.image.revision')!=commit:
        raise RuntimeError('Artifact revision/platform does not match the release')
    return record


def build(commit, folder):
    run(['git','-C',str(SOURCE),'fetch','origin','main'])
    if run(['git','-C',str(SOURCE),'rev-parse','origin/main']).strip()!=commit:
        raise RuntimeError('Selected source must be current remote main')
    if (folder/'release.json').exists():
        print(json.dumps(artifact(folder,commit)),flush=True)
        return
    source=folder/'source'
    source.mkdir(mode=0o700)
    with tarfile.open(folder/'source.tar') as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk() or not (source/member.name).resolve().is_relative_to(source):
                raise RuntimeError('Unsafe source archive')
        archive.extractall(source)
    if (source/'.env').exists() or list(source.glob('*.pem')):
        raise RuntimeError('Runtime credentials cannot enter build context')
    tag=REPOSITORY+':'+folder.name.removeprefix('storage-')
    build_metadata,tested_image_id=prepare_image(folder,source,commit,tag)
    probe='from pathlib import Path;import os;p=Path("/app");assert not (p/".env").exists();assert not list(p.rglob("*.pem"));assert not os.environ.get("DB_PASSWORD");print("Clean runtime image verified")'
    run(['docker','run','--rm','--network','none','--entrypoint','python',tag,'-c',probe],visible=True)
    test_image(tag)
    run(['docker','push',tag],timeout=300,visible=True)
    run(['docker','pull',tag],timeout=180)
    image=json.loads(run(['docker','image','inspect',tag]))[0]
    digests=[value for value in image.get('RepoDigests',[]) if value.startswith(REPOSITORY+'@sha256:')]
    if len(digests)!=1 or image['Architecture']!='amd64' or image['Id']!=tested_image_id:
        raise RuntimeError('Published digest/platform unresolved')
    record={'commit':commit,'tag':tag,'digest':digests[0],'platform':'linux/amd64','tests':'passed','status':'published',
            'build_backend':build_metadata['build_backend'],'tested_image_id':tested_image_id}
    private_json(folder/'release.json',record)
    print(json.dumps(record),flush=True)


def gate(folder, record, name, code=None, migration=False):
    cs=service_info()['Spec']['TaskTemplate']['ContainerSpec']
    manager=run(['docker','info','--format','{{.Swarm.NodeID}}']).strip()
    args=['docker','service','create','--detach=true','--with-registry-auth','--name',name,
          '--restart-condition','none','--limit-memory','384M','--constraint','node.id=='+manager,
          '--entrypoint','python','--env','STORAGE_RUNTIME_SECRET_PATH=/run/secrets/'+RUNTIME_TARGET]
    for network in service_info()['Spec']['TaskTemplate']['Networks']:
        args+=['--network',network['Target']]
    for key,target in [('runtime',RUNTIME_TARGET),('public',PUBLIC_KEY_TARGET)]:
        args+=['--secret','source='+record['secrets'][key]+',target='+target+',mode=0400']
    args+=[record['digest']]
    args+=['manage.py','migrate','--noinput'] if migration else ['-c',code]
    try:
        run(args)
        return wait_task(name)
    except Exception:
        # Protected diagnostics may include internal identifiers; never print raw logs.
        result=subprocess.run(['docker','service','logs','--raw','--tail','80',name],capture_output=True,text=True,timeout=15)
        private_json(folder/(name+'-error.json'),{'stdout':result.stdout,'stderr':result.stderr})
        raise
    finally:
        subprocess.run(['docker','service','rm',name],capture_output=True)


def migrate(commit, folder):
    record=artifact(folder,commit)
    if record.get('migration')=='complete_exit_0':
        print(json.dumps(record),flush=True)
        return
    baseline=service_info()
    ids=containers()
    if len(ids)!=1:
        raise RuntimeError('Expected one existing healthy File Manager replica')
    container=json.loads(run(['docker','inspect',ids[0]]))[0]
    if not container['State'].get('Running'):
        raise RuntimeError('Baseline replica is not healthy')
    private_json(folder/'previous-service.json',baseline)
    parse="from decouple import RepositoryEnv;import json;print(json.dumps(RepositoryEnv('/input/runtime.env').data))"
    values=json.loads(run(['docker','run','--rm','--network','none','--mount','type=bind,src='+str(folder/'runtime.env')+',dst=/input/runtime.env,readonly','--entrypoint','python',record['digest'],'-c',parse]))
    old=baseline_configuration(baseline['Spec']['TaskTemplate']['ContainerSpec'],ids[0])
    values=validate_configuration(values,old)
    oldkey=run(['docker','exec',ids[0],'python','-c',"import django;django.setup();from django.conf import settings;from pathlib import Path;import sys;sys.stdout.write(Path(settings.PUBLIC_KEY_PATH).read_text())"])
    public=(folder/'public.pem').read_text()
    if public.strip()!=oldkey.strip():
        raise RuntimeError('SSO verification key changed; this release does not rotate keys')
    from_key=hashlib.sha256(public.encode()).hexdigest()
    record['public_key_fingerprint']=from_key
    names={key:'storage-'+key+'-'+folder.name.removeprefix('storage-') for key in ('runtime','public')}
    for key,name in names.items():
        run(['docker','secret','create',name,'-'],input=json.dumps(values) if key=='runtime' else public)
    record['secrets']=names
    private_json(folder/'release.json',record)
    validate="""import django;django.setup()
from django.conf import settings
from django.db import connection
from django.core.management import call_command
from apps.authn.introspection import inspector_probe
call_command('check')
with connection.cursor() as cursor:cursor.execute('SELECT 1');cursor.fetchone()
assert inspector_probe()
print('DB, configuration and SSO inspector verified')"""
    gate(folder,record,'storage-validate-'+commit[:12],validate)
    task=gate(folder,record,'storage-migrate-'+commit[:12],migration=True)
    record.update(migration='complete_exit_0',migration_task=task,status='migrated')
    private_json(folder/'release.json',record)
    print(json.dumps(record),flush=True)


def verify(commit, folder):
    record=artifact(folder,commit)
    deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        service=service_info()
        state=service.get('UpdateStatus',{}).get('State')
        if state in ('paused','rollback_started','rollback_completed','rollback_paused'):
            raise RuntimeError('Requested release did not converge: '+state)
        ids=containers()
        if state=='completed' and len(ids)==1 and service['Spec']['TaskTemplate']['ContainerSpec']['Image']==record['digest']:
            item=json.loads(run(['docker','inspect',ids[0]]))[0]
            if item['State'].get('Health',{}).get('Status')=='healthy':break
        time.sleep(3)
    else:
        raise RuntimeError('Production rollout timed out')
    verify_runtime_spec(service['Spec']['TaskTemplate']['ContainerSpec'],record)
    inline_names={v.split('=',1)[0] for v in item['Config'].get('Env',[])}
    values=baseline_configuration(service['Spec']['TaskTemplate']['ContainerSpec'],ids[0])
    if inline_names.intersection(values):
        raise RuntimeError('Runtime configuration leaked into container inspect environment')
    code="""import django;django.setup()
from django.core.management import call_command
from apps.authn.introspection import inspector_probe
call_command('migrate',check=True)
assert inspector_probe()
print('Storage API, schema and SSO inspector verified')"""
    run(['docker','exec',ids[0],'python','-c',code],visible=True)
    for path in ('/health/live','/health/ready'):
        run(['curl','-fsS','--max-time','12','https://storage.arnatech.id'+path])
    status=run(['curl','-sS','--max-time','12','-o','/dev/null','-w','%{http_code}','https://storage.arnatech.id/api/v1/folders/root/children?owner_scope=org']).strip()
    if status!='401':raise RuntimeError('Unauthenticated private file listing must reject with 401')
    record['status']='verified'
    private_json(folder/'release.json',record)
    print(json.dumps(record),flush=True)


def roll(commit, folder):
    record=artifact(folder,commit)
    if record.get('migration')!='complete_exit_0':
        raise RuntimeError('Migration must complete successfully before any service update')
    if record.get('status')=='verified':
        verify(commit,folder)
        return
    baseline=json.loads((folder/'previous-service.json').read_text())
    current=service_info()
    if current['Version']['Index']!=baseline['Version']['Index']:
        raise RuntimeError('Production service changed after migration preparation; review before rollout')
    cs=current['Spec']['TaskTemplate']['ContainerSpec']
    args=['docker','service','update','--detach=true','--with-registry-auth','--image',record['digest'],
          '--update-parallelism','1','--update-order','start-first','--update-delay','10s','--update-monitor','60s',
          '--update-failure-action','rollback','--rollback-parallelism','1','--rollback-order','stop-first',
          '--stop-grace-period','60s','--health-cmd','python /app/deploy/healthcheck.py','--health-interval','15s',
          '--health-timeout','6s','--health-retries','3','--health-start-period','30s']
    args+=secret_update_args(cs,record)
    run([*args,SERVICE])
    record['status']='deployed'
    private_json(folder/'release.json',record)
    try:
        verify(commit,folder)
    except Exception:
        state=service_info().get('UpdateStatus',{}).get('State','')
        if not state.startswith('rollback'):
            run(['docker','service','rollback','--detach=true',SERVICE])
        # Observe actual recovery rather than calling command return a restored service.
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            restored=service_info()
            oldimage=baseline['Spec']['TaskTemplate']['ContainerSpec']['Image']
            ids=containers()
            if restored['Spec']['TaskTemplate']['ContainerSpec']['Image']==oldimage and restored.get('UpdateStatus',{}).get('State')=='rollback_completed' and ids:
                states=[json.loads(run(['docker','inspect',cid]))[0]['State'] for cid in ids]
                if all(s.get('Running') and ('Health' not in s or s['Health'].get('Status')=='healthy') for s in states):
                    record['status']='rolled_back'
                    private_json(folder/'release.json',record)
                    break
            time.sleep(3)
        raise


def cleanup(commit, folder):
    for path in (folder/'runtime.env', folder/'public.pem', folder/'registry/config.json',folder/'source.tar',
                 folder/'runtime-image.tar'):
        path.unlink(missing_ok=True)
    print('Temporary credential files removed; prior image/config and release evidence retained.',flush=True)


if __name__=='__main__':
    phase,commit,release=sys.argv[1:]
    if phase not in ('build','migrate','roll','verify','cleanup') or not re.fullmatch('[0-9a-f]{40}',commit) or not re.fullmatch(r'b[0-9]+-'+commit[:12]+r'-[0-9a-f]{8}',release):
        raise ValueError('Expected phase, full selected main commit and matching Jenkins release ID')
    folder=BASE/('storage-'+release)
    if not folder.is_dir():raise RuntimeError('Release must be staged before execution')
    os.environ['DOCKER_CONFIG']=str(folder/'registry')
    import fcntl
    with (BASE/'storage-release.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        {'build':build,'migrate':migrate,'roll':roll,'verify':verify,'cleanup':cleanup}[phase](commit,folder)
