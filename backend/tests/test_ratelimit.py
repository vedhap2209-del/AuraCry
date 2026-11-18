"""Phase 11: rate limiting + spam protection. Run from backend/:  python -m unittest tests.test_ratelimit -v"""
import unittest

from tests import _helpers as H
import db
import ratelimit
import security as S
from app import create_app


class RateLimit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(load_model=False)
        cls.app.config["RATELIMIT_ENABLED"] = True          # explicitly on for this suite
        cls.app.test_client_class = H.CsrfClient
        db.connect().execute("INSERT OR IGNORE INTO users(name,email,password_hash,pin_hash,role) VALUES('R','rl@test.com',?,?, 'USER')",
                             (S.hash_password("Good12345"), S.hash_pin(H.TEST_PIN))).connection.commit()

    def setUp(self):
        ratelimit.reset()

    def test_auth_surface_is_throttled_per_ip(self):
        c = self.client = self.app.test_client()
        hit429 = False
        for _ in range(60):
            r = c.post("/api/auth/login/identify", json={"identifier": "rl@test.com", "login_as": "USER"})
            if r.status_code == 429:
                hit429 = True
                self.assertEqual(r.get_json()["error"], "rate_limited")
                self.assertIn("Retry-After", r.headers)
                break
        self.assertTrue(hit429, "auth endpoint should rate-limit a burst from one IP")

    def test_global_api_limit(self):
        with self.app.app_context():                            # too_many() builds a jsonify response
            self.assertIsNone(ratelimit.limit("api:x", 2, 60))
            self.assertIsNone(ratelimit.limit("api:x", 2, 60))
            self.assertIsNotNone(ratelimit.limit("api:x", 2, 60))   # third over a limit of 2

    def test_duplicate_file_guard(self):
        self.assertFalse(ratelimit.duplicate(1, "abc"))
        self.assertTrue(ratelimit.duplicate(1, "abc"))          # same user + same file again
        self.assertFalse(ratelimit.duplicate(2, "abc"))         # different user is fine

    def test_concurrency_guard(self):
        with self.app.app_context():
            self.assertIsNone(ratelimit.begin_analysis(1))
            self.assertIsNotNone(ratelimit.begin_analysis(1))   # second concurrent start blocked
            ratelimit.end_analysis(1)
            self.assertIsNone(ratelimit.begin_analysis(1))      # allowed again after it finishes


if __name__ == "__main__":
    unittest.main()
