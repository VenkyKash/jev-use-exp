import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx2
from typesafe_sdk import Choice, TypeSafeClient, RetryPolicy
from native_audit import HttpAudit


class SdkWireAuditTest(unittest.TestCase):
    def test_sdk_wire_events_and_decoded_usage_share_request_id(self):
        # Explicit test-only transport: no request leaves this unit test.
        events = []
        audit = HttpAudit(events.append)
        def handle(request):
            self.assertEqual(request.url.path, "/v1/systemone")
            self.assertEqual(request.method, "POST")
            self.assertEqual(json.loads(request.content)["state"], {"test": True})
            return httpx2.Response(200, headers={"x-typesafe-request-id": "unit-test-id"}, json={
                "model": "unit-test", "usage": {"input_tokens": 3, "output_tokens": 1},
                "answers": {"candidate": {"type": "choice", "choice": "yes", "confidence": 1,
                                             "probabilities": {"yes": 1, "no": 0}}}})
        with httpx2.Client(transport=httpx2.MockTransport(handle),
                           event_hooks={"request": [audit.request], "response": [audit.response]}) as http:
            with TypeSafeClient(api_key="unit-test-secret", http_client=http, retry=RetryPolicy(max_retries=0)) as client:
                response = client.system_one(state={"test": True}, questions={"candidate": Choice(
                    instructions="Choose", criteria={"yes": "Yes", "no": "No"})})
        self.assertEqual(response.request_id, events[-1]["request_id"])
        self.assertEqual(events[-1]["status"], 200)
        self.assertEqual(response.usage.input_tokens, 3)
        self.assertNotIn("unit-test-secret", json.dumps(events))
