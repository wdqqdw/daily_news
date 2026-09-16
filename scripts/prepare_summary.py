"""Install a pinned, CPU-capable summarizer into the disposable project cache."""
import hashlib
from pathlib import Path
import platform
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'summary'
VERSION = 'b10995'
MODEL_REPO = 'Qwen/Qwen2.5-1.5B-Instruct-GGUF'
MODEL_REVISION = '91cad51170dc346986eccefdc2dd33a9da36ead9'
MODEL_FILE = 'qwen2.5-1.5b-instruct-q4_k_m.gguf'
MODEL_SHA = '6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e'
BINARIES = {
    ('Linux','x86_64'): ('ubuntu-x64', '44bfcb9df36318853f8f6ad6b588084c7eadf6d79e263e315ad9272dc2fee4ad'),
    ('Darwin','arm64'): ('macos-arm64', '0fcbc80b076cc866395291cc54897a5ce9c7782e2774af58c89125d58d326105'),
}

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def download(url, target, sha):
    if target.exists() and digest(target) == sha:
        return
    tmp = target.with_suffix(target.suffix + '.part')
    subprocess.run(['curl','-fL','--retry','3','--connect-timeout','20','--max-time','600',url,'-o',str(tmp)], check=True, timeout=660)
    if digest(tmp) != sha:
        tmp.unlink()
        raise RuntimeError('Checksum mismatch: ' + target.name)
    tmp.replace(target)

def prepare():
    CACHE.mkdir(parents=True,exist_ok=True)
    system, sha = BINARIES[(platform.system(),platform.machine())]
    name = f'llama-{VERSION}-bin-{system}.tar.gz'
    archive = CACHE/name
    download(f'https://github.com/ggml-org/llama.cpp/releases/download/{VERSION}/{name}',archive,sha)
    runtime = CACHE/VERSION
    if not list(runtime.rglob('llama-server')):
        runtime.mkdir(exist_ok=True)
        with tarfile.open(archive) as tf:
            tf.extractall(runtime, filter='data')
    download(f'https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{MODEL_FILE}', CACHE/MODEL_FILE, MODEL_SHA)
    print('Chinese summarizer ready: ' + MODEL_REPO,flush=True)

if __name__ == '__main__':
    prepare()
