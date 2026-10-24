# Argus AI RAG urban advisor

The RAG advisor is an optional, grounded ranking layer over the existing Argus
simulator. It does not calculate metrics or predict an after-state. It receives a
bounded completed-run report, retrieves local intervention records, asks the
advisor LLM to rank only actions the simulator can execute, validates the
response, and returns structured recommendations.

**Advisor LLM:** an [Agent 37](https://www.agent37.com) hosted Hermes agent
(`api/agent37.py`, `POST {AGENT37_AGENT_URL}/v1/responses` with `X-Agent37-Key`).
It replaced Groq-hosted `openai/gpt-oss-120b`, which is now used only as a
fallback when Agent 37 is not configured. Agent 37 has no JSON-schema response
mode, so the schema is sent in the prompt and validation stays strict.

The deterministic threshold advisor remains the reliable execution authority and
fallback. A missing API key, missing optional dependency, stale index, malformed
model response, invented action, or unknown target cannot stop the demo.

## Setup

```powershell
python -m pip install -r api\requirements-rag.txt
python -m api.rag.build_index
# .env (gitignored):  AGENT37_API_KEY=sk_live_...   AGENT37_AGENT_URL=https://<agent-id>.agent37.app
python -m api --host 127.0.0.1 --port 8000
```

Copy `.env.example` to `.env` and replace the placeholders, or set the values in
PowerShell. Free-tier Agent 37 agents sleep when idle and wake on a request, so
the first call can take longer; the API allows 150 s and the dashboard proxy 180 s. The API automatically loads the root `.env` without overriding a
value already present in the shell. The index is written to the ignored
`data/.rag_index/` directory. Rebuild it whenever
`data/urban_interventions.json` changes. Without the built semantic index, the
advisor uses a dependency-free lexical retriever and reports that backend
truthfully.

## Endpoint

After a run completes:

```http
POST /api/runs/{run_id}/advise
```

The backend obtains the report from its own run manager. The browser does not
send simulator output back to the API.

The response identifies `advisor_mode`, `fallback_used`, retrieval backend,
knowledge hash, model, retrieved knowledge, and ranked recommendations. Records
whose `source_status` is `NEEDS_SOURCE` must be shown as unverified contextual
leads, never as evidence-backed planning guidance.

## Apply and test boundary

Only these current simulator IDs are executable:

- `increase_shade`
- `improve_drainage`
- `alternative_pedestrian_routes`
- `no_major_intervention`

The validator requires every model-selected action to match the action on a
record that was actually retrieved. It also checks any supplied route, building,
or zone target against the bounded report. The existing simulator owns action
strengths and all before/after computation.

The frontend lets the operator select one or more returned actions. “Apply
selected and re-simulate” starts a new run with the optional
`selected_recommendation_ids` request field. The API accepts only the simulator's
allow-list, the pipeline forwards those IDs to `Simulation/main.py`, and the
simulator passes them through its existing `recommended_interventions(...)`
function. The after-state is therefore a real simulator run using only the
selected actions.

## Advisor chat

```http
POST /api/runs/{run_id}/chat   {"message": "...", "session_id": "<optional>"}
-> {"source": "agent37" | "deterministic", "reply": "...", "proposals": [{"action", "reason"}], "session_id"}
```

`api/chat.py`. The planner talks with the same Agent 37 agent about a completed
run: asks why a place is flagged, challenges a recommendation or suggests an idea.

- **Grounding:** the first turn of a session sends the advisor rules plus the
  run's facts (`build_explanation_payload`); follow-ups send only the message,
  because the agent keeps the conversation via `session_id`.
- **Across re-runs:** when the planner applies a proposal and a new run
  completes, that run's facts are injected into the same conversation, so the
  advisor can compare runs (it quoted both runs' metrics correctly in testing).
- **Proposals:** the agent may end a reply with one `PROPOSE: {...}` line. Only
  the four executable IDs survive; the dashboard shows each as a card whose
  "Apply & re-run" uses the existing `selected_recommendation_ids` path.
  Ideas the simulator cannot test are answered as such, not proposed.
- **Fallback:** if Agent 37 is unset or fails, the reply is the simulator's own
  rule-based advice, labelled with the reason.
- The LLM never produces metrics; every number it states comes from the run
  facts it was given. Sessions are in memory, so an API restart starts a fresh,
  re-grounded conversation.

## Tests

```powershell
python -m unittest api.test_chat api.test_rag -v
python -m unittest discover -s api -p "test_*.py"
python -m unittest integration.test_export_interfaces integration.test_run_pipeline
```
