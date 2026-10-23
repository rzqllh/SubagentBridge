"""PR-07 candidate: bounded, pin-only local skill text inspection.

Skills are untrusted content: this cannot grant tool rights, alter approvals or
prove TOCTOU-safe reads. The trusted executor must re-open/verify files under
an isolated OS identity before authorizing any side effect.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path, PurePosixPath

from subagentbridge.domain.contracts import Role

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
    def __init__(self, root: str | Path, *, pins: dict[str, str] | None = None):
        candidate = Path(root).absolute()
        if candidate.is_symlink() or getattr(candidate, 'is_junction', lambda: False)():
            raise SkillIntegrityError('linked skill root forbidden')
        self.root = candidate.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('root must be a directory')
        pin_map = dict(pins or {})
        if not all(
                type(name) is str and type(digest) is str and len(digest) == 64
                and all(c in '0123456789abcdef' for c in digest)
                for name, digest in pin_map.items()):
            raise ValueError('pins require text names and lowercase SHA256')
        self.pins = pin_map

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

    def discover_skills(self) -> dict[str, str]:
        """Scan registry root for readable skill markdown files and return posix path -> sha256 map."""
        discovered: dict[str, str] = {}
        for p in sorted(self.root.rglob("*.md")):
            if p.is_symlink() or getattr(p, "is_junction", lambda: False)():
                continue
            if not p.is_file():
                continue
            rel_posix = p.relative_to(self.root).as_posix()
            if not _valid_name(rel_posix):
                continue
            with p.open("rb") as stream:
                content = stream.read(MAX_SKILL_BYTES + 1)
            if len(content) <= MAX_SKILL_BYTES:
                discovered[rel_posix] = sha256(content).hexdigest()
        return discovered

    def pin_skill(self, relative: str, expected_sha256: str) -> None:
        """Register or update an approved skill pin after verification."""
        if not _valid_name(relative):
            raise SkillIntegrityError("invalid skill path for pinning")
        if (type(expected_sha256) is not str or len(expected_sha256) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha256)):
            raise ValueError("lowercase 64-char SHA256 hex string required")
        self.pins[relative] = expected_sha256

    def get_skills_for_role(self, role: Role | str) -> tuple[str, ...]:
        """Return approved pinned skill identifiers relevant to the specified role."""
        role_str = role.value if isinstance(role, Role) else str(role).upper()
        role_keywords: dict[str, tuple[str, ...]] = {
            "PM": ("plan", "orchestrate", "architecture", "verify", "context"),
            "DEVELOPER": ("execute", "debug", "prototype", "test", "interface"),
            "QA": ("review", "verify", "test", "security", "release"),
        }
        keywords = role_keywords.get(role_str, ())
        matched = []
        for name in sorted(self.pins):
            lower_name = name.lower()
            if any(kw in lower_name for kw in keywords):
                matched.append(name)
        return tuple(matched) if matched else tuple(sorted(self.pins))

    def load_harness_content(self, relative: str) -> str:
        """Load skill or rules markdown as untrusted instructional prompt content only."""
        return self.read_approved(relative)
