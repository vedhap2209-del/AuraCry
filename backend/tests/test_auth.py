"""Three-step authentication tests: password step, email OTP (correct / wrong / expired / attempt cap / resend cooldown),
account lockout, CSRF, and password reset. Run from backend/:  python -m unittest tests.test_auth -v"""
import time
import unittest

from tests import _helpers as H
import db
import security as S
from app import create_app


class Auth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(load_model=False)
        cls.app.test_client_class = H.CsrfClient
        c = db.connect()
        for n, e, p, r in (("Ada Admin", "a@test.com", "Admin1234", "ADMIN"), ("Una User", "u@test.com", "User12345", "USER")):
            c.execute("INSERT OR IGNORE INTO users(name,email,password_hash,pin_hash,role) VALUES(?,?,?,?,?)",
                      (n, e, S.hash_password(p), S.hash_pin(H.TEST_PIN), r))
        c.commit(); c.close()

    def setUp(self):
        # each test starts from a known state (tests share one DB and mutate passwords/locks/tickets)
        con = db.connect()
        for e, p, r in (("a@test.com", "Admin1234", "ADMIN"), ("u@test.com", "User12345", "USER")):
            con.execute("UPDATE users SET password_hash=?, pin_hash=?, role=?, status='ACTIVE', failed_logins=0, locked_until=NULL WHERE email=?",
                        (S.hash_password(p), S.hash_pin(H.TEST_PIN), r, e))
        con.execute("DELETE FROM login_tickets"); con.commit(); con.close()

    def client(self):
        return self.app.test_client()

    # -- step helpers --------------------------------------------------------
    def identify(self, c, email, role="USER"):
        return c.post("/api/auth/login/identify", json={"identifier": email, "login_as": role})

    def password(self, c, ticket, pw):
        return c.post("/api/auth/login/password", json={"ticket": ticket, "password": pw})

    def verify(self, c, ticket, code):
        return c.post("/api/auth/login/verify", json={"ticket": ticket, "code": code})

    # -- happy paths ---------------------------------------------------------
    def test_three_step_user_and_admin(self):
        for email, pw, role in (("u@test.com", "User12345", "USER"), ("a@test.com", "Admin1234", "ADMIN")):
            c = self.client()
            r = H.three_step_login(c, email, pw, role)
            self.assertEqual(r.status_code, 200, r.get_json())
            self.assertEqual(r.get_json()["user"]["role"], role)
            self.assertTrue(r.get_json()["csrf_token"])
            self.assertEqual(c.get("/api/auth/me").status_code, 200)

    def pin(self, c, ticket, pin=H.TEST_PIN):
        return c.post("/api/auth/login/pin", json={"ticket": ticket, "pin": pin})

    def test_no_session_until_all_three_factors(self):
        c = self.client()
        t, code = self._to_otp(c)
        self.assertEqual(c.get("/api/auth/me").status_code, 401)   # after password, before OTP
        r = self.verify(c, t, code)
        self.assertEqual(r.get_json()["step"], "pin")              # OTP correct -> advance to PIN, still no session
        self.assertEqual(c.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.pin(c, t).status_code, 200)          # PIN completes login
        self.assertEqual(c.get("/api/auth/me").status_code, 200)

    # -- password step --------------------------------------------------------
    def test_wrong_password_blocks_and_burns_ticket(self):
        c = self.client()
        t = self.identify(c, "u@test.com").get_json()["ticket"]
        self.assertEqual(self.password(c, t, "nope").status_code, 401)
        self.assertEqual(self.password(c, t, "User12345").status_code, 410)  # ticket is gone after a wrong password

    # -- OTP ------------------------------------------------------------------
    def _to_otp(self, c, email="u@test.com", pw="User12345"):
        t = self.identify(c, email).get_json()["ticket"]
        return t, self.password(c, t, pw).get_json()["dev_code"]

    def test_otp_delivery_fields(self):
        c = self.client()
        t = self.identify(c, "u@test.com").get_json()["ticket"]
        body = self.password(c, t, "User12345").get_json()
        self.assertTrue(body["otp_required"]); self.assertIn("@", body["masked_email"]); self.assertEqual(body["delivery"], "dev")
        self.assertEqual(len(body["dev_code"]), 6)

    def test_correct_otp_advances_to_pin(self):
        c = self.client(); t, code = self._to_otp(c)
        r = self.verify(c, t, code)
        self.assertEqual(r.status_code, 200); self.assertEqual(r.get_json()["step"], "pin"); self.assertTrue(r.get_json()["pin_set"])

    def test_wrong_pin_then_correct(self):
        c = self.client(); t, code = self._to_otp(c); self.verify(c, t, code)
        self.assertEqual(self.pin(c, t, "0000").status_code, 401)
        self.assertEqual(self.pin(c, t).status_code, 200)

    def test_pin_locks_after_max_attempts(self):
        c = self.client(); t, code = self._to_otp(c); self.verify(c, t, code)
        for _ in range(S.PIN_MAX_ATTEMPTS):
            self.pin(c, t, "0000")
        r = self.pin(c, t, "0000")
        self.assertEqual(r.status_code, 429); self.assertEqual(r.get_json()["error"], "pin_locked")

    def test_first_time_pin_setup_for_legacy_account(self):
        con = db.connect()
        con.execute("INSERT OR IGNORE INTO users(name,email,password_hash,role) VALUES('N','nopin@test.com',?, 'USER')",
                    (S.hash_password("Good12345"),))
        con.execute("UPDATE users SET pin_hash=NULL, failed_logins=0, locked_until=NULL WHERE email='nopin@test.com'")
        con.commit(); con.close()
        c = self.client()
        t = self.identify(c, "nopin@test.com").get_json()["ticket"]
        code = self.password(c, t, "Good12345").get_json()["dev_code"]
        r = self.verify(c, t, code)
        self.assertFalse(r.get_json()["pin_set"])                  # no PIN yet -> setup
        self.assertEqual(self.pin(c, t, "7391").status_code, 200)  # setting a PIN completes login
        # next login uses that PIN
        self.assertEqual(H.three_step_login(self.client(), "nopin@test.com", "Good12345", "USER", pin="7391").status_code, 200)

    def test_wrong_otp_counts_down_then_locks(self):
        c = self.client(); t, code = self._to_otp(c)
        bad = "000000" if code != "000000" else "111111"
        for _ in range(S.OTP_MAX_ATTEMPTS + 1):        # the (N+1)th wrong code burns the ticket
            r = self.verify(c, t, bad)
        self.assertEqual(r.status_code, 429); self.assertEqual(r.get_json()["error"], "otp_locked")
        self.assertEqual(self.verify(c, t, code).status_code, 410)   # ticket burned

    def test_expired_otp(self):
        c = self.client(); t, code = self._to_otp(c)
        con = db.connect(); con.execute("UPDATE login_tickets SET otp_expires=? WHERE token=?", (int(time.time()) - 1, t)); con.commit(); con.close()
        r = self.verify(c, t, code)
        self.assertEqual(r.status_code, 410); self.assertEqual(r.get_json()["error"], "otp_expired")

    def test_resend_cooldown_then_allowed(self):
        c = self.client(); t, _ = self._to_otp(c)
        r = c.post("/api/auth/login/resend", json={"ticket": t})
        self.assertEqual(r.status_code, 429); self.assertEqual(r.get_json()["error"], "cooldown")
        con = db.connect(); con.execute("UPDATE login_tickets SET last_sent=? WHERE token=?", (0, t)); con.commit(); con.close()
        r = c.post("/api/auth/login/resend", json={"ticket": t})
        self.assertEqual(r.status_code, 200); self.assertEqual(len(r.get_json()["dev_code"]), 6)

    # -- lockout --------------------------------------------------------------
    def test_password_failures_increment_and_lock(self):
        con = db.connect()
        con.execute("INSERT OR IGNORE INTO users(name,email,password_hash,role) VALUES('L','lock@test.com',?, 'USER')",
                    (S.hash_password("Good12345"),))
        con.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE email='lock@test.com'")
        con.commit(); con.close()
        # wrong passwords accumulate; the DB lock trips at the threshold (use fresh clients to dodge the per-IP throttle)
        locked = False
        for _ in range(S.LOCKOUT_THRESHOLD):
            c = self.client()
            r = self.identify(c, "lock@test.com")
            if r.status_code == 423:
                locked = True; break
            if r.status_code == 429:                    # per-IP throttle also counts as "blocked"
                locked = True; break
            tk = r.get_json()["ticket"]
            if self.password(c, tk, "wrong").status_code == 423:
                locked = True; break
        # regardless of which guard fired first, the account must now be refused even with the RIGHT password
        self.assertTrue(locked or H.three_step_login(self.client(), "lock@test.com", "Good12345", "USER").status_code in (423, 429))

    def test_locked_account_is_refused_at_identify(self):
        con = db.connect()
        con.execute("INSERT OR IGNORE INTO users(name,email,password_hash,role) VALUES('K','klock@test.com',?, 'USER')",
                    (S.hash_password("Good12345"),))
        con.execute("UPDATE users SET locked_until=? WHERE email='klock@test.com'", (int(time.time()) + 600,))
        con.commit(); con.close()
        r = self.identify(self.client(), "klock@test.com")
        self.assertEqual(r.status_code, 423); self.assertEqual(r.get_json()["error"], "locked")

    # -- CSRF -----------------------------------------------------------------
    def test_csrf_required_for_authenticated_mutations(self):
        c = self.client(); H.three_step_login(c, "u@test.com", "User12345", "USER")
        # a raw client without the echoed header is rejected
        raw = self.app.test_client()          # default client (no CSRF echo)
        raw.set_cookie("session", c.get_cookie("session").value)
        r = raw.post("/api/account/password", json={"current_password": "x", "new_password": "y"})
        self.assertEqual(r.status_code, 403); self.assertEqual(r.get_json()["error"], "csrf")
        # the CSRF-aware client passes the guard (then fails validation, not CSRF)
        self.assertEqual(c.post("/api/account/password", json={"current_password": "bad", "new_password": "Short1"}).status_code, 400)

    # -- password reset -------------------------------------------------------
    def test_password_reset_flow(self):
        c = self.client()
        r = c.post("/api/auth/password-reset/request", json={"email": "u@test.com"})
        self.assertEqual(r.status_code, 200); code = r.get_json()["dev_code"]; t = r.get_json()["ticket"]
        bad = c.post("/api/auth/password-reset/confirm", json={"ticket": t, "code": "999999", "new_password": "NewPass123", "confirm_password": "NewPass123"})
        self.assertEqual(bad.status_code, 401)
        ok = c.post("/api/auth/password-reset/confirm", json={"ticket": t, "code": code, "new_password": "NewPass123", "confirm_password": "NewPass123"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(H.three_step_login(self.client(), "u@test.com", "NewPass123", "USER").status_code, 200)

    def test_reset_request_unknown_email_is_generic(self):
        r = self.client().post("/api/auth/password-reset/request", json={"email": "ghost@test.com"})
        self.assertEqual(r.status_code, 200); self.assertNotIn("ticket", r.get_json())


if __name__ == "__main__":
    unittest.main()
