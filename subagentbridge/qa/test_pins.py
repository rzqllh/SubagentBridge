"""Read-only local integrity probe for pre-approved QA test files.

This records on-disk SHA256 only; it is NOT a trustworthy verifier principal,
clean Git checkout proof, isolation boundary, or an ExecutorReceipt. Same-user
or elevated processes can race or tamper with these files. Independent BVE and
OS identity separation remain mandatory for production QA VERIFIED.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
from collections.abc import Mapping

MAX_QA_FILE_BYTES = 8 * 1024 * 1024


class QaTestIntegrityError(PermissionError):
    pass


def validate_qa_test_path(relative: str) -> None:
    if (type(relative) is not str or not relative or '\\' in relative
            or ':' in relative or '\x00' in relative):
        raise QaTestIntegrityError('QA test path must use plain relative POSIX components')
    pure = PurePosixPath(relative)
    if (pure.is_absolute() or not relative.startswith('tests/')
            or any(piece in ('', '.', '..') for piece in relative.split('/'))
            or len(pure.parts) < 2 or pure.parts[0] != 'tests'):
        raise QaTestIntegrityError('QA tests must be pinned under tests/ with no traversal')


def verify_local_test_pins(checkout_root: str | Path,
                           pins: Mapping[str, str]) -> dict[str, str]:
    """Return verified disk hashes, refusing missing, swapped, oversized tests.

    This is an inspect-only helper, never a substitute for QA evidence/receipts.
    """
    root = Path(checkout_root).absolute()
    if not root.is_dir() or root.is_symlink() or getattr(root,'is_junction',lambda:False)():
        raise QaTestIntegrityError('checkout root must be an existing real directory')
    if not pins:
        raise QaTestIntegrityError('at least one QA-owned test pin required')
    result: dict[str, str] = {}
    for name, expected in pins.items():
        validate_qa_test_path(name)
        if (type(expected) is not str or len(expected) != 64
                or any(ch not in '0123456789abcdef' for ch in expected)):
            raise QaTestIntegrityError('SHA256 pin must be lowercase hex')
        path = root
        for component in name.split('/'):
            path = path / component
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():
                raise QaTestIntegrityError('QA test file or ancestor is linked')
        if not path.is_file():
            raise QaTestIntegrityError('QA test missing or not a regular file')
        # Conservative fail-closed limit; a production verifier requires
        # directory file handles / out-of-process confinement to close TOCTOU.
        with path.open('rb') as stream:
            blob = stream.read(MAX_QA_FILE_BYTES + 1)
        if len(blob) > MAX_QA_FILE_BYTES:
            raise QaTestIntegrityError('QA test exceeds read limit')
        actual = sha256(blob).hexdigest()
        if actual != expected:
            raise QaTestIntegrityError('QA test file hash has changed')
        result[name] = actual
    return result
