"""Deterministic disclosure at the chat presentation boundary, including history.

This carries provenance only. Business policy and explanations belong in the KB;
the conversation loop remains unaware of subscription policy or data storage.
"""
import json
from backend import config
from backend.models.subscription import POLICY_LABEL


def qualify_subscription_answer(response, *, message='', history=(), raw_data=None, tools_called=()):
    context = json.dumps([message, history, raw_data or {}, response], ensure_ascii=False)
    synthetic_context = (POLICY_LABEL in context or 'SYN-SUB-' in context
                         or (config.USE_SAMPLE_DATA and any(
                             name in {'get_subscription_summary', 'get_subscription_devices'} for name in tools_called)))
    if not synthetic_context:
        return response
    # Always lead with the disclosure, even if the model buried it at the end.
    notice = f'Synthetic demo data. **{POLICY_LABEL}**'
    return response if response.startswith(notice) else f'{notice}\n\n{response}'
