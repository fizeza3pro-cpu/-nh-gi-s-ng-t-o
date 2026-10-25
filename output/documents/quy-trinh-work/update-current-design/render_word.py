"""Dùng Word cho bước DOCX→PDF trên Windows, renderer đóng gói cho PDF→PNG."""
from pathlib import Path
import importlib.util
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
RUNTIME = Path('C:/Users/OS/.cache/codex-runtimes/codex-primary-runtime')
RENDERER = Path('C:/Users/OS/.codex/plugins/cache/openai-primary-runtime/documents/26.1022.11436/skills/documents/render_docx.py')
os.environ['PATH'] = str(RUNTIME / 'dependencies/native/poppler/Library/bin') + os.pathsep + os.environ['PATH']
spec = importlib.util.spec_from_file_location('packaged_docx_renderer', RENDERER)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def convert(doc_path, user_profile, convert_tmp_dir, stem, verbose=False):
    destination = Path(convert_tmp_dir) / (stem + '.pdf')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(ROOT / 'export_pdf.ps1'), '-InputFile', doc_path, '-OutputFile', str(destination)],
        capture_output=True, text=True, timeout=100, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0 or not destination.exists():
        raise RuntimeError(result.stdout + result.stderr)
    print(result.stdout.strip(), flush=True)
    return str(destination), result.stdout


renderer.convert_to_pdf = convert
renderer.main()
