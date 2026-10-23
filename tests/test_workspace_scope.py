from pathlib import Path
import tempfile
import unittest
from subagentbridge.workspaces.scope import ScopedWorkspace, dispatch_folder_name

class ScopeTests(unittest.TestCase):
    def test_normal_relative(self):
        with tempfile.TemporaryDirectory() as d:
            ws=ScopedWorkspace(d)
            self.assertEqual(ws.require_path('src/new.py'),(Path(d)/'src/new.py').resolve())
    def test_parent_escape_and_absolute(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            ws=ScopedWorkspace(d)
            for x in ('../escape',Path(outside)/'secret'):
                with self.subTest(x=str(x)), self.assertRaises(PermissionError):
                    ws.require_path(x)
    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            try: (Path(d)/'link').symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError): self.skipTest('symlink privilege unavailable')
            ws=ScopedWorkspace(d)
            with self.assertRaises(PermissionError): ws.require_path('link/secret')
    def test_same_dispatch_stable_distinct(self):
        self.assertEqual(dispatch_folder_name('T','D'),dispatch_folder_name('T','D'))
        self.assertNotEqual(dispatch_folder_name('T','D'),dispatch_folder_name('T','E'))
        self.assertFalse('/' in dispatch_folder_name('../','..\\'))
    def test_root_must_exist(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): ScopedWorkspace(Path(d)/'missing')

if __name__=='__main__':unittest.main()
