#!/usr/bin/env python3
"""
ClipForge License Server v2
============================
Run: python3 license_server.py serve
Admin: http://localhost:8080/admin

CLI:
  python3 license_server.py generate --plan solo --email buyer@email.com
  python3 license_server.py list
  python3 license_server.py revoke CFAI-XXXX-XXXX-XXXX-XXXX
  python3 license_server.py serve --port 8080

DEPLOY TO PRODUCTION (Railway.app - free tier):
  1. Create account at railway.app
  2. New project -> Deploy from GitHub or upload folder
  3. Set env var: LICENSE_SECRET=your-long-random-string
  4. Copy your Railway URL into clipforge.py LICENSE_SERVER_URL
"""

import os, sys, json, secrets, string
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH   = Path(__file__).parent / "licenses.json"
ADMIN_HTML= Path(__file__).parent / "admin_dashboard.html"
SECRET    = os.environ.get("LICENSE_SECRET", "clipforge-change-this-in-production")
ADMIN_PASS= os.environ.get("ADMIN_PASSWORD", "clipforge-admin-2025")

PLANS = {
    "solo": {"seats":1,"label":"6-Month Solo", "price":497,"days":185},
    "team": {"seats":3,"label":"6-Month Team", "price":997,"days":185},
    "pro":  {"seats":1,"label":"Monthly",       "price":97, "days":31},
}

def load_db():
    if DB_PATH.exists():
        try: return json.loads(DB_PATH.read_text())
        except: pass
    return {"keys":{}}

def save_db(db):
    DB_PATH.write_text(json.dumps(db, indent=2))

def new_key():
    chars = string.ascii_uppercase + string.digits
    segs = ["".join(secrets.choice(chars) for _ in range(4)) for _ in range(4)]
    return "CFAI-" + "-".join(segs)

def make_record(plan, email="", note=""):
    p = PLANS[plan]
    return {
        "plan":plan,"seats":p["seats"],"label":p["label"],"price":p["price"],
        "email":email,"note":note,"active":True,"activations":[],
        "created":datetime.now().isoformat(),
        "expires":(datetime.now()+timedelta(days=p["days"])).isoformat(),
        "last_seen":None,
    }

def cli_generate(plan, email="", note=""):
    if plan not in PLANS:
        print(f"Unknown plan. Choose: {', '.join(PLANS)}"); sys.exit(1)
    db = load_db()
    key = new_key()
    db["keys"][key] = make_record(plan, email, note)
    save_db(db)
    p = PLANS[plan]
    print(f"\n{'='*54}\n  License key generated\n{'='*54}")
    print(f"  Key:    {key}")
    print(f"  Plan:   {p['label']}  |  Seats: {p['seats']}  |  ${p['price']}")
    if email: print(f"  Email:  {email}")
    print(f"{'='*54}\n")

def cli_list():
    db = load_db()
    if not db["keys"]:
        print("\nNo keys yet.\n"); return
    print(f"\n{'KEY':<26}{'PLAN':<17}{'SEATS':<7}{'ACTS':<6}{'STATUS':<9}EMAIL")
    print("-"*80)
    for key, d in db["keys"].items():
        acts = len(d.get("activations",[]))
        status = "ACTIVE" if d.get("active") else "REVOKED"
        print(f"{key:<26}{d['label']:<17}{d['seats']:<7}{acts}/{d['seats']:<4}{status:<9}{d.get('email','')[:25]}")
    print()

def cli_revoke(key):
    db = load_db()
    if key not in db["keys"]: print(f"Key not found: {key}"); return
    db["keys"][key]["active"] = False
    save_db(db)
    print(f"Revoked: {key}")

