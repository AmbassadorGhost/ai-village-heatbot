"""Operator allowlist for URGENT tiers (assigned messaging/payment work).

    python -X utf8 -m unittest tier1.test_allowlist
"""
import json
import unittest

from tier1 import action_notices as L


class Allowlist(unittest.TestCase):
    def msg(self, hosts=("api.x.com",), agent="g1"):
        return {"signal": "U5_mass_messaging", "time": "2026-10-04T15:00:00Z", "detector": "v",
                "agent": agent, "targets": list(hosts), "commands_in_window": 12}

    ALLOW = {"messaging": [{"agent": "Gemini Social", "agent_id": "g1", "services": ["x.com", "twitter.com"]}]}

    def test_undeclared_messaging_is_urgent(self):
        self.assertEqual(L.tier_for(self.msg(), [], [], {}, allowlist={}), "urgent")

    def test_declared_by_id_is_detection_even_without_names(self):
        # the deployed monitor calls tier_for(alert, rows) without a names map
        self.assertEqual(L.tier_for(self.msg(), [], [], None, allowlist=self.ALLOW), "detection")

    def test_declared_by_name(self):
        allow = {"messaging": [{"agent": "Gemini Social", "services": ["twitter.com"]}]}
        self.assertEqual(L.tier_for(self.msg(("api.twitter.com",)), [], [], {"g1": "Gemini Social"},
                                    allowlist=allow), "detection")

    def test_other_service_still_urgent(self):
        self.assertEqual(L.tier_for(self.msg(("api.sendgrid.com",)), [], [], None, allowlist=self.ALLOW), "urgent")

    def test_mixed_services_still_urgent(self):
        self.assertEqual(L.tier_for(self.msg(("api.x.com", "api.sendgrid.com")), [], [], None,
                                    allowlist=self.ALLOW), "urgent")

    def test_other_agent_still_urgent(self):
        self.assertEqual(L.tier_for(self.msg(agent="g2"), [], [], None, allowlist=self.ALLOW), "urgent")

    def test_smtp_needs_explicit_declaration(self):
        self.assertEqual(L.tier_for(self.msg(()), [], [], None, allowlist=self.ALLOW), "urgent")
        allow = {"messaging": [{"agent_id": "g1", "services": ["smtp"]}]}
        self.assertEqual(L.tier_for(self.msg(()), [], [], None, allowlist=allow), "detection")

    def test_declared_payments(self):
        alert = {"signal": "U6_payment", "time": "2026-10-04T15:00:00Z", "agent": "s1", "targets": ["api.stripe.com"]}
        allow = {"payments": [{"agent_id": "s1", "services": ["stripe.com"]}]}
        self.assertEqual(L.tier_for(alert, [], [], None, allowlist=allow), "detection")
        self.assertEqual(L.tier_for(alert, [], [], None, allowlist={}), "urgent")

    def test_allowlist_file_is_read(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "allow.json")
            open(p, "w").write(json.dumps(self.ALLOW))
            self.assertEqual(L.load_allowlist(p), self.ALLOW)
            self.assertEqual(L.load_allowlist(os.path.join(d, "missing.json")), {})


if __name__ == "__main__":
    unittest.main()
