"""Known-answer tests for action_features (synthetic commands only).

    python -m unittest -v test_action_features
"""
import json
import unittest

from action_features import extract as X


class Methods(unittest.TestCase):
    def test_plain_get_is_not_a_write(self):
        f = X("curl -s https://example.org/page")
        self.assertEqual(f["request_methods"], ["GET"])
        self.assertEqual(f["write_hosts"], [])

    def test_curl_data_is_post(self):
        f = X("curl -s -d 'a=1' https://api.example.org/submit")
        self.assertEqual(f["request_methods"], ["POST"])
        self.assertEqual(f["write_hosts"], ["api.example.org"])

    def test_curl_explicit_method(self):
        self.assertEqual(X("curl -X PUT https://x.example.org/a")["request_methods"], ["PUT"])
        self.assertEqual(X("curl -XDELETE https://x.example.org/a")["write_hosts"], ["x.example.org"])

    def test_curl_json_and_form(self):
        self.assertEqual(X("curl --json '{}' https://a.example.org")["write_hosts"], ["a.example.org"])
        self.assertEqual(X("curl -F file=@x.png https://b.example.org/up")["write_hosts"], ["b.example.org"])

    def test_explicit_get_with_data_flag_keeps_method(self):
        # curl -G -d sends a GET query; -X GET wins over the default POST
        self.assertEqual(X("curl -X GET -d q=1 https://a.example.org")["request_methods"], ["GET"])

    def test_wget_post(self):
        self.assertEqual(X("wget --post-data='x=1' https://w.example.org/f")["write_hosts"], ["w.example.org"])

    def test_python_requests_post(self):
        cmd = "python3 -c \"import requests; requests.post('https://p.example.org/api', json={'a':1})\""
        f = X(cmd)
        self.assertIn("POST", f["request_methods"])
        self.assertEqual(f["write_hosts"], ["p.example.org"])

    def test_python_get_only(self):
        f = X("python3 -c \"import requests; print(requests.get('https://p.example.org').text)\"")
        self.assertEqual(f["request_methods"], ["GET"])
        self.assertEqual(f["write_hosts"], [])

    def test_urllib_request_with_data(self):
        f = X("python3 - <<'EOF'\nimport urllib.request\nr=urllib.request.Request('https://u.example.org/x', data=b'1')\nEOF")
        self.assertIn("POST", f["request_methods"])

    def test_chained_segments_attribute_writes_per_segment(self):
        f = X("curl https://read.example.org && curl -d x=1 https://write.example.org")
        self.assertEqual(f["write_hosts"], ["write.example.org"])
        self.assertEqual(f["request_methods"], ["GET", "POST"])


class Loops(unittest.TestCase):
    def test_shell_for_loop(self):
        self.assertTrue(X("for i in $(seq 1 50); do curl -d x=$i https://a.example.org; done")["loop_construct"])

    def test_python_range_loop(self):
        self.assertTrue(X("python3 -c \"for i in range(100): pass\"")["loop_construct"])

    def test_no_loop(self):
        self.assertFalse(X("curl https://a.example.org")["loop_construct"])


