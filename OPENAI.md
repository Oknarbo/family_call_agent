# Optional OpenAI text understanding

This integration uses the Responses API with structured output. Deepgram remains STT
and Azure remains TTS. The model rewrites Croatian requests into forms supported by the
existing parser; it does not execute tools or write to the database. Existing confirmation,
authorization, timing and inventory rules remain in force.

Supported integration points: inbound requests, clarification/correction phrasing, ambiguous
approval wording, and ordinary outbound reminder acknowledgements/snooze requests.
Exact known confirmations do not need a model call. Medication and household-safety
outcomes remain deterministic. Unsupported domain intents do not become implemented
merely because their wording is understood. The model can still misinterpret meaning;
review the spoken proposal before approving it.

## Activation

Deploy the updated source, then edit the private server `.env`:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini-2025-04-14
OPENAI_API_KEY=your-private-project-key
OPENAI_TIMEOUT_SECONDS=12
```

Use an OpenAI API project with billing enabled. Never paste the key into GitHub or chat.
Recreate API and worker after changing environment variables:

```bash
docker compose -f compose.hetzner.yml up -d --build
docker compose -f compose.hetzner.yml exec api python -m scripts.test_openai
```

The last command only checks local configuration. To explicitly make one billable text
probe using a fixed non-personal sentence, without a phone call or saved reminder:

```bash
docker compose -f compose.hetzner.yml exec api python -m scripts.test_openai --request
```

To revert, use `LLM_PROVIDER=development` and `LLM_MODEL=deterministic-hr` and recreate
the services. Existing reminders are unaffected by the provider choice.

## Cost and privacy

GPT-4.1 mini lists $0.40 per million input tokens and $1.60 per million output tokens.
For example, 1,000 input and 200 output tokens cost about $0.00072, excluding telephony,
speech and taxes. Actual turn size varies. Requests have an input-length limit, 700 output
tokens, a timeout and no automatic retries. There is no application-wide hard dollar cap.

Only the current utterance and previous question are sent; phone-like strings are redacted.
They can still contain personal reminder content. Requests use `store=false`; this does
not imply zero provider retention. Unknown callers are rejected before model access.
Logs do not contain response bodies or API keys. Failed, refused or incomplete responses
do not execute a write. Pending actions survive a transient model error within the same call.

The integration has local mocked contract and SQL tests. Real account/model access,
Croatian interpretation accuracy and latency still need a text-only probe before paid calls.

Sources: [model and pricing](https://developers.openai.com/api/docs/models/gpt-4.1-mini),
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
