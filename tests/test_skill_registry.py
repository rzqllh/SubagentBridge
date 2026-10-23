import hashlib
from pathlib import Path
import tempfile
import unittest
from subagentbridge.skills.registry import LocalSkillRegistry,SkillIntegrityError
class SkillTests(unittest.TestCase):
 def test_pinned_and_tampered(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'SKILL.md';f.write_text('trusted text');h=hashlib.sha256(f.read_bytes()).hexdigest();r=LocalSkillRegistry(d,pins={'SKILL.md':h})
   self.assertEqual(r.read_approved('SKILL.md'),'trusted text');f.write_text('unsafe override')
   with self.assertRaises(SkillIntegrityError):r.read_approved('SKILL.md')
 def test_unknown_denied(self):
  with tempfile.TemporaryDirectory() as d:
   (Path(d)/'NEW.md').write_text('hello');r=LocalSkillRegistry(d,pins={})
   with self.assertRaises(SkillIntegrityError):r.read_approved('NEW.md')
 def test_escape_denied(self):
  with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
   f=Path(outside)/'x';f.write_text('x');r=LocalSkillRegistry(d,pins={'../x':'0'*64})
   with self.assertRaises((FileNotFoundError,SkillIntegrityError)):r.read_approved('../x')
 def test_symlink_denied(self):
  with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as out:
   f=Path(out)/'secret';f.write_text('x');l=Path(d)/'skill.md'
   try:l.symlink_to(f)
   except (OSError,NotImplementedError):self.skipTest('symlink unavailable')
   r=LocalSkillRegistry(d,pins={'skill.md':hashlib.sha256(b'x').hexdigest()})
   with self.assertRaises(SkillIntegrityError):r.read_approved('skill.md')
if __name__=='__main__':unittest.main()