class Evasion(unittest.TestCase):
    def test_user_agent_flag(self):
        self.assertTrue(X("curl -A 'Mozilla/5.0' https://a.example.org")["browser_ua_spoof"])

    def test_user_agent_header(self):
        self.assertTrue(X("curl -H 'User-Agent: Mozilla/5.0 (X11)' https://a.example.org")["browser_ua_spoof"])

    def test_python_headers_ua(self):
        self.assertTrue(X("python3 -c \"h={'User-Agent': 'Mozilla/5.0'}\"")["browser_ua_spoof"])

    def test_honest_ua_is_not_spoof(self):
        self.assertFalse(X("curl -H 'User-Agent: village-bot/1.0' https://a.example.org")["browser_ua_spoof"])

    def test_proxy(self):
        self.assertTrue(X("curl --proxy http://p:8080 https://a.example.org")["proxy_use"])
        self.assertTrue(X("torsocks curl https://a.example.org")["proxy_use"])
        self.assertFalse(X("curl https://proxy-docs.example.org")["proxy_use"])
        self.assertTrue(X("curl -x socks5://127.0.0.1:9050 https://a.example.org")["proxy_use"])
        self.assertTrue(X("HTTPS_PROXY=http://p:8080 curl https://a.example.org")["proxy_use"])
        self.assertTrue(X("python3 -c \"requests.get(u, proxies={'https': p})\"")["proxy_use"])

    def test_shell_x_flags_are_not_proxies(self):
        # v0.2.1 regression (Greg's side): `set -x`, `bash -x`, `grep -x` matched the old pattern
        for cmd in ("set -x\ncurl https://a.example.org", "bash -x deploy.sh", "grep -x foo file.txt",
                    "xargs -x echo < list", "curl -s https://a.example.org | grep -x ok"):
            self.assertFalse(X(cmd)["proxy_use"], cmd)

    def test_mirror_of(self):
        f = X("curl https://r.jina.ai/https://blocked.example.com/article")
        self.assertEqual(f["mirror_of_hosts"], ["blocked.example.com"])


class Captcha(unittest.TestCase):
    def test_terms(self):
        self.assertTrue(X("curl -d 'g-recaptcha-response=abc' https://a.example.org")["captcha_terms"])
        self.assertTrue(X("curl https://cap.example.org/captcha/next")["captcha_terms"])
        self.assertFalse(X("curl https://a.example.org")["captcha_terms"])

    def test_solver_service(self):
        self.assertTrue(X("curl https://2captcha.com/in.php")["captcha_solver_service"])
        self.assertTrue(X("python3 -c \"from twocaptcha import TwoCaptcha\"")["captcha_solver_service"])


class AccountsMessagingPayments(unittest.TestCase):
    def test_signup_and_login_hosts(self):
        f = X("curl -d u=x https://svc.example.org/api/signup && curl https://svc2.example.org/login")
        self.assertEqual(f["signup_endpoint_hosts"], ["svc.example.org"])
        self.assertEqual(f["login_endpoint_hosts"], ["svc2.example.org"])

    def test_credentials_flag_only(self):
        f = X("curl -H 'Authorization: Bearer sk-SECRET123' https://a.example.org")
        self.assertTrue(f["credential_present"])

    def test_messaging(self):
        self.assertEqual(X("curl -d x https://api.sendgrid.com/v3/mail/send")["messaging_hosts"], ["api.sendgrid.com"])
        self.assertTrue(X("python3 -c \"import smtplib\"")["smtp_use"])
        self.assertEqual(X("curl -d s https://masto.example/api/v1/statuses")["messaging_hosts"], ["masto.example"])

    def test_payments(self):
        self.assertEqual(X("curl -u k: https://api.stripe.com/v1/charges")["payment_hosts"], ["api.stripe.com"])


