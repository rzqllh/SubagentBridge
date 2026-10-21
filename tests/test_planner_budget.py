import unittest
from subagentbridge.planner.budget import BudgetLedger,BudgetExceeded,validate_task_dag
class PlannerTests(unittest.TestCase):
 def test_dependency_order(self):self.assertEqual(validate_task_dag({'B':('A',),'A':()},{'A':('ac',),'B':('ac',)}),('A','B'))
 def test_cycle_denied(self):
  with self.assertRaises(ValueError):validate_task_dag({'A':('B',),'B':('A',)},{'A':('ac',),'B':('ac',)})
 def test_missing_ac_denied(self):
  with self.assertRaises(ValueError):validate_task_dag({'A':()},{'A':()})
 def test_unknown_dependency(self):
  with self.assertRaises(ValueError):validate_task_dag({'A':('X',)},{'A':('ac',)})
 def test_budget_concurrency(self):
  b=BudgetLedger(tokens=100,cost_microunits=200,max_workers=1);b.reserve(dispatch_id='x',token_allowance=50,cost_microunits=120)
  with self.assertRaises(BudgetExceeded):b.reserve(dispatch_id='y',token_allowance=1,cost_microunits=1)
  with self.assertRaises(BudgetExceeded):b.reserve(dispatch_id='x',token_allowance=1,cost_microunits=1)
  b.release('x',unused_tokens=20,unused_cost=80)
  self.assertEqual(b.snapshot()['tokens_available'],70)
 def test_budget_cannot_refund_unearned(self):
  b=BudgetLedger(tokens=10,cost_microunits=10,max_workers=1);b.reserve(dispatch_id='x',token_allowance=10,cost_microunits=10)
  with self.assertRaises(ValueError):b.release('x',unused_tokens=11)

if __name__=='__main__':unittest.main()
