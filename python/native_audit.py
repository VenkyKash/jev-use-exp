"""Credential-safe HTTP evidence for the native runner's real SDK client."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
import time
import uuid

import httpx2
from typesafe_sdk import RetryPolicy, TypeSafeClient


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class HttpAudit:
    def __init__(self, emit):
        self.emit = emit

    def request(self, request):
        audit_id = uuid.uuid4().hex
        request.extensions["jev_audit"] = (audit_id, time.monotonic())
        self.emit(dict(event="provider_http_request", audit_id=audit_id, utc=utc_now(),
                       method=request.method,
                       endpoint=str(request.url.copy_with(userinfo=b"", query=None, fragment=None))))

    def response(self, response):
        audit_id, started = response.request.extensions["jev_audit"]
        self.emit(dict(event="provider_http_response", audit_id=audit_id, utc=utc_now(),
                       status=response.status_code,
                       request_id=response.headers.get("x-typesafe-request-id"),
                       elapsed_ms=round((time.monotonic()-started)*1000, 2)))


@contextmanager
def audited_client(emit):
    # No user-supplied transport or mock fallback in this production constructor.
    audit = HttpAudit(emit)
    key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise ValueError("TYPESAFE_API_KEY is required")
    emit(dict(event="provider_client", utc=utc_now(), transport="httpx2.HTTPTransport",
              credential_fingerprint=hashlib.sha256(key.encode()).hexdigest()[:16],
              retries=0))
    with httpx2.Client(timeout=10, event_hooks={"request": [audit.request], "response": [audit.response]}) as http:
        with TypeSafeClient(http_client=http, retry=RetryPolicy(max_retries=0)) as client:
            yield client