class AuthoredMarkup(unittest.TestCase):
    """v0.2.2: writing a page is not making a request (Grok news page, 3 Oct)."""
    PAGE = ("cd site && python3 << 'PY'\n"
            "from pathlib import Path\n"
            "art = '''<!DOCTYPE html><html><body><h1>Hackathon FAQ</h1>\n"
            "<form method=\"post\" action=\"https://aivillageblog.substack.com/api/v1/free\"><input name=email></form>\n"
            "<p>Read more: <a href=\"https://aivillageblog.substack.com/join\">join the newsletter</a></p>'''\n"
            "Path('tip-7524.html').write_text(art)\n"
            "PY")

    def test_page_with_form_and_join_link_is_not_a_write_or_signup(self):
        f = X(self.PAGE)
        self.assertEqual(f["write_hosts"], [])
        self.assertEqual(f["signup_endpoint_hosts"], [])

    def test_real_signup_post_still_counts(self):
        f = X("curl -X POST -d email=a@b.c https://example.org/signup")
        self.assertEqual(f["write_hosts"], ["example.org"])
        self.assertEqual(f["signup_endpoint_hosts"], ["example.org"])

    def test_python_post_beside_a_page_still_counts(self):
        f = X(self.PAGE + "\npython3 -c \"import requests; requests.post('https://example.org/register', data={})\"")
        self.assertIn("example.org", f["write_hosts"])
        self.assertEqual(f["signup_endpoint_hosts"], ["example.org"])

    def test_blog_slug_with_join_is_not_a_signup_even_beside_a_real_post(self):
        # The real shape of Grok's turn (checked with show_turns --explain): an IndexNow ping
        # (a real urllib POST) in the same script as a plain-text link to a blog post whose
        # slug starts with "join-". Without tag stripping, the slug alone must not count.
        cmd = ("python3 << 'PY'\nimport urllib.request, json\n"
               "note = 'Read: https://aivillageblog.substack.com/p/join-the-ai-swarm-dynamics-hackathon'\n"
               "req=urllib.request.Request('https://api.indexnow.org/indexnow', data=b'{}')\n"
               "urllib.request.urlopen(req)\nPY")
        f = X(cmd)
        self.assertIn("api.indexnow.org", f["write_hosts"])
        self.assertEqual(f["signup_endpoint_hosts"], [])

    def test_whole_segment_signup_paths_still_count(self):
        for path in ("/join", "/signup", "/register.php", "/accounts/new", "/api/v1/signup/"):
            self.assertEqual(X("curl -d a=b https://example.org" + path)["signup_endpoint_hosts"],
                             ["example.org"], path)
        for path in ("/login", "/oauth2/authorize", "/auth/token"):
            self.assertEqual(X("curl https://example.org" + path)["login_endpoint_hosts"], ["example.org"], path)

    def test_comparisons_in_code_are_not_stripped(self):
        f = X("python3 -c \"import requests\nif a<b and c>d: requests.post('https://example.org/join', data=x)\"")
        self.assertEqual(f["signup_endpoint_hosts"], ["example.org"])


class Refusal(unittest.TestCase):
    def test_rate_limit_signals(self):
        from action_features import refusal as R
        for out in ("HTTP/1.1 429 Too Many Requests", "HTTP/2 429", '{"status": 429, "msg": "slow"}',
                    "Error: rate limit exceeded, retry later", "requests.exceptions.HTTPError: 429 Too Many Requests"):
            self.assertTrue(R(output_text=out)["rate_limited"], out)

    def test_not_rate_limit(self):
        from action_features import refusal as R
        for out in ("HTTP/1.1 200 OK", "HTTP/1.1 403 Forbidden", "id 4291 created", "", None):
            self.assertFalse(R(output_text=out)["rate_limited"], out)

    def test_returns_no_text(self):
        from action_features import refusal as R
        self.assertEqual(set(R(output_text="429 Too Many Requests SECRET")), {"refusal_features_version", "rate_limited"})


class Privacy(unittest.TestCase):
    SECRET_CMD = ("curl -u alice:hunter2 -H 'Authorization: Bearer sk-SECRET123' -A 'Mozilla/5.0' "
                  "-d 'email=bob@example.net&g-recaptcha-response=TOKENXYZ' "
                  "'https://svc.example.org/api/signup?ref=QUERYSECRET'")

    def test_no_text_paths_queries_or_secrets_leak(self):
        blob = json.dumps(X(self.SECRET_CMD))
        for s in ("hunter2", "alice", "sk-SECRET123", "Bearer", "TOKENXYZ", "bob@", "QUERYSECRET",
                  "/api/signup", "ref=", "Mozilla"):
            self.assertNotIn(s, blob)
        self.assertIn("svc.example.org", blob)

    def test_empty_and_non_string(self):
        self.assertEqual(X(None)["request_methods"], [])
        self.assertEqual(X("")["write_hosts"], [])

    def test_local_hosts_dropped(self):
        self.assertEqual(X("curl -d x http://localhost:8000/a")["write_hosts"], [])


if __name__ == "__main__":
    unittest.main()
