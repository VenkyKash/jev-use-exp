# Offline adapter comparison

Compared the original choose_with_typesafe path against JevChooser.choose plus
validate_decision, using a replay-only client. No real SDK client, network request,
or Driver was constructed. Each path received the same candidate IDs/descriptions,
goal, controlled observation, and answer values. Only the response question key
was mapped to the key each adapter requests. This isolates response acceptance;
it does not prove equivalent live prompts or model behavior.

## Results

All five retained diagnostic answers passed both paths: the audited acknowledge
probe and four Chrome launch probes. The original two failing Chrome responses
were not retained, so their rejection cause cannot be reconstructed.

Synthetic boundaries expose real differences:

| Answer | Original adapter | Native path |
|---|---|---|
| Confidence 0.49, valid distribution | Accepts | confidence_rejected |
| Missing one candidate probability | Accepts | probability_keys |
| Probabilities sum to 0.7 | Accepts | probability_sum |
| Confidence 1.1 | Accepts | provider_response_invalid |
| Probability outside 0..1 | Accepts | provider_response_invalid |
| Unknown selected ID | Rejects | Rejects |

The browser runner also checks candidate identity/capture freshness, but does not
apply a confidence threshold. Synthetic invalid numeric responses are injected
after SDK parsing; this does not establish that the live SDK would emit them.

The paths share system_one and Choice, but not identical request construction:
question names and instructions differ, the browser puts history at the top level,
and the native request builder nests recent history in its observation and supplies
different UI context. Native client timeout/retry configuration also differs.
This replay does not exercise HTTP transport, SDK decoding, model sensitivity to
these prompt differences, or dashboard attribution.

Conclusion: stricter native validation can reject answers accepted by the original,
but no retained real answer reproduced that divergence. There is no evidence here
that architectural separation caused the missing usage or historical failures.
Do not loosen safeguards or refactor production code on that assumption.

Executable coverage: python/tests/test_adapter_comparison.py. The recorded cases
are copied from local diagnostic traces without credentials or UI content.
