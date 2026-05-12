#!/usr/bin/env python3
"""
ClipForge Update Server
========================
Host this alongside your license server (same Railway/Render instance).
This is what ClipForge checks on every startup to see if a new version exists.

Run: python3 update_server.py serve
Admin: http://localhost:8081/admin

HOW TO RELEASE A NEW VERSION:
  1. Make your changes to clipforge.py
  2. Run: python3 update_server.py publish --version 3.1.0 --file clipforge.py --notes "What changed"
  3. That's it — all buyers get the update on their next ClipForge launch

DEPLOY:
  Upload to same Railway/Render server as license_server.py
  Set env var: UPDATE_SECRET=your-secret-here
"""

import os, json, hashlib, shutil
from pathlib import Path
from datetime import datetime

STORAGE   = Path(__file__).parent / "update_storage"
STORAGE.mkdir(exist_ok=True)
MANIFEST  = STORAGE / "version.json"
SECRET    = os.environ.get("UPDATE_SECRET", "clipforge-update-secret")
PORT      = int(os.environ.get("UPDATE_PORT", 8081))

def file_hash(path):
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""): sha.update(chunk)
    return sha.hexdigest()

def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"version": "3.0.0", "released": None, "download_url": None, "notes": "Initial release"}

def cli_publish(version, filepath, notes="", base_url="http://localhost:8081"):
    src = Path(filepath)
    if not src.exists():
        print(f"File not found: {filepath}"); return

    # Validate Python syntax
    import ast
    try:
        ast.parse(src.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"Syntax error in file: {e}"); return

    # Copy to storage
    dest = STORAGE / f"clipforge_{version}.py"
    shutil.copy2(src, dest)

    # Generate manifest
    manifest = {
        "version":      version,
        "released":     datetime.now().isoformat(),
        "download_url": f"{base_url}/download/clipforge.py",
        "sha256":       file_hash(dest),
        "size_bytes":   dest.stat().st_size,
        "notes":        notes,
        "min_version":  "3.0.0",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))

    # Also save as latest
    shutil.copy2(dest, STORAGE / "clipforge.py")

    print(f"\n{'='*52}")
    print(f"  v{version} published")
    print(f"{'='*52}")
    print(f"  File:    {dest.name} ({dest.stat().st_size:,} bytes)")
    print(f"  Hash:    {manifest['sha256'][:32]}...")
    print(f"  Notes:   {notes}")
    print(f"\n  Buyers will get this update on next ClipForge launch.")
    print(f"  Rollback: python3 update_server.py rollback\n")

def cli_rollback():
    versions = sorted(STORAGE.glob("clipforge_*.py"))
    if len(versions) < 2:
        print("No previous version to rollback to."); return
    # Get second to last
    prev = versions[-2]
    shutil.copy2(prev, STORAGE / "clipforge.py")
    # Update manifest
    manifest = load_manifest()
    manifest["notes"] = f"[ROLLBACK] {manifest.get('notes','')}"
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f"Rolled back to: {prev.name}")

def cli_list():
    versions = sorted(STORAGE.glob("clipforge_*.py"), reverse=True)
    manifest = load_manifest()
    print(f"\n  Current version: {manifest.get('version','unknown')}")
    print(f"  Released: {manifest.get('released','never')}")
    print(f"  Notes: {manifest.get('notes','')}")
    print(f"\n  All versions stored ({len(versions)}):")
    for v in versions:
        size = v.stat().st_size
        mtime = datetime.fromtimestamp(v.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"    {v.name:<35} {size:>10,} bytes  {mtime}")
    print()

