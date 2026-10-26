"""Build only the local manual-refresh experiment; no publication operations."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
component = root / 'custom_components/aigosmart'
version = json.loads((component / 'manifest.json').read_text())['version']
output = root / f'dist/aigosmart-ha-{version}-local-manual-refresh-diagnostics.zip'
output.parent.mkdir(exist_ok=True)
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for path in sorted(component.rglob('*')):
        if (path.is_file() and not path.is_symlink()
                and path.suffix in {'.py', '.json', '.png', '.js'}
                and '__pycache__' not in path.parts):
            archive.write(path, path.relative_to(root))
    for name in ('LOCAL_MANUAL_REFRESH.md', 'LOCAL_SOURCE_CONTINUITY.json'):
        archive.write(root / 'docs' / name, 'docs/' + name)
with ZipFile(output) as archive:
    assert archive.testzip() is None
    for name in archive.namelist():
        assert archive.read(name) == (root / name).read_bytes()
print(output)
