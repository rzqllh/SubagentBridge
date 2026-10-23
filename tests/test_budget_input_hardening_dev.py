"""Developer-owned budget/DAG input hardening tests; no changes to QA tests."""
import unittest
from subagentbridge.planner.budget import BudgetLedger, validate_task_dag


class BudgetBoundaryTests(unittest.TestCase):
    def test_construct_rejects_bool_float_and_nonint_ceiling(self):
        for name in ('tokens', 'cost_microunits', 'max_workers'):
            for bad in (True, 1.5, '2', None):
                args = dict(tokens=100, cost_microunits=100, max_workers=2)
                args[name] = bad
                with self.subTest(name=name, bad=bad), self.assertRaises(ValueError):
                    BudgetLedger(**args)

    def test_reserve_and_refund_rejects_bool_float_without_mutating_budget(self):
        b = BudgetLedger(tokens=100, cost_microunits=100, max_workers=1)
        initial = b.snapshot()
        for kw in ({'token_allowance': True, 'cost_microunits': 0},
                   {'token_allowance': 0.5, 'cost_microunits': 0},
                   {'token_allowance': 1, 'cost_microunits': False}):
            with self.assertRaises(ValueError):
                b.reserve(dispatch_id='d', **kw)
            self.assertEqual(b.snapshot(), initial)
        b.reserve(dispatch_id='d', token_allowance=40, cost_microunits=80)
        after = b.snapshot()
        for kw in ({'unused_tokens': True}, {'unused_tokens': 1.5},
                   {'unused_cost': True}, {'unused_cost': 0.1},
                   {'unused_tokens': -1}):
            with self.assertRaises(ValueError):
                b.release('d', **kw)
            self.assertEqual(b.snapshot(), after)
        b.release('d', unused_tokens=20, unused_cost=30)
        self.assertEqual(b.snapshot(), dict(tokens_available=80, cost_available=50, active=0))

    def test_long_dag_avoids_python_recursion_limit(self):
        n = 2100
        deps = {f't{i}': (f't{i-1}',) if i else () for i in range(n)}
        ac = {k: ('specified acceptance',) for k in deps}
        order = validate_task_dag(deps, ac)
        self.assertEqual(len(order), n)
        self.assertEqual(order[0], 't0')
        self.assertEqual(order[-1], f't{n-1}')

    def test_dag_duplicate_dependencies_and_ac_are_rejected(self):
        for graph, ac in (
            ({'x': ('y', 'y'), 'y': ()}, {'x': ('one',), 'y': ('two',)}),
            ({'x': ()}, {'x': ('same', 'same')}),
            ({'x': (True,)}, {'x': ('criterion',)}),
        ):
            with self.assertRaises(ValueError):
                validate_task_dag(graph, ac)

    def test_shared_dependency_is_not_reported_as_cycle(self):
        graph = {'a': (), 'b': ('a',), 'c': ('a','b'), 'd': ('a','c')}
        ac = {k: ('ac',) for k in graph}
        order = validate_task_dag(graph, ac)
        self.assertEqual(len(order), 4)
        for task, deps in graph.items():
            for dep in deps:
                self.assertLess(order.index(dep), order.index(task))

if __name__ == '__main__':
    unittest.main()
