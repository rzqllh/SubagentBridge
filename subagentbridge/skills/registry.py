"""PR-07 partial: file-content hashing and explicit allowlist; no prompt trust.

This registry does not grant runtime tool rights. On-disk file verification
has TOCTOU limitations and must be re-verified by a trusted executor.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path

class SkillIntegrityError(PermissionError):pass

class LocalSkillRegistry:
    def __init__(self, root: str|Path, *, pins:dict[str,str]):
        self.root=Path(root).resolve(strict=True)
        if not self.root.is_dir(): raise ValueError('root must be a directory')
        self.pins=dict(pins)
        if not all(len(v)==64 and all(c in '0123456789abcdef' for c in v) for v in self.pins.values()):
            raise ValueError('pins must be lowercase SHA256 hex')

    def _path(self, relative: str)->Path:
        if not relative or Path(relative).is_absolute():raise SkillIntegrityError('relative skill filename required')
        source=self.root/relative
        if source.is_symlink() or any(x.is_symlink() for x in source.parents if x!=self.root):
            raise SkillIntegrityError('skill symlink denied')
        p=source.resolve(strict=True)
        if not p.is_relative_to(self.root) or not p.is_file():raise SkillIntegrityError('skill path escapes root')
        return p

    def read_approved(self, relative:str)->str:
        expected=self.pins.get(relative)
        if expected is None:raise SkillIntegrityError('unregistered skill requires approval')
        p=self._path(relative)
        content=p.read_bytes()
        if sha256(content).hexdigest()!=expected:raise SkillIntegrityError('skill content changed: approval required')
        return content.decode('utf-8')
