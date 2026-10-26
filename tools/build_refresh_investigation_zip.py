"""Reproducible local-only archive; allowlisted sources, no account data."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'custom_components/aigosmart'
OUTPUT = ROOT / 'dist/aigosmart-ha-0.1.4-beta.6-local-refresh-investigation.zip'


def build():
    manifest = json.loads((COMPONENT / 'manifest.json').read_text())
    assert manifest['version'] == '0.1.4-beta.6'
    assert 'http' in manifest['after_dependencies']
    paths = sorted(p for p in COMPONENT.rglob('*') if p.is_file()
                   and not p.is_symlink() and '__pycache__' not in p.parts
                   and (p.suffix in {'.py', '.json', '.png', '.js'} or p.name == 'LICENSE'))
    paths += [ROOT / name for name in (
        'docs/LOCAL_MANUAL_REFRESH.md', 'docs/LOCAL_SOURCE_CONTINUITY.json',
        'docs/LOCAL_REFRESH_INVESTIGATION.md', 'docs/ISSUE11_SOURCE_CONTINUITY.json',
        'tools/build_refresh_investigation_zip.py')]
    OUTPUT.parent.mkdir(exist_ok=True)
    with ZipFile(OUTPUT, 'w', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(paths):
            info = ZipInfo(path.relative_to(ROOT).as_posix(), (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    with ZipFile(OUTPUT) as archive:
        assert archive.testzip() is None
        expected = {p.relative_to(ROOT).as_posix() for p in paths}
        assert set(archive.namelist()) == expected
        for name in expected:
            assert archive.read(name) == (ROOT / name).read_bytes()
    return hashlib.sha256(OUTPUT.read_bytes()).hexdigest()


if __name__ == '__main__':
    first = build()
    assert build() == first
    print(OUTPUT)
    print('SHA256', first)
    print('Two builds identical; complete archive/source byte parity verified')
