import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALGO_PATH = ROOT / "quantconnect-poc" / "algorithms" / "spy_qqq_credit_spread_poc.py"


def load_function_from_source(function_name):
    source = ALGO_PATH.read_text()
    tree = ast.parse(source)
    func_node = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    module = ast.Module(body=[func_node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, str(ALGO_PATH), "exec"), namespace)
    return namespace[function_name]


class QuantConnectPocAlgorithmTests(unittest.TestCase):
    def test_algorithm_contains_live_mode_guard(self):
        source = ALGO_PATH.read_text()
        self.assertIn("self.LiveMode", source)
        self.assertIn("must not run live", source)

    def test_safe_spread_quantity_refuses_trade_above_risk_budget(self):
        calculate = load_function_from_source("calculate_safe_spread_quantity")
        self.assertEqual(calculate(100_000, 0.005, 10), 0)

    def test_safe_spread_quantity_allows_trade_within_risk_budget(self):
        calculate = load_function_from_source("calculate_safe_spread_quantity")
        self.assertEqual(calculate(100_000, 0.01, 5), 2)


if __name__ == "__main__":
    unittest.main()
