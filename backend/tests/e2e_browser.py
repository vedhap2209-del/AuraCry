"""Real-browser end-to-end test.  pip install playwright && playwright install chromium
Run from backend/:  python -m tests.e2e_browser     (starts its own server on a temp database)"""
import os, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

from tests import _helpers as H   # sets SECRET_KEY / DATABASE_PATH temp env
import db
from werkzeug.security import generate_password_hash
from playwright.sync_api import sync_playwright

PORT, URL = 5057, "http://127.0.0.1:5057"
SHOTS = Path(os.environ.get("SHOTS", tempfile.gettempdir())) / "shots"; SHOTS.mkdir(parents=True, exist_ok=True)
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""), flush=True)


def main():
    db.init(); c = db.connect()
    c.execute("INSERT INTO users(name,email,password_hash,role) VALUES('Ada Admin','admin@test.com',?, 'ADMIN')", (generate_password_hash("Admin1234"),)); c.commit(); c.close()
    wav = Path(tempfile.gettempdir()) / "e2e_cry.wav"
    y, sr = H.synth_cry(); wav.write_bytes(H.wav_bytes(y, sr).read())
    env = dict(os.environ, PORT=str(PORT))
    srv = subprocess.Popen([sys.executable, "app.py"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try: urllib.request.urlopen(URL + "/api/health"); break
            except Exception: time.sleep(0.5)
        with sync_playwright() as p:
            br = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
            ctx = br.new_context(viewport={"width": 430, "height": 900}, permissions=["microphone"]); pg = ctx.new_page()
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "fonts.g" not in m.text and "Failed to load resource" not in m.text and "ERR_" not in m.text else None)
            pg.goto(URL); pg.wait_for_selector("text=LOGIN"); pg.screenshot(path=str(SHOTS / "01_login.png"))
            check("login page shows mascot + role switch", pg.locator(".mc-orb").count() == 1 and pg.locator(".seg button").count() == 2)
            # empty submit
            pg.click("button.btn.lg"); check("empty login shows message", pg.locator(".notice.err").count() == 1)
            # register
            pg.click("text=Register"); pg.fill("input[name=name]", "Una User"); pg.fill("input[name=email]", "una@test.com"); pg.fill("input[name=password]", "abcdefgh"); pg.fill("input[name=confirm_password]", "abcdefgh"); pg.click("button.btn.lg")
            check("weak password rejected", pg.locator(".notice.err").count() == 1)
            pg.fill("input[name=password]", "Passw0rd1"); pg.fill("input[name=confirm_password]", "Passw0rd1"); pg.click("button.btn.lg")
            pg.wait_for_selector("text=Account created"); check("registration -> login with notice", True)
            # wrong password / admin selection
            pg.fill("input[name=identifier]", "una@test.com"); pg.fill("input[name=password]", "wrongpass1"); pg.click("button.btn.lg"); pg.wait_for_selector(".notice.err")
            check("wrong password message", "Invalid email or password" in pg.inner_text(".notice.err"))
            pg.click("text=Admin >> nth=0"); pg.fill("input[name=password]", "Passw0rd1"); pg.click("button.btn.lg"); pg.wait_for_selector(".notice.err")
            check("user choosing Admin gets Access Denied", "Access Denied" in pg.inner_text(".notice.err"))
            pg.click(".seg button >> text=User"); pg.click("button.btn.lg"); pg.wait_for_selector("text=Welcome back")
            pg.screenshot(path=str(SHOTS / "02_home.png")); check("user login -> home", "/user/home" in pg.url)
            # unauthorized admin page
            r = pg.goto(URL + "/admin/dashboard"); check("user cannot open /admin/dashboard (server 403)", r.status == 403)
            pg.goto(URL + "/user/home"); pg.wait_for_selector("text=Welcome back")
            # upload flow
            pg.click("text=Start Cry Analysis"); pg.wait_for_selector("text=Upload Audio")
            pg.set_input_files("input[type=file]", {"name": "notes.txt", "mimeType": "text/plain", "buffer": b"hi"}); pg.wait_for_selector(".notice.err"); check("txt upload rejected in browser", True)
            pg.set_input_files("input[type=file]", str(wav)); pg.wait_for_selector("text=GET RESULTS"); pg.screenshot(path=str(SHOTS / "03_ready.png"))
            check("audio ready shows duration", "Duration" in pg.inner_text(".card"))
            pg.click("text=GET RESULTS"); pg.wait_for_selector("text=Random Forest", timeout=20000); pg.screenshot(path=str(SHOTS / "04_processing.png"))
            pg.wait_for_url("**/user/result/*", timeout=30000); pg.wait_for_selector("text=Why this answer"); pg.wait_for_timeout(1200)
            pg.screenshot(path=str(SHOTS / "05_result.png"), full_page=True)
            txt = pg.inner_text(".phone")
            for needle in ("All categories", "Why this answer", "What you can try", "When to get medical help", "Mel spectrogram", "Reliability"):
                check(f"result shows '{needle}'", needle in txt)
            pg.click("summary"); pg.wait_for_selector(".stage"); check("trace has Random Forest, AdaBoost, Logistic Regression", all(s in pg.inner_text(".lab-flow") for s in ("Random Forest", "AdaBoost", "Logistic Regression")))
            check("spectrogram image loaded", pg.evaluate("document.querySelector('img.spec').naturalWidth") > 100)
            # history
            pg.click("button[aria-label=Back]"); pg.wait_for_selector("text=Welcome back"); pg.click("text=History"); pg.wait_for_selector(".item"); check("history lists analysis", pg.locator(".item").count() == 1)
            pg.click(".item"); pg.wait_for_selector("text=Why this answer"); check("history details opens", True)
            # lab
            pg.click("button[aria-label=Back]"); pg.click("nav >> text=Lab"); pg.wait_for_selector(".sample"); pg.click(".sample >> nth=3"); pg.wait_for_selector("text=Decision"); pg.wait_for_timeout(2500)
            pg.screenshot(path=str(SHOTS / "06_lab_row.png"), full_page=True); check("lab (dataset row) renders 3 stages", "Logistic Regression" in pg.inner_text(".lab-flow") and "Label in dataset" in pg.inner_text(".lab-flow"))
            pg.set_input_files("input[type=file]", str(wav)); pg.wait_for_selector("svg.wf", timeout=20000); pg.wait_for_timeout(2500)
            pg.screenshot(path=str(SHOTS / "07_lab_audio.png"), full_page=True); check("lab (audio) draws waveform + units", pg.locator("svg.wf rect").count() >= 3)
            # profile + logout + back guard
            pg.click("text=Profile"); pg.wait_for_selector("text=Edit profile"); pg.click("text=Logout"); pg.wait_for_selector("text=LOGIN")
            pg.goto(URL + "/user/home"); pg.wait_for_selector("text=LOGIN"); check("after logout /user/home -> login", "/login" in pg.url)
            # dark mode
            pg.click(".themebtn"); check("dark mode toggles", pg.evaluate("document.documentElement.dataset.theme") == "dark"); pg.click(".themebtn")
            # admin
            ctx2 = br.new_context(viewport={"width": 1280, "height": 850}); a = ctx2.new_page(); a.on("pageerror", lambda e: errs.append(str(e)))
            a.goto(URL); a.click("text=Admin >> nth=0"); a.fill("input[name=identifier]", "admin@test.com"); a.fill("input[name=password]", "Admin1234"); a.click("button.btn.lg"); a.wait_for_selector("text=Dashboard")
            a.screenshot(path=str(SHOTS / "08_admin_dash.png")); check("admin login -> dashboard with real counts", "Analyses" in a.inner_text("main") and "Dataset rows" in a.inner_text("main"))
            for path, needle in (("/admin/users", "Una User"), ("/admin/dataset", "Training CSV"), ("/admin/model", "Model comparison"), ("/admin/model/confusion", "Predicted"), ("/admin/records", "AC-"), ("/admin/reports", "Cry type distribution"), ("/admin/profile", "Admin profile"), ("/admin/lab", "Pipeline Lab")):
                a.goto(URL + path); a.wait_for_selector(f"text={needle}", timeout=15000); check(f"admin page {path}", True)
            a.goto(URL + "/admin/model"); a.wait_for_selector("text=Model comparison"); a.screenshot(path=str(SHOTS / "09_admin_model.png"), full_page=True)
            a.goto(URL + "/admin/dataset"); a.wait_for_selector("text=EMPTY"); a.screenshot(path=str(SHOTS / "10_admin_dataset.png")); check("empty training CSV is flagged", True)
            a.goto(URL + "/admin/records"); a.click("tr.click >> nth=0"); a.wait_for_selector("text=Analysis ID"); check("admin record details", "Una User" in a.inner_text("main"))
            a.goto(URL + "/admin/users"); a.click("tr.click:has-text('Una User')"); a.wait_for_selector("button:text-is('Deactivate')"); a.click("button:text-is('Deactivate')"); a.wait_for_selector("button:text-is('Activate')"); check("admin can deactivate a user", True)
            check("no JS errors in console", not errs, "; ".join(errs[:3]))
            br.close()
    finally:
        srv.terminate()
    bad = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed"); sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
