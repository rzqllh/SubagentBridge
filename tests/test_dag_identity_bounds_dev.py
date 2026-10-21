"""Developer-owned type safety for deterministic DAG admission."""
import unittest
from subagentbridge.planner.budget import validate_task_dag

class DagIdentityBounds(unittest.TestCase):
    def test_nontext_mapping_ids_denied_as_value_error(self):
        for ids in ({'one':(), 5:()}, {'one':(), None:()}):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                validate_task_dag(ids,{k:('ac',) for k in ids})

    def test_oversized_task_or_dependency_id_denied(self):
        key='x'*257
        for graph,criteria in (({key:()},{key:('ac',)}),
                               ({'a':(key,)},{'a':('ac',)})):
            with self.assertRaises(ValueError):validate_task_dag(graph,criteria)

    def test_nonmapping_inputs_denied(self):
        with self.assertRaises(ValueError): validate_task_dag([('a',())],{'a':('ac',)})

if __name__=='__main__':unittest.main()
