import unittest

from app.services.discord_gateway import (
    GATEWAY_INTENTS,
    heartbeat_payload,
    hello_interval_ms,
    identify_payload,
    resume_payload,
)


class DiscordGatewayProtocolTests(unittest.TestCase):
    def test_identify_uses_guilds_intent_only(self) -> None:
        payload = identify_payload("secret-token")
        self.assertEqual(payload["op"], 2)
        self.assertEqual(payload["d"]["intents"], GATEWAY_INTENTS)
        self.assertEqual(payload["d"]["intents"], 1)
        self.assertEqual(payload["d"]["properties"]["browser"], "cyberhost")

    def test_resume_and_heartbeat_keep_seq(self) -> None:
        resume = resume_payload("secret-token", "sess", 42)
        self.assertEqual(resume["op"], 6)
        self.assertEqual(resume["d"]["session_id"], "sess")
        self.assertEqual(resume["d"]["seq"], 42)
        self.assertEqual(heartbeat_payload(7), {"op": 1, "d": 7})

    def test_hello_interval_rejects_invalid(self) -> None:
        self.assertEqual(hello_interval_ms({"op": 10, "d": {"heartbeat_interval": 41250}}), 41250)
        with self.assertRaises(ValueError):
            hello_interval_ms({"op": 10, "d": {}})
        with self.assertRaises(ValueError):
            hello_interval_ms({"op": 10, "d": {"heartbeat_interval": 500}})
