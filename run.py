"""One-command start:  python run.py   (creates .env + first admin if missing, then starts the server)."""
import os, secrets, subprocess, sys
from pathlib import Path

B = Path(__file__).resolve().parent / "backend"
env = B / ".env"
if not env.exists():
    env.write_text((B / ".env.example").read_text().replace("change-me", secrets.token_hex(32)))
    print("Created backend/.env with a fresh SECRET_KEY")
os.chdir(B); sys.path.insert(0, str(B))
import db; db.init()
c = db.connect()
admin_email = (os.environ.get("ADMIN_EMAIL") or "admin@auracry.local").strip().lower()
admin_row = c.execute("SELECT id,email FROM users WHERE role='ADMIN' ORDER BY id LIMIT 1").fetchone()
if not admin_row:
    from werkzeug.security import generate_password_hash
    c.execute("INSERT INTO users(name,email,password_hash,role) VALUES('Main Admin',?,?, 'ADMIN')",
              (admin_email, generate_password_hash("Admin12345")))
    c.commit()
    print(f"First admin created -> {admin_email} / Admin12345   (change it after first login)")
elif os.environ.get("ADMIN_EMAIL") and admin_row["email"] == "admin@auracry.local":
    conflict = c.execute("SELECT id FROM users WHERE email=? AND id<>?", (admin_email, admin_row["id"])).fetchone()
    if not conflict:
        c.execute("UPDATE users SET email=? WHERE id=?", (admin_email, admin_row["id"]))
        c.commit()
        print(f"Admin email updated to {admin_email}; existing password and PIN hashes were preserved.")
c.close()
from app import create_app
print("Open http://127.0.0.1:5000")
create_app().run(host="127.0.0.1", port=5000, debug=False)
