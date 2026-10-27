"""Build a clean manual-install archive, without credentials or reports."""
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
root = Path(__file__).resolve().parents[1]
version = json.loads((root / 'custom_components/aigosmart/manifest.json').read_text())['version']
output = root / f'dist/aigosmart-ha-{version}.zip'
output.parent.mkdir(exist_ok=True)
def write_file(archive, path, name):
    info = ZipInfo(str(name), (2026, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, path.read_bytes(), compresslevel=9)

with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for path in sorted((root / 'custom_components/aigosmart').rglob('*')):
        if path.is_file() and (path.suffix in {'.py', '.json', '.png', '.js'} or path.name == 'LICENSE') and '__pycache__' not in path.parts:
            write_file(archive, path, path.relative_to(root))
    for name in ('README.md', 'CHANGELOG.md', 'VALIDATION.md', 'hacs.json', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'docs/RELEASE_014.md', 'docs/BETA_DIAGNOSTICS.md', 'docs/SESSION_REFRESH_BETA4.md', 'docs/INTEGRATED_CARD_BETA5.md',
                 'docs/screenshots/native-mode-en.png', 'docs/screenshots/native-mode-de.png'):
        write_file(archive, root / name, name)
print(output)
