"""Build a clean manual-install archive, without credentials or reports."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root = Path(__file__).resolve().parents[1]
version = json.loads((root / 'custom_components/aigosmart/manifest.json').read_text())['version']
output = root / f'dist/aigosmart-ha-{version}.zip'
output.parent.mkdir(exist_ok=True)
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for path in sorted((root / 'custom_components/aigosmart').rglob('*')):
        if path.is_file() and path.suffix in {'.py', '.json', '.png'} and '__pycache__' not in path.parts:
            archive.write(path, path.relative_to(root))
    for name in ('README.md', 'CHANGELOG.md', 'VALIDATION.md', 'hacs.json', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'docs/BETA_DIAGNOSTICS.md', 'docs/SESSION_REFRESH_BETA4.md',
                 'docs/screenshots/native-mode-en.png', 'docs/screenshots/native-mode-de.png'):
        archive.write(root / name, name)
print(output)
