"""Developer-owned negative tests; not QA invariant tests."""
from __future__ import annotations
import hashlib
import tempfile
import unittest
from pathlib import Path
from subagentbridge.skills.registry import LocalSkillRegistry, SkillIntegrityError, MAX_SKILL_BYTES


class PinnedSkillHardening(unittest.TestCase):
    def test_valid_skill_read_and_traversal_spellings_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'SKILL.md').write_text('read-only instructions')
            h=hashlib.sha256((root/'SKILL.md').read_bytes()).hexdigest()
            names={'SKILL.md':h, './SKILL.md':h, 'nested/../SKILL.md':h,
                   'nested//SKILL.md':h, '..\\SKILL.md':h, 'C:/SKILL.md':h}
            registry=LocalSkillRegistry(root,pins=names)
            self.assertEqual(registry.read_approved('SKILL.md'),'read-only instructions')
            for name in list(names)[1:]:
                with self.subTest(name=name), self.assertRaises(SkillIntegrityError):
                    registry.read_approved(name)

    def test_overlarge_file_is_denied_without_unbounded_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'SKILL.md'
            p.write_bytes(b'a'*(MAX_SKILL_BYTES+1))
            registry=LocalSkillRegistry(tmp,pins={'SKILL.md':hashlib.sha256(p.read_bytes()).hexdigest()})
            with self.assertRaises(SkillIntegrityError):
                registry.read_approved('SKILL.md')

    def test_invalid_utf8_denied_after_hash_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'SKILL.md'
            p.write_bytes(b'\xff')
            registry=LocalSkillRegistry(tmp,pins={'SKILL.md':hashlib.sha256(b'\xff').hexdigest()})
            with self.assertRaises(SkillIntegrityError):
                registry.read_approved('SKILL.md')

    def test_pin_requires_exact_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                LocalSkillRegistry(tmp,pins={'SKILL.md':'A'*64})
