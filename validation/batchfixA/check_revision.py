import io, tarfile, subprocess, pathlib, os, sys
root=pathlib.Path.cwd()
rev=sys.argv[1]
dest=root/'validation'/'batchfixA'/rev
dest.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive',rev,'src']))) as archive:
    archive.extractall(dest,filter='data')
env=dict(os.environ,PYTHONPATH=str(dest/'src')+';tests;scripts',PYTHONDONTWRITEBYTECODE='1')
for target in sys.argv[2:]:
    result=subprocess.run([sys.executable,'-m','unittest',target],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    text=result.stdout.decode('utf8','replace')
    (root/'validation'/'batchfixA'/f'{rev}-{target}.log').write_text(text,encoding='utf8')
    print(rev,target,result.returncode,text[-4500:],flush=True)
