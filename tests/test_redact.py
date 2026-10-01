"""Secrets are always removed from captured files; every removal is reported."""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from codebase_agent_setup import redact


class JsonRedactionTests(unittest.TestCase):
    def redact(self, value):
        text, removals = redact.text(json.dumps(value, indent=2), "config.json")
        return json.loads(text), removals

    def test_secret_named_keys_lose_their_values(self):
        cleaned, removals = self.redact({"url": "https://example.invalid", "token": "abcd1234efgh"})
        self.assertEqual(cleaned["url"], "https://example.invalid")
        self.assertEqual(cleaned["token"], redact.PLACEHOLDER)
        self.assertEqual([r.location for r in removals], ["token"])

    def test_nested_and_listed_secrets_are_found_and_located(self):
        cleaned, removals = self.redact(
            {
                "servers": [
                    {"name": "a", "api_key": "sk-secret"},
                    {"name": "b", "headers": {"Authorization": "Bearer x"}},
                ]
            }
        )
        self.assertEqual(cleaned["servers"][0]["api_key"], redact.PLACEHOLDER)
        self.assertEqual(cleaned["servers"][1]["headers"]["Authorization"], redact.PLACEHOLDER)
        self.assertEqual(cleaned["servers"][0]["name"], "a")
        self.assertEqual(
            sorted(r.location for r in removals), ["servers[0].api_key", "servers[1].headers.Authorization"]
        )

    def test_environment_variable_references_are_kept(self):
        """Pointing at a variable is how a setup is meant to carry a secret; it is not a secret."""
        cleaned, removals = self.redact({"token_env": "SOURCEGRAPH_TOKEN", "api_key": "${OPENAI_API_KEY}"})
        self.assertEqual(cleaned["token_env"], "SOURCEGRAPH_TOKEN")
        self.assertEqual(cleaned["api_key"], "${OPENAI_API_KEY}")
        self.assertEqual(removals, [])

    def test_a_secret_shaped_value_under_an_innocent_key_is_still_removed(self):
        cleaned, removals = self.redact({"note": "use sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"})
        self.assertIn(redact.PLACEHOLDER, cleaned["note"])
        self.assertNotIn("sk-ant-api03", cleaned["note"])
        self.assertEqual([r.location for r in removals], ["note"])

    def test_empty_and_null_secret_values_are_not_reported(self):
        cleaned, removals = self.redact({"token": "", "secret": None})
        self.assertEqual(cleaned, {"token": "", "secret": None})
        self.assertEqual(removals, [])


class TextRedactionTests(unittest.TestCase):
    def test_assignments_in_plain_text_are_redacted_per_line(self):
        source = "HOME=/home/someone\nOPENAI_API_KEY=sk-proj-AAAAAAAAAAAAAAAAAAAA\n"
        cleaned, removals = redact.text(source, ".env")
        self.assertIn("HOME=/home/someone", cleaned)
        self.assertIn("OPENAI_API_KEY=" + redact.PLACEHOLDER, cleaned)
        self.assertEqual([r.location for r in removals], ["line 2"])

    def test_known_token_shapes_are_redacted_wherever_they_appear(self):
        for secret in (
            "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "AKIAAAAAAAAAAAAAAAAA",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
        ):
            with self.subTest(secret):
                cleaned, removals = redact.text(f"prefix {secret} suffix", "notes.md")
                self.assertNotIn(secret, cleaned)
                self.assertTrue(removals)

    def test_a_file_with_no_secrets_is_returned_unchanged(self):
        source = "# Handover\n\nAs of 2026-09-30. Nothing secret here.\n"
        cleaned, removals = redact.text(source, "HANDOVER.md")
        self.assertEqual(cleaned, source)
        self.assertEqual(removals, [])

    def test_malformed_json_falls_back_to_line_scanning_rather_than_failing(self):
        cleaned, removals = redact.text('{"token": "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",', "broken.json")
        self.assertNotIn("ghp_A", cleaned)
        self.assertTrue(removals)


class BinaryTests(unittest.TestCase):
    def test_a_file_that_is_not_utf8_text_is_refused_rather_than_guessed(self):
        with self.assertRaises(redact.RedactionError):
            redact.text_bytes(b"\x00\x01\x02binary", "cache.bin")


if __name__ == "__main__":
    unittest.main()
