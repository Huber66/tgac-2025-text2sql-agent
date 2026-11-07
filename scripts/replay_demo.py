"""Replay a scripted tool sequence through the real graph and demo database.

SQL choices are predefined; the graph and database execute each step.
"""
import json
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from execution_tools import test_connection
from langchain_core.messages import AIMessage
from main import LangGraphCoordinator, canonicalize_result_v4, load_error_result_blacklist, thread_safe_save
from prompt_engine import PromptBuilder, SchemaRetriever


class ScriptedToolCaller:
    """Return fixed tool calls without constructing a model API client."""

    def __init__(self, correct_sql):
        wrong_sql = (
            "SELECT game_id, SUM(play_minutes) AS total_minutes FROM demo_sessions "
            "WHERE event_date = '20990101' GROUP BY game_id"
        )
        self.actions = deque([
            ('execute_sql_tool', {'query': 'SELECT event_date, player_id, game_id, play_minutes FROM demo_sessions ORDER BY event_date, player_id LIMIT 5'}),
            ('execute_sql_tool', {'query': wrong_sql}),
            ('submit_final_sql', {'final_sql_query': wrong_sql}),
            ('revise_plan', {'new_plan_description': 'The empty result used an incorrect date. Use 20260101 and join the returning-player snapshot on the same date.'}),
            ('execute_sql_tool', {'query': correct_sql}),
            ('submit_final_sql', {'final_sql_query': correct_sql}),
        ])
        self.call_count = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        if not self.actions:
            raise RuntimeError('Replay exhausted its predefined tool calls before submission succeeded.')
        name, arguments = self.actions.popleft()
        self.call_count += 1
        return AIMessage(content='', tool_calls=[{
            'name': name, 'args': arguments, 'id': f'replay_{self.call_count}',
        }])


def summarize_history(history):
    events = []
    by_id = {}
    for message in history:
        for call in message.get('tool_calls', []):
            event = {'step': len(events) + 1, 'tool': call['name'], 'arguments': call['args']}
            events.append(event)
            by_id[call['id']] = event
        if message.get('type') == 'tool':
            event = by_id.get(message.get('tool_call_id'))
            if event is None:
                continue
            observation = message.get('content', '')
            try:
                observation = json.loads(observation)
            except (json.JSONDecodeError, TypeError):
                pass
            event['observation'] = observation
    return events


def main():
    if config.PROFILE != 'demo':
        print('Replay is restricted to TGAC_PROFILE=demo and the synthetic fixtures.')
        return 1
    if not test_connection():
        return 1

    tasks = json.loads(Path(config.DATASET_PATH).read_text(encoding='utf-8'))
    answers = json.loads(Path(config.ANSWER_KEY_FILE).read_text(encoding='utf-8'))
    task = next(item for item in tasks if item['sql_id'] == 'sql_1')
    expected = next(item for item in answers if item['sql_id'] == 'sql_1')
    output_root = Path(config.OUTPUT_DIR)
    run_dir = output_root / 'scripted_replay' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    config.OUTPUT_DIR = str(run_dir)
    caller = ScriptedToolCaller(expected['query'])
    coordinator = LangGraphCoordinator(
        caller, SchemaRetriever(), PromptBuilder(), {},
        load_error_result_blacklist(config.ERROR_SAMPLES_FILE),
    )
    result = coordinator.run_task(task, ignore_cache=True)
    if result is None:
        print('Replay failed. Check the local execution logs.')
        return 1

    logs = list(run_dir.rglob('_FINAL_AGENT_RESULT.json'))
    if len(logs) != 1:
        print('Replay did not produce one final graph log.')
        return 1
    events = summarize_history(json.loads(logs[0].read_text(encoding='utf-8'))['history'])
    submissions = [event for event in events if event['tool'] == 'submit_final_sql']
    blocked = sum(str(event.get('observation', '')).startswith('Error:') for event in submissions)
    accepted = sum(str(event.get('observation', '')).startswith('Success:') for event in submissions)
    executions = len(list(run_dir.rglob('step_*_generated.sql')))
    matched = canonicalize_result_v4(result['result']) == canonicalize_result_v4(expected['result'])
    passed = blocked == 1 and accepted == 1 and executions == 4 and matched and not caller.actions
    if not passed:
        print(f'Replay check failed: blocked={blocked}, accepted={accepted}, executions={executions}, matched={matched}')
        return 1

    output_root.mkdir(parents=True, exist_ok=True)
    report = {
        'mode': 'scripted_tool_replay',
        'uses_model_api': False,
        'data_source': 'independently created synthetic demo',
        'events': events,
        'blocked_submissions': blocked,
        'accepted_submissions': accepted,
        'sql_executions_including_final_reexecution': executions,
        'result_matches_fixture': matched,
        'final_result': result,
    }
    trace_path = output_root / 'replay_trace.json'
    trace_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if not thread_safe_save(result, str(output_root / 'replay_result.json')):
        return 1
    print('[PASS] Known empty result rejected; revised SQL accepted.')
    print('[PASS] Final SQL re-executed; result matches the synthetic fixture.')
    print(f'No model API calls. Trace: {trace_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
