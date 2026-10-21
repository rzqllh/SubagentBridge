"""Developer-owned fake integration harness checks, never QA certification."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class OfflineSmokeTests(unittest.TestCase):
    def test_fake_pm_dev_qa_flow_fail_closed(self):
        spec = importlib.util.spec_from_file_location('local_fake_smoke', ROOT/'examples'/'supervised_offline_smoke.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.run_supervised_fake_smoke()
        self.assertEqual(result['status'],'FAKE_ONLY_PASS')
        self.assertTrue(result['dependency_denial'])
        self.assertTrue(result['duplicate_messages_denied'])
        self.assertEqual(result['audit_event_count'], 4)
        self.assertTrue(all(v == 'VERIFIED' for v in result['tasks_fake_verified_before_tree_change'].values()))
        self.assertTrue(all(v != 'VERIFIED' for v in result['tasks_after_tree_change'].values()))
        self.assertEqual(result['release_status'],'UNVERIFIED')
        self.assertEqual(result['provider_calls'],0)
        self.assertEqual(result['real_executor_calls'],0)
        self.assertFalse(result['autonomy'])
        self.assertFalse(result['security_certified'])

if __name__ == '__main__':
    unittest.main()