def run_server(port=8080):
    from flask import Flask, request, jsonify
    from flask_cors import CORS
    app = Flask(__name__)
    CORS(app)

    def now_str(): return datetime.now().isoformat()
    def expired(rec):
        e = rec.get("expires")
        return e and datetime.now() > datetime.fromisoformat(e)

    # ── Public endpoints (ClipForge app calls these) ──────────────────────────
    @app.route("/activate", methods=["POST"])
    def activate():
        d = request.get_json() or {}
        key = d.get("key","").strip().upper()
        mid = d.get("machine_id","")
        if not key or not mid:
            return jsonify({"valid":False,"message":"Missing key or machine ID"}), 400
        db = load_db()
        if key not in db["keys"]:
            return jsonify({"valid":False,"message":"License key not found. Check for typos or contact support@clipforgeai.com"}), 403
        rec = db["keys"][key]
        if not rec.get("active"):
            return jsonify({"valid":False,"message":"This key has been revoked. Contact support@clipforgeai.com"}), 403
        if expired(rec):
            return jsonify({"valid":False,"message":"License expired. Renew at clipforgeai.com"}), 403
        acts = rec.get("activations",[])
        seats = rec.get("seats",1)
        if mid in acts:
            rec["last_seen"] = now_str(); db["keys"][key]=rec; save_db(db)
            return jsonify({"valid":True,"plan":rec["plan"],"label":rec["label"],
                "seats":seats,"used":len(acts),"expires":rec.get("expires"),
                "message":f"Welcome back! {rec['label']} active."})
        if len(acts) >= seats:
            return jsonify({"valid":False,
                "message":f"All {seats} seat(s) in use. Email support@clipforgeai.com to transfer."}), 403
        acts.append(mid); rec["activations"]=acts; rec["last_seen"]=now_str()
        db["keys"][key]=rec; save_db(db)
        return jsonify({"valid":True,"plan":rec["plan"],"label":rec["label"],
            "seats":seats,"used":len(acts),"expires":rec.get("expires"),
            "message":f"Activated! {rec['label']} — {seats-len(acts)} seat(s) remaining."})

    @app.route("/check", methods=["POST"])
    def check():
        d = request.get_json() or {}
        key = d.get("key","").strip().upper()
        mid = d.get("machine_id","")
        db = load_db()
        if key not in db["keys"]: return jsonify({"valid":False,"message":"Key not found"})
        rec = db["keys"][key]
        if not rec.get("active"): return jsonify({"valid":False,"message":"License revoked"})
        if expired(rec): return jsonify({"valid":False,"message":"License expired — renew at clipforgeai.com"})
        if mid not in rec.get("activations",[]): return jsonify({"valid":False,"message":"Machine not registered"})
        rec["last_seen"]=now_str(); db["keys"][key]=rec; save_db(db)
        return jsonify({"valid":True,"plan":rec["plan"],"label":rec["label"],"expires":rec.get("expires")})

    @app.route("/deactivate", methods=["POST"])
    def deactivate():
        d = request.get_json() or {}
        key = d.get("key","").strip().upper(); mid = d.get("machine_id","")
        db = load_db()
        if key not in db["keys"]: return jsonify({"ok":False,"message":"Key not found"})
        rec = db["keys"][key]; acts = rec.get("activations",[])
        if mid in acts:
            acts.remove(mid); rec["activations"]=acts; db["keys"][key]=rec; save_db(db)
            return jsonify({"ok":True,"message":"Deactivated. You can now activate on a new machine."})
        return jsonify({"ok":False,"message":"Machine not found"})

    @app.route("/health")
    def health():
        db = load_db()
        return jsonify({"status":"ok","keys":len(db["keys"]),
            "active":sum(1 for k in db["keys"].values() if k.get("active"))})

    # ── Admin endpoints (dashboard calls these) ───────────────────────────────
    @app.route("/admin")
    def admin():
        if ADMIN_HTML.exists(): return ADMIN_HTML.read_text()
        return "<h1>Admin dashboard not found</h1>"

    @app.route("/admin/keys")
    def admin_keys():
        return jsonify({"keys": load_db()["keys"]})

    @app.route("/admin/generate", methods=["POST"])
    def admin_generate():
        d = request.get_json() or {}
        plan=d.get("plan","solo"); email=d.get("email",""); note=d.get("note","")
        if plan not in PLANS: return jsonify({"error":"Invalid plan"}), 400
        db = load_db(); key = new_key()
        rec = make_record(plan, email, note)
        db["keys"][key]=rec; save_db(db)
        return jsonify({"key":key,"data":rec})

    @app.route("/admin/revoke", methods=["POST"])
    def admin_revoke():
        key = (request.get_json() or {}).get("key","").strip().upper()
        db = load_db()
        if key not in db["keys"]: return jsonify({"ok":False}), 404
        db["keys"][key]["active"]=False; save_db(db)
        return jsonify({"ok":True})

    @app.route("/admin/restore", methods=["POST"])
    def admin_restore():
        key = (request.get_json() or {}).get("key","").strip().upper()
        db = load_db()
        if key not in db["keys"]: return jsonify({"ok":False}), 404
        db["keys"][key]["active"]=True; save_db(db)
        return jsonify({"ok":True})

    print(f"\n{'='*52}")
    print(f"  ClipForge License Server running")
    print(f"  Local:  http://localhost:{port}")
    print(f"  Admin:  http://localhost:{port}/admin")
    print(f"{'='*52}")
    print(f"  Keys in database: {len(load_db()['keys'])}")
    print(f"  Press Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    g = sub.add_parser("generate")
    g.add_argument("--plan", default="solo", choices=list(PLANS))
    g.add_argument("--email", default="")
    g.add_argument("--note", default="")
    sub.add_parser("list")
    r = sub.add_parser("revoke")
    r.add_argument("key")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8080)
    args = p.parse_args()
    if   args.cmd=="generate": cli_generate(args.plan, args.email, args.note)
    elif args.cmd=="list":     cli_list()
    elif args.cmd=="revoke":   cli_revoke(args.key)
    elif args.cmd=="serve":    run_server(args.port)
    else: p.print_help()
