"""Restore checkpointed website assets without discarding interrupted output."""
import json
import shutil
from pathlib import Path
from uuid import uuid4


def recover_build(folder):
    folder = Path(folder).resolve()
    for backup in sorted(folder.glob('.build-backup-*')):
        marker = backup / 'checkpoint.json'
        if not marker.is_file():
            continue
        if backup.resolve() != backup.absolute() or marker.resolve() != marker.absolute():
            raise OSError('Build recovery metadata is linked elsewhere.')
        checkpoint = json.loads(marker.read_text(encoding='utf-8'))
        if not isinstance(checkpoint, dict) or any(type(checkpoint.get(name)) is not bool for name in ('website', 'GENERATED_COPY.json')):
            raise ValueError('Build recovery checkpoint is incomplete; backups were kept.')
        for name in ('website', 'GENERATED_COPY.json'):
            source, target = backup / name, folder / name
            if source.resolve() != source.absolute() or target.resolve() != target.absolute():
                raise OSError('Build recovery assets are linked elsewhere.')
            staged = folder / f'.recovery-{uuid4().hex}'
            if checkpoint.get(name):
                if name == 'website':
                    # Refuse links before copying any content outside this folder.
                    if any(path.resolve() != path.absolute() for path in source.rglob('*')):
                        raise OSError('Build backup contains linked assets.')
                    shutil.copytree(source, staged)
                else:
                    shutil.copy2(source, staged)
            if target.exists():
                target.rename(backup / f'interrupted-{name}-{uuid4().hex}')
            if staged.exists():
                staged.rename(target)
        marker.rename(backup / 'recovered.json')
        (folder / 'DELIVERY.json').unlink(missing_ok=True)
    return folder
