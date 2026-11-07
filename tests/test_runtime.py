import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import config
import main
import reset_and_init_db
from execution_tools import _normalize_numbers_in_result
from langchain_core.messages import AIMessage, ToolMessage


def execution_messages(sql, rows):
    return [
        AIMessage(content='', tool_calls=[{'name': 'execute_sql_tool', 'args': {'query': sql}, 'id': 'exec_1'}]),
        ToolMessage(content=json.dumps(rows), tool_call_id='exec_1'),
    ]


class RuntimeTests(unittest.TestCase):
    def coordinator(self, blacklist=None, model=None, answers=None):
        retriever = Mock()
        retriever.get_relevant_schema_as_text.return_value = 'Synthetic schema'
        builder = Mock()
        builder.build_agent_input.return_value = 'Synthetic task'
        return main.LangGraphCoordinator(model, retriever, builder, answers or {}, blacklist or {})

    def test_decimal_and_float_result_format_matches_demo_contract(self):
        rows = _normalize_numbers_in_result([{'total': Decimal('75.00'), 'ratio': Decimal('0.333333'), 'count': 4.0}])
        self.assertEqual(rows, [{'total': 75, 'ratio': 0.33, 'count': 4}])
        self.assertIsInstance(rows[0]['total'], int)

    def test_blacklist_matches_reordered_rows_without_column_names(self):
        wrong = [{'old': 1}, {'old': 2}]
        coordinator = self.coordinator({'sql_1': {main.canonicalize_result_v4(wrong)}})
        status, _ = coordinator._check_result_blacklist('sql_1', 'SELECT bad', execution_messages('SELECT bad;', [{'new': 2}, {'new': 1}]))
        self.assertEqual(status, 'FAIL')

    def test_known_empty_result_is_blocked(self):
        coordinator = self.coordinator({'sql_1': {main.canonicalize_result_v4([])}})
        status, _ = coordinator._check_result_blacklist('sql_1', 'SELECT empty', execution_messages('SELECT empty', []))
        self.assertEqual(status, 'FAIL')

    def test_blacklist_does_not_reuse_a_different_query_result(self):
        wrong = [{'value': 1}]
        coordinator = self.coordinator({'sql_1': {main.canonicalize_result_v4(wrong)}})
        status, _ = coordinator._check_result_blacklist('sql_1', 'SELECT other', execution_messages('SELECT original', wrong))
        self.assertEqual(status, 'PASS')

    def test_cache_only_executes_sql_without_a_model(self):
        coordinator = self.coordinator(answers={'sql_1': {'query': 'SELECT 75', 'result': [{'obsolete': 1}]}})
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'OUTPUT_DIR', directory), patch.object(main.SqlExecutorTool, 'run', return_value='[{"actual": 75}]'):
            result = coordinator.run_task({'sql_id': 'sql_1'}, cache_only=True)
        self.assertEqual(result['result'], [{'actual': 75}])

    def test_final_sql_is_reexecuted_instead_of_copying_history(self):
        coordinator = self.coordinator(model=Mock())
        state = {'messages': execution_messages('SELECT old', [{'value': -1}]) + [
            AIMessage(content='', tool_calls=[{'name': 'submit_final_sql', 'args': {'final_sql_query': 'SELECT 75'}, 'id': 'submit_1'}])
        ]}
        graph = Mock()
        graph.invoke.return_value = state
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'OUTPUT_DIR', directory), patch.object(coordinator, '_build_graph', return_value=graph), patch.object(main.SqlExecutorTool, 'run', return_value='[{"value": 75}]') as execute:
            result = coordinator.run_task({'sql_id': 'sql_1', 'question': 'Synthetic', 'table_list': []}, ignore_cache=True)
        execute.assert_called_once_with('SELECT 75')
        self.assertEqual(result['result'], [{'value': 75}])

    def test_model_failure_preserves_original_error_in_log(self):
        coordinator = self.coordinator(model=Mock())
        graph = Mock()
        graph.invoke.side_effect = RuntimeError('synthetic model outage')
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'OUTPUT_DIR', directory), patch.object(coordinator, '_build_graph', return_value=graph):
            result = coordinator.run_task({'sql_id': 'sql_1', 'question': 'Synthetic', 'table_list': []}, ignore_cache=True)
            logs = list(Path(directory).rglob('_FINAL_AGENT_RESULT.json'))
            self.assertIsNone(result)
            self.assertEqual(len(logs), 1)
            self.assertIn('synthetic model outage', json.loads(logs[0].read_text(encoding='utf-8'))['sql'])

    def test_init_refuses_existing_tables_before_any_ddl(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (2,)
        with patch.object(reset_and_init_db, 'get_raw_connection', return_value=connection):
            with self.assertRaises(SystemExit) as stopped:
                reset_and_init_db.reset_database()
        self.assertEqual(stopped.exception.code, 1)
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertFalse(any(sql.startswith(('DROP ', 'CREATE ')) for sql in statements))


if __name__ == '__main__':
    unittest.main()
