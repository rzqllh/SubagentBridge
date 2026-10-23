"""Offline adapter contract. No external network or installed 9Router needed."""
from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.error import URLError
from subagentbridge.models.nine_router import (
    LocalRouterConfig, NineRouterClient, CallBudget, RouterProtocolError,
    UnknownCapability, RequestBudgetExceeded, LocalHttpTransport, RouterUnavailable,
)


class FakeTransport:
    def __init__(self, models=None, reply=None):
        self.models = models if models is not None else {'data': [{'id': 'local/model-a',
            'supported_parameters': ['stream', 'tools']}, {'id': 'local/unknown'}]}
        self.reply = reply if reply is not None else {'choices': [{'message': {'role': 'assistant',
            'content': 'ok'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 8, 'completion_tokens': 2}}
        self.calls = []

    def request(self, *, config, method, path, payload):
        self.calls.append((method, path, payload))
        return self.models if method == 'GET' else self.reply


class Offline9RouterTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeTransport()
        self.client = NineRouterClient(LocalRouterConfig('http://127.0.0.1:2999', 'secret-do-not-log'),
                                       transport=self.fake)

    def test_only_literal_loopback_and_no_credentials_in_repr(self):
        for origin in ('https://127.0.0.1:2999', 'http://example.com:2999',
                       'http://localhost:2999', 'http://127.0.0.1',
                       'http://127.0.0.1:2999/path', 'http://evil@127.0.0.1:2999'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                LocalRouterConfig(origin, 'secret-do-not-log')
        self.assertNotIn('secret-do-not-log', repr(self.client.config))
        self.assertEqual(LocalRouterConfig('http://[::1]:3000', 'k').origin, 'http://[::1]:3000')

    def test_capability_unknown_is_not_assumed(self):
        models = self.client.discover()
        self.assertEqual(len(models), 2)
        self.assertTrue(models[0].tool_calls)
        self.assertIsNone(models[1].tool_calls)
        with self.assertRaises(UnknownCapability):
            self.client.models.select(['local/unknown'], coding=True)

    def test_no_model_invocation_without_d02_decision(self):
        self.client.discover()
        with self.assertRaises(PermissionError):
            self.client.chat(model_id='local/model-a', messages=({'role':'user','content':'hi'},),
                             max_tokens=5, budget=CallBudget(requests=1,tokens=5))
        self.assertEqual(len(self.fake.calls), 1)  # Only discovery, never a model request

    def test_actual_usage_and_precharged_request_budget(self):
        self.client.discover()
        budget = CallBudget(requests=1, tokens=15)
        reply = self.client.chat(model_id='local/model-a', messages=({'role':'user','content':'hi'},),
                                 max_tokens=12, budget=budget, provider_terms_approved=True)
        self.assertEqual((reply.text, reply.usage_class, reply.prompt_tokens), ('ok','actual',8))
        self.assertEqual((budget.requests_left, budget.tokens_left), (0,3))
        with self.assertRaises(RequestBudgetExceeded):
            self.client.chat(model_id='local/model-a', messages=({'role':'user','content':'hi'},),
                             max_tokens=1, budget=budget, provider_terms_approved=True)
        self.assertEqual(len(self.fake.calls), 2)

    def test_invalid_messages_do_not_spend_budget(self):
        self.client.discover()
        budget = CallBudget(requests=1, tokens=5)
        with self.assertRaises(ValueError):
            self.client.chat(model_id='local/model-a', messages=({'role':'tool','content':'fake'},),
                             max_tokens=3, budget=budget, provider_terms_approved=True)
        self.assertEqual(budget.requests_left, 1)

    def test_tool_calls_never_execute_and_no_success_claim(self):
        self.fake.reply = {'choices': [{'message': {'tool_calls':[{'function':{'name':'shell'}}]},
                                       'finish_reason':'tool_calls'}]}
        self.client.discover()
        reply = self.client.chat(model_id='local/model-a', messages=({'role':'user','content':'go'},),
                                 max_tokens=5, budget=CallBudget(requests=1,tokens=5),
                                 provider_terms_approved=True)
        self.assertTrue(reply.tool_calls_pending)
        self.assertEqual(reply.finish_reason, 'TOOL_CALLS_BLOCKED')

    def test_malformed_discovery_and_response_fail_closed(self):
        self.fake.models = {'data': [{'id':'dup'}, {'id':'dup'}]}
        with self.assertRaises(RouterProtocolError): self.client.discover()
        self.fake.models = {'data': [{'id':'okay'}]}
        self.client.discover()
        self.fake.reply = {'choices': []}
        with self.assertRaises(RouterProtocolError):
            self.client.chat(model_id='okay', messages=({'role':'user','content':'x'},),
                             max_tokens=5, budget=CallBudget(requests=1,tokens=5),
                             provider_terms_approved=True)

    def test_unknown_or_failed_capability_cannot_call(self):
        self.client.discover()
        with self.assertRaises(UnknownCapability):
            self.client.chat(model_id='not-discovered', messages=({'role':'user','content':'x'},),
                             max_tokens=5, budget=CallBudget(requests=1,tokens=5),
                             provider_terms_approved=True)

    def test_concurrent_request_budget_stops_at_limit(self):
        budget = CallBudget(requests=5, tokens=5)
        def worker(_):
            try:
                budget.charge(1)
                return True
            except RequestBudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=24) as pool:
            results = list(pool.map(worker, range(100)))
        self.assertEqual(sum(results), 5)
        self.assertEqual((budget.tokens_left, budget.requests_left), (0, 0))

    def test_transport_hides_secret_even_when_backend_error_contains_it(self):
        class RejectingOpener:
            def open(self, *args, **kwargs):
                raise URLError('secret-do-not-log in remote error')
        with patch('subagentbridge.models.nine_router.build_opener', return_value=RejectingOpener()) as opener:
            with self.assertRaises(RouterUnavailable) as err:
                LocalHttpTransport().request(config=self.client.config,
                      method='GET', path='/v1/models', payload=None)
        self.assertNotIn('secret-do-not-log', str(err.exception))
        self.assertEqual(opener.call_args.args[0].proxies, {})

    def test_usage_unknown_when_missing(self):
        self.fake.reply = {'choices': [{'message': {'content':'answer'}, 'finish_reason':'stop'}]}
        self.client.discover()
        reply = self.client.chat(model_id='local/model-a', messages=({'role':'user','content':'x'},),
                                 max_tokens=5, budget=CallBudget(requests=1,tokens=5),
                                 provider_terms_approved=True)
        self.assertEqual(reply.usage_class, 'unknown')
        self.assertIsNone(reply.prompt_tokens)

if __name__ == '__main__': unittest.main()
