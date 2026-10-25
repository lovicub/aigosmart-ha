"""Reproduce the integrated card from a verified, read-only local checkout."""
import hashlib
from pathlib import Path
import subprocess
import sys

COMMIT = 'f4bb918d261d63a49ed40f27c194b5f8be555e8d'
ROOT = Path(__file__).resolve().parents[1]


def transform(source):
    source = source.replace('AigoSmartPremiumCard', 'AigoSmartHAIntegratedCard')
    source = source.replace('AIGOSMART_PREMIUM_CARD_VERSION', 'AIGOSMART_HA_INTEGRATED_CARD_VERSION')
    source = source.replace('aigosmart-premium-card', 'aigosmart-ha-integrated-card')
    source = source.replace('AigoSmart Premium Card', 'AigoSmart HA Integrated')
    source = source.replace('</footer>', '<div class="integrated-brand">AigoSmart HA Integrated</div></footer>')
    source = source.replace('footer span{', '.integrated-brand{color:#c7d5e8;font-size:11px;letter-spacing:.3px;line-height:1.5;margin-top:8px}footer span{')
    return '/* Adapted from pinned MIT source; see PROVENANCE.json and LICENSE. */\n(() => {\n' + source + '\n})();\n'


def main():
    checkout = Path(sys.argv[1]).resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(checkout), *args])
    if git('rev-parse', 'HEAD').decode().strip() != COMMIT:
        raise SystemExit('Source HEAD does not match pin')
    files = ['aigosmart-premium-card.js', 'LICENSE']
    snapshots = {name: git('show', f'{COMMIT}:{name}') for name in files}
    for name, content in snapshots.items():
        if (checkout / name).read_bytes() != content:
            raise SystemExit('Source file differs from pinned commit')
    dest = ROOT / 'custom_components/aigosmart/frontend'
    dest.mkdir(exist_ok=True)
    (dest / 'aigosmart-premium-card.source.js').write_bytes(snapshots[files[0]])
    (dest / 'LICENSE').write_bytes(snapshots['LICENSE'])
    (dest / 'aigosmart-ha-integrated-card.js').write_text(transform(snapshots[files[0]].decode()))
    import json
    provenance = {'repository': 'https://github.com/lovicub/aigosmart-premium-card',
                  'version': '0.1.1-beta.1', 'commit': COMMIT,
                  'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(dest.iterdir()) if p.name != 'PROVENANCE.json'}}
    (dest / 'PROVENANCE.json').write_text(json.dumps(provenance, indent=2) + '\n')


if __name__ == '__main__':
    main()
