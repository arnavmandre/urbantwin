"""Advisor chat: grounding, session continuity, proposal validation, fallback. No network (fake agent)."""
import json
import unittest
from pathlib import Path
from unittest import mock

from api import agent37, chat
from api.rag import advisor

ROOT = Path(__file__).resolve().parents[1]
REPORT = json.loads((ROOT / "Simulation" / "urbantwin_demo_output.json").read_text(encoding="utf-8"))


class FakeAgent:
    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

    def __call__(self, text, session_id):
        self.sent.append((text, session_id))
        return self.replies.pop(0), "sess-1"


class ChatTests(unittest.TestCase):
    def setUp(self):
        chat._SESSIONS.clear()

    def test_first_turn_is_grounded_followups_are_not_new_run_is_injected(self):
        agent = FakeAgent(["Heat is the issue.", "Shade helps routes.", "After the re-run HEI rose."])
        first = chat.chat(REPORT, "run-a", "What is wrong?", send=agent)
        self.assertEqual(first["session_id"], "sess-1")
        text, sid = agent.sent[0]
        self.assertIsNone(sid)
        self.assertIn("RUN FACTS (run run-a)", text)
        self.assertIn("increase_shade", text)  # allowed actions are in the rules
        self.assertIn(f'"before_metrics":', text)

        chat.chat(REPORT, "run-a", "Why shade?", "sess-1", send=agent)
        self.assertEqual(agent.sent[1], ("PLANNER: Why shade?", "sess-1"))

        chat.chat(REPORT, "run-b", "Did it work?", "sess-1", send=agent)
        self.assertIn("NEW RUN FACTS (run run-b", agent.sent[2][0])
        self.assertEqual(agent.sent[2][1], "sess-1")

    def test_unknown_session_restarts_grounded(self):
        agent = FakeAgent(["ok"])
        chat.chat(REPORT, "run-a", "hi", "stale-session-from-before-restart", send=agent)
        self.assertIn("RUN FACTS", agent.sent[0][0])
        self.assertIsNone(agent.sent[0][1])

    def test_proposals_are_validated_and_stripped_from_text(self):
        reply = ('Shade the corridors.\nPROPOSE: {"proposals": [{"action": "increase_shade", "reason": "heat"},'
                 ' {"action": "build_metro", "reason": "x"}, {"action": "increase_shade", "reason": "dup"}]}')
        result = chat.chat(REPORT, "run-a", "fix it", send=FakeAgent([reply]))
        self.assertEqual(result["reply"], "Shade the corridors.")
        self.assertEqual(result["proposals"], [{"action": "increase_shade", "reason": "heat"}])

    def test_reply_that_is_only_a_proposal_still_shows_its_reasoning(self):
        reply = 'PROPOSE: {"proposals": [{"action": "increase_shade", "reason": "Heat is the main concern."}]}'
        result = chat.chat(REPORT, "run-a", "what first?", send=FakeAgent([reply]))
        self.assertEqual(result["reply"], "Heat is the main concern.")
        self.assertEqual(len(result["proposals"]), 1)

    def test_no_major_intervention_never_combines(self):
        _, proposals = chat.parse_reply('x\nPROPOSE: {"proposals": [{"action": "no_major_intervention"},'
                                        ' {"action": "improve_drainage"}]}')
        self.assertEqual([p["action"] for p in proposals], ["improve_drainage"])

    def test_malformed_propose_line_is_dropped_not_fatal(self):
        text, proposals = chat.parse_reply("Answer.\nPROPOSE: {not json}")
        self.assertEqual((text, proposals), ("Answer.", []))

    def test_agent_failure_falls_back_to_simulator_advice(self):
        def broken(text, session_id):
            raise RuntimeError("Agent 37 unreachable: timed out")
        result = chat.chat(REPORT, "run-a", "hi", send=broken)
        self.assertEqual(result["source"], "deterministic")
        self.assertIn("unreachable", result["unavailable_reason"])
        self.assertIn("rule-based", result["reply"])
        self.assertTrue(all(p["action"] in advisor.ALLOWED_RECOMMENDATION_IDS for p in result["proposals"]))

    def test_unconfigured_agent_falls_back(self):
        with mock.patch.dict("os.environ", {"AGENT37_API_KEY": "", "AGENT37_AGENT_URL": ""}):
            result = chat.chat(REPORT, "run-a", "hi")
        self.assertEqual(result["source"], "deterministic")


class Agent37Tests(unittest.TestCase):
    def test_extract_json_tolerates_fences_and_prose(self):
        self.assertEqual(agent37.extract_json('Here:\n```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(ValueError):
            agent37.extract_json("no json here")

    def test_agent37_replaces_groq_when_configured(self):
        env = {"AGENT37_API_KEY": "sk_live_test", "AGENT37_AGENT_URL": "https://x.agent37.app", "GROQ_API_KEY": "g"}
        with mock.patch.dict("os.environ", env):
            call, label = advisor._default_llm()
        self.assertIs(call, advisor._agent37_call)
        self.assertEqual(label, agent37.MODEL_LABEL)
        with mock.patch.dict("os.environ", {"AGENT37_API_KEY": "", "AGENT37_AGENT_URL": "", "GROQ_API_KEY": "g"}):
            self.assertIs(advisor._default_llm()[0], advisor._groq_call)

    def test_failed_turn_is_an_error_and_key_is_never_echoed(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"status": "failed", "error": "model overloaded"}'
        env = {"AGENT37_API_KEY": "sk_live_SECRET", "AGENT37_AGENT_URL": "https://x.agent37.app"}
        with mock.patch.dict("os.environ", env), mock.patch("urllib.request.urlopen", return_value=response):
            with self.assertRaises(RuntimeError) as ctx:
                agent37.send("hi")
        self.assertIn("failed", str(ctx.exception))
        self.assertNotIn("SECRET", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