def run_server():
    from flask import Flask, send_file, jsonify, request
    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app)

    @app.route("/version.json")
    def version():
        """ClipForge app calls this on every startup"""
        manifest = load_manifest()
        return jsonify(manifest)

    @app.route("/download/clipforge.py")
    def download():
        """Serves the latest clipforge.py to updating clients"""
        latest = STORAGE / "clipforge.py"
        if not latest.exists():
            return jsonify({"error": "No version published yet"}), 404
        return send_file(str(latest), as_attachment=True, download_name="clipforge.py")

    @app.route("/health")
    def health():
        manifest = load_manifest()
        return jsonify({
            "status": "ok",
            "current_version": manifest.get("version"),
            "has_release": (STORAGE / "clipforge.py").exists(),
        })

    @app.route("/admin")
    def admin():
        manifest = load_manifest()
        versions = sorted(STORAGE.glob("clipforge_*.py"), reverse=True)
        rows = "".join(
            f"<tr><td style='font-family:monospace'>{v.name}</td>"
            f"<td>{v.stat().st_size:,} bytes</td>"
            f"<td>{datetime.fromtimestamp(v.stat().st_mtime).strftime('%Y-%m-%d %H:%M')}</td></tr>"
            for v in versions
        )
        return f"""<!DOCTYPE html>
<html>
<head><title>ClipForge Update Server</title>
<style>
  body{{font-family:-apple-system,sans-serif;background:#f5f4ef;color:#1a1a2e;padding:2rem;max-width:800px;margin:0 auto}}
  .card{{background:#fff;border:0.5px solid #e8e0c0;border-radius:12px;padding:1.5rem;margin-bottom:1rem}}
  .badge{{display:inline-block;background:#1a1a2e;color:#f0c040;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  td,th{{padding:8px 12px;border-bottom:0.5px solid #f0ead0;text-align:left}}
  th{{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#8892a4;background:#fafaf7}}
  h1{{font-size:22px;font-weight:800;margin-bottom:4px}}
  h2{{font-size:14px;font-weight:600;margin-bottom:1rem;color:#8892a4}}
</style>
</head>
<body>
  <h1>ClipForge Update Server</h1>
  <h2>Auto-update distribution for ClipForge AI</h2>
  <div class="card">
    <div style="margin-bottom:8px"><span class="badge">Current Version</span> <strong style="margin-left:8px;font-size:18px">{manifest.get('version','—')}</strong></div>
    <div style="font-size:13px;color:#8892a4;margin-bottom:4px">Released: {manifest.get('released','—')}</div>
    <div style="font-size:13px;color:#8892a4">Notes: {manifest.get('notes','—')}</div>
  </div>
  <div class="card">
    <table>
      <thead><tr><th>File</th><th>Size</th><th>Published</th></tr></thead>
      <tbody>{rows if rows else '<tr><td colspan=3 style="color:#8892a4;font-style:italic">No versions published yet</td></tr>'}</tbody>
    </table>
  </div>
  <div class="card" style="font-size:12px;color:#8892a4">
    <strong>To publish a new version:</strong><br>
    <code style="font-family:monospace;background:#f5f4ef;padding:2px 6px;border-radius:4px">python3 update_server.py publish --version 3.1.0 --file clipforge.py --notes "What changed"</code>
  </div>
</body></html>"""

    print(f"\n{'='*52}")
    print(f"  ClipForge Update Server")
    print(f"  http://localhost:{PORT}")
    print(f"  Admin: http://localhost:{PORT}/admin")
    print(f"{'='*52}")
    manifest = load_manifest()
    print(f"  Current version: {manifest.get('version')}")
    print(f"  Storage: {STORAGE}")
    print(f"\n  Press Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")

    pub = sub.add_parser("publish", help="Publish a new version")
    pub.add_argument("--version", required=True)
    pub.add_argument("--file", required=True, help="Path to clipforge.py")
    pub.add_argument("--notes", default="")
    pub.add_argument("--url", default="http://localhost:8081")

    sub.add_parser("rollback", help="Rollback to previous version")
    sub.add_parser("list", help="List all published versions")
    sub.add_parser("serve", help="Start the update server")

    args = p.parse_args()

    if   args.cmd == "publish":  cli_publish(args.version, args.file, args.notes, args.url)
    elif args.cmd == "rollback": cli_rollback()
    elif args.cmd == "list":     cli_list()
    elif args.cmd == "serve":    run_server()
    else: p.print_help()
