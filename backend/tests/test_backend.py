"""Backend tests. Run from backend/:  python -m unittest discover -v"""
import io
import unittest

from werkzeug.security import generate_password_hash

from tests import _helpers as H
import db
from app import create_app


class Backend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(load_model=True)
        cls.app.test_client_class = H.CsrfClient
        import security as S
        c = db.connect()
        for n, e, p, r in (("Ada Admin", "admin@test.com", "Admin1234", "ADMIN"), ("Una User", "user@test.com", "User12345", "USER"),
                           ("Ula Other", "other@test.com", "Other12345", "USER")):
            c.execute("INSERT INTO users(name,email,password_hash,pin_hash,role) VALUES(?,?,?,?,?)",
                      (n, e, S.hash_password(p), S.hash_pin(H.TEST_PIN), r))
        c.commit(); c.close()

    def client(self):
        return self.app.test_client()

    def login(self, c, email, pw, as_):
        return H.three_step_login(c, email, pw, as_)

    # ---------------------------------------------------------------- role rules
    def test_register_ignores_role(self):
        c = self.client()
        r = c.post("/api/auth/register", json={"name": "Eve Evil", "email": "eve@test.com", "password": "Passw0rd1",
                                               "confirm_password": "Passw0rd1", "pin": "2468", "role": "ADMIN"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(db.connect().execute("SELECT role FROM users WHERE email='eve@test.com'").fetchone()[0], "USER")

    def test_login_matrix(self):
        c = self.client()
        self.assertEqual(self.login(c, "user@test.com", "User12345", "USER").status_code, 200)
        self.assertEqual(self.login(self.client(), "user@test.com", "User12345", "ADMIN").status_code, 403)
        self.assertEqual(self.login(self.client(), "nobody@test.com", "Whatever12", "ADMIN").status_code, 403)
        self.assertEqual(self.login(self.client(), "admin@test.com", "Admin1234", "ADMIN").status_code, 200)
        self.assertEqual(self.login(self.client(), "admin@test.com", "Admin1234", "USER").status_code, 403)
        self.assertEqual(self.login(self.client(), "user@test.com", "wrongpass1", "USER").status_code, 401)

    def test_user_blocked_from_admin_api_and_page(self):
        c = self.client(); self.login(c, "user@test.com", "User12345", "USER")
        for p in ("/api/admin/stats", "/api/admin/users", "/api/admin/dataset", "/api/admin/model/performance", "/api/admin/reports"):
            self.assertEqual(c.get(p).status_code, 403, p)
        self.assertEqual(c.get("/admin/dashboard").status_code, 403)
        self.assertEqual(c.post("/api/admin/model/retrain").status_code, 403)

    def test_anonymous_blocked(self):
        c = self.client()
        for p in ("/api/dashboard", "/api/analyses", "/api/admin/stats", "/api/lab/samples"):
            self.assertEqual(c.get(p).status_code, 401, p)
        self.assertEqual(c.get("/admin/dashboard").status_code, 403)

    def test_logout_revokes(self):
        c = self.client(); self.login(c, "user@test.com", "User12345", "USER")
        self.assertEqual(c.get("/api/dashboard").status_code, 200)
        c.post("/api/auth/logout")
        self.assertEqual(c.get("/api/dashboard").status_code, 401)

    def test_validation(self):
        c = self.client()
        P = {"pin": "2468"}
        for body in ({"name": "A", "email": "x@y.com", "password": "Passw0rd1", "confirm_password": "Passw0rd1", **P},
                     {"name": "Abe", "email": "bad", "password": "Passw0rd1", "confirm_password": "Passw0rd1", **P},
                     {"name": "Abe", "email": "a@b.com", "password": "abcdefgh", "confirm_password": "abcdefgh", **P},
                     {"name": "Abe", "email": "a@b.com", "password": "abc", "confirm_password": "abc", **P},
                     {"name": "Abe", "email": "a@b.com", "password": "Passw0rd1", "confirm_password": "Passw0rd2", **P},
                     {"name": "Abe", "email": "a@b.com", "password": "Passw0rd1", "confirm_password": "Passw0rd1", "pin": "12"}):
            self.assertEqual(c.post("/api/auth/register", json=body).status_code, 400, body)

    # ---------------------------------------------------------------- real analysis
    def test_full_analysis_flow(self):
        self.assertTrue(self.app.test_client().get("/api/health").json["status"] == "ready")
        c = self.client(); self.login(c, "user@test.com", "User12345", "USER")
        y, sr = H.synth_cry()
        r = c.post("/api/analyses", data={"audio": (H.wav_bytes(y, sr), "cry.wav")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.json)
        a = r.json["analysis"]; res = a["result"]
        self.assertGreaterEqual(res["n_units"], 3)
        self.assertAlmostEqual(sum(res["probabilities"].values()), 1.0, places=2)
        self.assertEqual([t["key"] for t in res["trace"]][:3], ["decode", "segment", "features"])
        for k in ("rf", "ada", "meta", "explain", "advice"):
            self.assertIn(k, [t["key"] for t in res["trace"]])
        self.assertIn("rf", res["stages"]); self.assertIn("ada", res["stages"])
        pitches = [u["features"]["Mean_F0"] for u in res["units"]]
        for p, true in zip(pitches, (420, 480, 390)):
            self.assertLess(abs(p - true) / true, 0.06, pitches)           # real pitch tracking, not canned
        self.assertTrue(res["advice"]["steps"] and res["advice"]["red_flags"])
        # files + ownership
        self.assertEqual(c.get(a["audio_url"]).status_code, 200)
        self.assertEqual(c.get(a["spectrogram_url"]).status_code, 200)
        self.assertEqual(c.get(a["spectrogram_url"]).mimetype, "image/png")
        self.assertEqual(c.get("/api/analyses").json["analyses"][0]["id"], a["id"])
        # Phase 14: downloadable PDF report (owner can; a different user cannot)
        rep = c.get(a["report_url"])
        self.assertEqual(rep.status_code, 200, rep.data[:200])
        self.assertEqual(rep.mimetype, "application/pdf")
        self.assertTrue(rep.data.startswith(b"%PDF-"))
        other = self.client(); self.login(other, "other@test.com", "Other12345", "USER")
        self.assertEqual(other.get(f"/api/analyses/{a['id']}").status_code, 404)
        self.assertEqual(other.get(a["audio_url"]).status_code, 404)
        self.assertEqual(other.get(a["report_url"]).status_code, 404)
        adm = self.client(); self.login(adm, "admin@test.com", "Admin1234", "ADMIN")
        self.assertEqual(adm.get(f"/api/admin/analyses/{a['id']}").status_code, 200)
        self.assertEqual(adm.get(a["audio_url"]).status_code, 200)
        self.assertGreaterEqual(adm.get("/api/admin/stats").json["total_analyses"], 1)
        self.assertGreaterEqual(len(adm.get("/api/admin/reports").json["distribution"]), 1)
        self.assertEqual(adm.get("/api/admin/analyses?q=cry.wav").json["analyses"][0]["id"], a["id"])

    def test_different_audio_gives_different_features(self):
        c = self.client(); self.login(c, "user@test.com", "User12345", "USER")
        y1, sr = H.synth_cry(); y2, _ = H.synth_cry(bursts=((0.2, 1.4, 700), (2.0, 3.2, 800)), total=3.6, seed=3)
        f = [c.post("/api/analyses", data={"audio": (H.wav_bytes(y, sr), "x.wav")}, content_type="multipart/form-data").json["analysis"]["result"]["units"][0]["features"]["Mean_F0"] for y in (y1, y2)]
        self.assertGreater(abs(f[0] - f[1]), 150)

    def test_invalid_audio_rejected(self):
        c = self.client(); self.login(c, "user@test.com", "User12345", "USER")
        post = lambda b, n: c.post("/api/analyses", data={"audio": (io.BytesIO(b), n)}, content_type="multipart/form-data")
        self.assertEqual(post(b"hello", "notes.txt").status_code, 400)
        self.assertEqual(post(b"this is not audio", "fake.wav").status_code, 422)
        import numpy as np
        self.assertEqual(post(H.wav_bytes(np.zeros(44100 * 2, dtype="float32"), 44100).read(), "silent.wav").status_code, 422)
        self.assertEqual(post(H.wav_bytes(np.random.randn(1000).astype("float32") * .3, 44100).read(), "short.wav").status_code, 422)
        self.assertEqual(c.post("/api/analyses", data={}, content_type="multipart/form-data").status_code, 400)

    # ---------------------------------------------------------------- lab
    def test_lab_dataset_row_and_audio(self):
        c = self.client(); self.login(c, "user@test.com", "User12345", "USER")
        s = c.get("/api/lab/samples").json["samples"]
        self.assertGreaterEqual(len(s), 9)
        r = c.post("/api/lab/run", json={"row": s[0]["id"]})
        self.assertEqual(r.status_code, 200); res = r.json["result"]
        self.assertEqual(res["source"], "dataset_row"); self.assertEqual(res["n_units"], 1)
        self.assertEqual(set(res["stages"]), {"rf", "ada"})
        self.assertEqual(c.post("/api/lab/run", json={"row": 10 ** 6}).status_code, 400)
        y, sr = H.synth_cry()
        r = c.post("/api/lab/run", data={"audio": (H.wav_bytes(y, sr), "demo.wav")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200); self.assertEqual(r.json["result"]["source"], "audio")
        self.assertEqual(c.get("/api/analyses").json["analyses"], c.get("/api/analyses").json["analyses"])

    # ---------------------------------------------------------------- admin
    def test_admin_user_management_and_dataset(self):
        adm = self.client(); self.login(adm, "admin@test.com", "Admin1234", "ADMIN")
        users = adm.get("/api/admin/users?q=other").json["users"]
        uid = users[0]["id"]
        self.assertEqual(adm.patch(f"/api/admin/users/{uid}/status", json={"status": "INACTIVE"}).status_code, 200)
        self.assertEqual(self.login(self.client(), "other@test.com", "Other12345", "USER").status_code, 401 if False else 403)
        self.assertEqual(adm.patch(f"/api/admin/users/{uid}/status", json={"status": "ACTIVE"}).status_code, 200)
        admin_id = db.connect().execute("SELECT id FROM users WHERE role='ADMIN'").fetchone()[0]
        self.assertEqual(adm.delete(f"/api/admin/users/{admin_id}").status_code, 400)
        d = adm.get("/api/admin/dataset").json
        self.assertEqual(d["test"]["rows"], 931)
        self.assertFalse(d["train"]["empty"])          # the real balanced training CSV is now present (Phase 2)
        m = adm.get("/api/admin/model/performance").json
        self.assertTrue(m["model_ready"]); self.assertIn("comparison", m["metrics"])
        bad = adm.post("/api/admin/dataset/upload", data={"role": "train", "file": (io.BytesIO(b"a,b\n1,2\n"), "x.csv")}, content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
