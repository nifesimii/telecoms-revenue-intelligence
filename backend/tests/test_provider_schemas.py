"""Strict provider schemas do not replace application-side validation."""
import asyncio
from copy import deepcopy
import json

import anthropic
import httpx
import pytest
from pydantic import ValidationError

from backend.agent import inference
from backend.agent.measure_scope import MeasureScope, SCOPE_TOOL


def test_strict_tool_transforms_nested_constraints_without_mutating_local_schema():
    original = deepcopy(SCOPE_TOOL)
    tool = inference.strict_tool(SCOPE_TOOL)
    assert tool['strict'] is True
    assert tool['name'] == SCOPE_TOOL['name']
    assert tool['input_schema'] == anthropic.transform_schema(SCOPE_TOOL['input_schema'])
    assert tool['input_schema']['additionalProperties'] is False
    dealer = tool['input_schema']['properties']['dealer_id']['anyOf'][0]
    assert 'maxLength' not in dealer
    assert 'maxLength: 100' in dealer['description']
    tool['input_schema']['required'].append('not_a_local_requirement')
    tool['input_schema']['properties']['kind']['enum'].append('not_a_local_kind')
    assert SCOPE_TOOL == original


@pytest.mark.parametrize('scope', [
    {'kind': 'identity', 'dealer_name': 'x' * 301},
    {'kind': 'measure', 'measures': ['activation_count'], 'periods': ['202613']},
    {'kind': 'measure', 'measures': ['activation_count'], 'periods': ['202601'], 'limit': 101},
    {'kind': 'measure', 'measures': ['activation_count'], 'periods': ['202601'], 'record_offset': 1},
])
def test_provider_transformation_keeps_original_local_constraints_and_cross_field_checks(scope):
    inference.strict_tool(SCOPE_TOOL)
    with pytest.raises(ValidationError):
        MeasureScope.model_validate(scope)


def test_strict_tool_is_serialized_on_provider_request_with_forced_selection():
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            'id': 'msg_test', 'type': 'message', 'role': 'assistant',
            'model': 'claude-sonnet-4-5', 'content': [], 'stop_reason': 'end_turn',
            'stop_sequence': None, 'usage': {'input_tokens': 1, 'output_tokens': 1},
        })

    async def exercise():
        async with anthropic.AsyncAnthropic(api_key='test', max_retries=0,
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
            await inference.InferenceRun('test').create(
                client, model='claude-sonnet-4-5', max_tokens=10,
                messages=[{'role': 'user', 'content': 'Resolve scope'}],
                tools=[inference.strict_tool(SCOPE_TOOL)],
                tool_choice={'type': 'tool', 'name': SCOPE_TOOL['name']})

    asyncio.run(exercise())
    assert len(requests) == 1
    assert requests[0]['tools'][0]['strict'] is True
    assert requests[0]['tool_choice'] == {'type': 'tool', 'name': 'resolve_measure_request'}
