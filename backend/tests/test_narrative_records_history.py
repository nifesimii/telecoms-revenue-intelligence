"""Interpretation retains paging context; final record intros do not copy old tables."""
import asyncio
from copy import deepcopy
import json

from backend.agent.agent import run_agent
from backend.tests.test_agent import install_scope_provider
from backend.tests.test_investigation_response import request


def test_record_scope_uses_history_but_final_intro_has_no_old_table_or_offsets(monkeypatch):
    history = [
        {'role': 'user', 'content': 'Show the first twenty affected records for dealer 296065 in June 2026.'},
        {'role': 'assistant', 'content': 'Showing records 1–20 of 50.\n\n| IMEI |\n|---|\n| PRIOR-RECORD |\n\n### Verification evidence\n\nPrevious provenance.'},
    ]
    original = deepcopy(history)
    calls, _ = install_scope_provider(monkeypatch, request(presentation='records', record_offset=20, limit=20))
    result = asyncio.run(run_agent('Next page please', history, reporting_period='202606'))
    assert calls[0]['messages'][:-1] == original
    final_payload = json.loads(calls[1]['messages'][-1]['content'])
    assert final_payload['history'] == []
    assert 'record_offset' not in final_payload['scope'] and 'limit' not in final_payload['scope']
    assert 'PRIOR-RECORD' not in calls[1]['messages'][-1]['content']
    assert 'Previous provenance' not in calls[1]['messages'][-1]['content']
    assert history == original
    assert result['raw_data']['measure_evidence']['investigation']['pagination']['offset'] == 20
    assert 'Showing records 21–40 of 50.' in result['response']
