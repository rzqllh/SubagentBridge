"""PR-07 candidate: bounded, pin-only local skill text inspection.

Skills are untrusted content: this cannot grant tool rights, alter approvals or
prove TOCTOU-safe reads. The trusted executor must re-open/verify files under
an isolated OS identity before authorizing any side effect.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path, PurePosixPath

MAX_SKILL_BYTES = 2 * 1024 * 1024


class SkillIntegrityError(PermissionError):
    pass


def _valid_name(name: str) -> bool:
    if (type(name) is not str or not name or len(name) > 1024 or '\\' in name
            or ':' in name or '\x00' in name):
        return False
    parts = name.split('/')
    return (len(parts) >= 1 and all(p and p not in ('.', '..') for p in parts)
            and not PurePosixPath(name).is_absolute())


class LocalSkillRegistry:
    def __init__(self, root: str | Path, *, pins: dict[str, str]):
        candidate = Path(root).absolute()
        if candidate.is_symlink() or getattr(candidate, 'is_junction', lambda: False)():
            raise SkillIntegrityError('linked skill root forbidden')
        self.root = candidate.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('root must be a directory')
        if type(pins) is not dict or not all(
                type(name) is str and type(digest) is str and len(digest) == 64
                and all(c in '0123456789abcdef' for c in digest)
                for name, digest in pins.items()):
            raise ValueError('pins require text names and lowercase SHA256')
        self.pins = dict(pins)

    def _path(self, relative: str) -> Path:
        if not _valid_name(relative):
            raise SkillIntegrityError('canonical POSIX relative skill filename required')
        source = self.root
        for part in relative.split('/'):
            source = source / part
            if source.is_symlink() or getattr(source, 'is_junction', lambda: False)():
                raise SkillIntegrityError('skill symlink/junction forbidden')
        p = source.resolve(strict=True)
        if not p.is_relative_to(self.root) or not p.is_file():
            raise SkillIntegrityError('skill path escapes root or is not a file')
        return p

    def read_approved(self, relative: str) -> str:
        if not _valid_name(relative):
            raise SkillIntegrityError('invalid skill path')
        expected = self.pins.get(relative)
        if expected is None:
            raise SkillIntegrityError('unregistered skill requires approval')
        p = self._path(relative)
        with p.open('rb') as stream:
            content = stream.read(MAX_SKILL_BYTES + 1)
        if len(content) > MAX_SKILL_BYTES:
            raise SkillIntegrityError('skill file exceeds bounded read limit')
        if sha256(content).hexdigest() != expected:
            raise SkillIntegrityError('skill content changed: approval required')
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise SkillIntegrityError('skill text is not valid UTF-8') from exc
