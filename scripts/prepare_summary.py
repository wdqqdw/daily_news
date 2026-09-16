"""Install a pinned, CPU-capable summarizer into the disposable project cache."""
import hashlib
from pathlib import Path
import platform
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'summary'
VERSION = 'b10995'
MODEL_REPO = 'Qwen/Qwen2.5-7B-Instruct-GGUF'
MODEL_REVISION = 'bb5d59e06d9551d752d08b292a50eb208b07ab1f'
MODEL_PARTS = {
    'qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf': 'dfce12e3862a5283ccfb88221b48480e58745165de856439950d0f22590580db',
    'qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf': '539cf93f78e887edea1c04e2d7d8cdaca9d01dae9c9025bcb8accbe29df3d72a',
}
MODEL_FILE = next(iter(MODEL_PARTS))
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
    for filename, sha in MODEL_PARTS.items():
        download(f'https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{filename}', CACHE/filename, sha)
    print('Chinese summarizer ready: ' + MODEL_REPO,flush=True)

if __name__ == '__main__':
    prepare()
