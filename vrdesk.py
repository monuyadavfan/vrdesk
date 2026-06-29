#!/usr/bin/env python3
"""
VrDesk V1.4 — Ultimate Edition
================================
Run: python vrdesk_v1.4.py
URL: http://localhost:8080
PIN: 1234

Install deps:
  pip install flask
  pip install yt-dlp          # video downloader
  pkg install p7zip unrar     # archive support
"""

from flask import Flask, request, jsonify, send_file, Response
import os, shutil, mimetypes, subprocess, json, hashlib
import zipfile, tarfile, re, signal, tempfile, threading, time
import base64, glob
from pathlib import Path
from datetime import datetime
from functools import wraps

app   = Flask(__name__)
app.secret_key = os.urandom(24)

ROOT    = os.path.expanduser("~")
VERSION = "1.4"

# HTML file path — same folder as this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE  = os.path.join(SCRIPT_DIR, "vrdesk.html")

CONFIG_FILE = os.path.join(ROOT, ".vrdesk_config.json")
TRASH_DIR   = os.path.join(ROOT, ".vrdesk_trash")
NOTES_FILE  = os.path.join(ROOT, ".vrdesk_notes.json")
RECENT_FILE = os.path.join(ROOT, ".vrdesk_recent.json")
TAGS_FILE   = os.path.join(ROOT, ".vrdesk_tags.json")
BM_FILE     = os.path.join(ROOT, ".vrdesk_bookmarks.json")
DL_DIR      = os.path.join(ROOT, "Downloads")

os.makedirs(TRASH_DIR, exist_ok=True)
os.makedirs(DL_DIR,    exist_ok=True)

DEFAULT_CFG = {
    "pin_hash":       hashlib.sha256(b"1234").hexdigest(),
    "login_required": True,
    "storage_lock":   False,
    "theme":          "dark",
    "autosave":       True,
    "ngrok_token":    "",
}

def load_cfg():
    try:
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CFG, **json.load(f)}
    except:
        return DEFAULT_CFG.copy()

def save_cfg(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

SESSIONS     = {}
BG_JOBS      = {}
HTTP_SERVERS = {}
TUNNEL_PROCS = {}
DL_PROGRESS  = {}

STORAGE_ROOTS = {
    "home":    ROOT,
    "storage": "/storage/emulated/0",
    "sdcard":  "/sdcard",
    "external":"/storage",
    "root":    "/",
}

def safe_path(rel):
    if not rel: return ROOT
    if rel.startswith("/"):
        return os.path.realpath(rel)
    return os.path.realpath(os.path.join(ROOT, rel))

def file_info(path):
    try:
        stat   = os.stat(path)
        name   = os.path.basename(path)
        is_dir = os.path.isdir(path)
        ext    = os.path.splitext(name)[1].lower() if not is_dir else ""
        mime   = mimetypes.guess_type(path)[0] or ""
        return {
            "name":     name,
            "path":     path,
            "is_dir":   is_dir,
            "size":     stat.st_size,
            "size_str": human_size(stat.st_size),
            "mtime":    datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "perms":    oct(stat.st_mode)[-3:],
            "ext":      ext,
            "mime":     mime,
            "is_image": mime.startswith("image/"),
            "is_video": mime.startswith("video/"),
            "is_audio": mime.startswith("audio/"),
            "is_pdf":   mime == "application/pdf",
        }
    except:
        return None

def human_size(b):
    for u in ["B","KB","MB","GB"]:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def add_recent(path):
    try:
        recent = []
        try:
            with open(RECENT_FILE) as f: recent = json.load(f)
        except: pass
        recent = [r for r in recent if r != path]
        recent.insert(0, path)
        with open(RECENT_FILE, "w") as f: json.dump(recent[:30], f)
    except: pass

def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        cfg = load_cfg()
        if not cfg.get("login_required", True):
            return f(*a, **kw)
        tok = request.cookies.get("vrd_tok","") or request.headers.get("X-VrDesk-Token","")
        if tok not in SESSIONS:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*a, **kw)
    return dec

def load_bookmarks():
    try:
        with open(BM_FILE) as f: return json.load(f)
    except:
        return [
            {"icon":"🏠","name":"Home",      "path": ROOT},
            {"icon":"📦","name":"Storage",   "path":"/storage/emulated/0"},
            {"icon":"⬇", "name":"Downloads","path":"/storage/emulated/0/Download"},
            {"icon":"📷","name":"DCIM",      "path":"/storage/emulated/0/DCIM"},
            {"icon":"🎵","name":"Music",     "path":"/storage/emulated/0/Music"},
            {"icon":"🎬","name":"Videos",    "path":"/storage/emulated/0/Movies"},
            {"icon":"🔧","name":"/usr",      "path":"/usr"},
            {"icon":"⚙", "name":"Termux",   "path":"/data/data/com.termux"},
        ]

def save_bookmarks(data):
    with open(BM_FILE, "w") as f: json.dump(data, f, ensure_ascii=False)

def load_tags():
    try:
        with open(TAGS_FILE) as f: return json.load(f)
    except: return {}

def save_tags(data):
    with open(TAGS_FILE, "w") as f: json.dump(data, f, ensure_ascii=False)

# ══════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════
@app.route("/api/login", methods=["POST"])
def api_login():
    cfg  = load_cfg()
    if not cfg.get("login_required", True):
        tok = "nologin_token"
        SESSIONS[tok] = True
        r = jsonify({"ok": True, "token": tok, "login_required": False})
        r.set_cookie("vrd_tok", tok, max_age=86400*7)
        return r
    data = request.get_json(silent=True) or {}
    pin  = data.get("pin", "")
    if hashlib.sha256(pin.encode()).hexdigest() == cfg["pin_hash"]:
        tok = hashlib.sha256(os.urandom(32)).hexdigest()
        SESSIONS[tok] = True
        r = jsonify({"ok": True, "token": tok})
        r.set_cookie("vrd_tok", tok, max_age=86400*7)
        return r
    return jsonify({"error": "Wrong PIN"}), 403

@app.route("/api/logout", methods=["POST"])
def api_logout():
    tok = request.cookies.get("vrd_tok","")
    SESSIONS.pop(tok, None)
    r = jsonify({"ok": True})
    r.delete_cookie("vrd_tok")
    return r

@app.route("/api/check_auth")
def api_check_auth():
    cfg = load_cfg()
    if not cfg.get("login_required", True):
        SESSIONS["nologin_token"] = True
        return jsonify({"ok": True, "login_required": False})
    tok = request.cookies.get("vrd_tok","") or request.headers.get("X-VrDesk-Token","")
    return jsonify({"ok": tok in SESSIONS, "login_required": True})

@app.route("/api/config", methods=["GET"])
@login_required
def api_config_get():
    cfg = load_cfg()
    return jsonify({k:v for k,v in cfg.items() if k != "pin_hash"})

@app.route("/api/config", methods=["POST"])
@login_required
def api_config_set():
    cfg  = load_cfg()
    data = request.get_json(silent=True) or {}
    for key in ["login_required","storage_lock","theme","autosave","ngrok_token"]:
        if key in data: cfg[key] = data[key]
    save_cfg(cfg)
    return jsonify({"ok": True})

@app.route("/api/change_pin", methods=["POST"])
@login_required
def api_change_pin():
    cfg  = load_cfg()
    data = request.get_json(silent=True) or {}
    old  = data.get("old_pin","")
    new  = data.get("new_pin","").strip()
    if hashlib.sha256(old.encode()).hexdigest() != cfg["pin_hash"]:
        return jsonify({"error": "Wrong current PIN"}), 403
    if len(new) < 4:
        return jsonify({"error": "PIN must be at least 4 digits"}), 400
    cfg["pin_hash"] = hashlib.sha256(new.encode()).hexdigest()
    save_cfg(cfg)
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════
# FILE SYSTEM
# ══════════════════════════════════════════════════
@app.route("/api/list")
@login_required
def api_list():
    path = safe_path(request.args.get("path","/"))
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Invalid path"}), 400
    try:
        items = []
        for name in sorted(os.listdir(path)):
            info = file_info(os.path.join(path, name))
            if info: items.append(info)
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        tags = load_tags()
        for item in items:
            item["tags"] = tags.get(item["path"], [])
        return jsonify({"items": items, "root": ROOT, "cwd": path})
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403

@app.route("/api/storage_roots")
@login_required
def api_storage_roots():
    roots = []
    for name, path in STORAGE_ROOTS.items():
        if os.path.exists(path):
            try:
                s = shutil.disk_usage(path)
                roots.append({"name":name,"path":path,
                    "total":human_size(s.total),"free":human_size(s.free),
                    "pct":round(s.used/s.total*100) if s.total else 0})
            except:
                roots.append({"name":name,"path":path})
    return jsonify({"roots": roots})

@app.route("/api/read")
@login_required
def api_read():
    path = safe_path(request.args.get("path",""))
    if not path or not os.path.isfile(path):
        return jsonify({"error": "Not a file"}), 400
    if os.path.getsize(path) > 10*1024*1024:
        return jsonify({"error": "File too large (>10MB)"}), 400
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        add_recent(path)
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/write", methods=["POST"])
@login_required
def api_write():
    data = request.get_json(silent=True) or {}
    path = safe_path(data.get("path",""))
    if not path: return jsonify({"error": "Invalid"}), 400
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data.get("content",""))
        add_recent(path)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/delete", methods=["POST"])
@login_required
def api_delete():
    data      = request.get_json(silent=True) or {}
    paths     = data.get("paths",[])
    permanent = data.get("permanent", False)
    if not paths:
        p = data.get("path","")
        paths = [p] if p else []
    errs = []
    for p in paths:
        path = safe_path(p)
        if not path: errs.append(p); continue
        try:
            if permanent:
                shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
            else:
                name = os.path.basename(path)
                ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                dst  = os.path.join(TRASH_DIR, f"{ts}__{name}")
                shutil.move(path, dst)
                with open(dst+".meta","w") as f:
                    json.dump({"original":path,"deleted":ts,"name":name}, f)
        except Exception as e:
            errs.append(str(e))
    return jsonify({"ok": not errs, "errors": errs})

@app.route("/api/trash")
@login_required
def api_trash():
    items = []
    for meta_f in glob.glob(os.path.join(TRASH_DIR,"*.meta")):
        try:
            with open(meta_f) as f: meta = json.load(f)
            tp = meta_f[:-5]
            if os.path.exists(tp):
                items.append({**meta,"trash_path":tp,
                    "size_str":human_size(os.path.getsize(tp) if os.path.isfile(tp) else 0)})
        except: pass
    items.sort(key=lambda x:x.get("deleted",""), reverse=True)
    return jsonify({"items": items})

@app.route("/api/trash/restore", methods=["POST"])
@login_required
def api_trash_restore():
    data       = request.get_json(silent=True) or {}
    trash_path = data.get("trash_path","")
    meta_f     = trash_path + ".meta"
    try:
        with open(meta_f) as f: meta = json.load(f)
        shutil.move(trash_path, meta["original"])
        os.remove(meta_f)
        return jsonify({"ok": True, "restored": meta["original"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/trash/clear", methods=["POST"])
@login_required
def api_trash_clear():
    try:
        shutil.rmtree(TRASH_DIR); os.makedirs(TRASH_DIR)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/rename", methods=["POST"])
@login_required
def api_rename():
    d   = request.get_json(silent=True) or {}
    src = safe_path(d.get("path",""))
    nn  = d.get("new_name","").strip()
    if not src or not nn: return jsonify({"error":"Invalid"}), 400
    try:
        os.rename(src, os.path.join(os.path.dirname(src), nn))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/bulk_rename", methods=["POST"])
@login_required
def api_bulk_rename():
    d       = request.get_json(silent=True) or {}
    paths   = d.get("paths",[])
    pattern = d.get("pattern","{name}")
    start   = int(d.get("start",1))
    renamed = []
    for i, p in enumerate(paths):
        path = safe_path(p)
        if not path or not os.path.exists(path): continue
        name = os.path.basename(path)
        stem = os.path.splitext(name)[0]
        ext  = os.path.splitext(name)[1]
        new_name = (pattern
            .replace("{name}", stem)
            .replace("{ext}", ext.lstrip("."))
            .replace("{n}", str(start+i).zfill(3)))
        if ext and not new_name.endswith(ext): new_name += ext
        dst = os.path.join(os.path.dirname(path), new_name)
        try:
            os.rename(path, dst)
            renamed.append({"from":name,"to":new_name})
        except Exception as e:
            renamed.append({"from":name,"error":str(e)})
    return jsonify({"ok": True, "renamed": renamed})

@app.route("/api/move", methods=["POST"])
@login_required
def api_move():
    d   = request.get_json(silent=True) or {}
    src = safe_path(d.get("src",""))
    dst = safe_path(d.get("dst_dir",""))
    if not src or not dst: return jsonify({"error":"Invalid"}), 400
    try:
        shutil.move(src, os.path.join(dst, os.path.basename(src)))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/copy", methods=["POST"])
@login_required
def api_copy():
    d   = request.get_json(silent=True) or {}
    src = safe_path(d.get("src",""))
    dst = safe_path(d.get("dst_dir",""))
    if not src or not dst: return jsonify({"error":"Invalid"}), 400
    try:
        out = os.path.join(dst, os.path.basename(src))
        shutil.copytree(src,out) if os.path.isdir(src) else shutil.copy2(src,out)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/mkdir", methods=["POST"])
@login_required
def api_mkdir():
    d = request.get_json(silent=True) or {}
    p = safe_path(d.get("path",""))
    n = d.get("name","").strip()
    if not p or not n: return jsonify({"error":"Invalid"}), 400
    try:
        os.makedirs(os.path.join(p,n), exist_ok=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/touch", methods=["POST"])
@login_required
def api_touch():
    d = request.get_json(silent=True) or {}
    p = safe_path(d.get("path",""))
    n = d.get("name","").strip()
    if not p or not n: return jsonify({"error":"Invalid"}), 400
    try:
        Path(os.path.join(p,n)).touch()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/download")
@login_required
def api_download():
    path = safe_path(request.args.get("path",""))
    if not path or not os.path.isfile(path):
        return jsonify({"error":"Not found"}), 404
    return send_file(path, as_attachment=True)

@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    dst = safe_path(request.form.get("path","/"))
    if not dst: return jsonify({"error":"Invalid"}), 400
    saved = []
    for f in request.files.getlist("files"):
        dest = os.path.join(dst, f.filename)
        f.save(dest); saved.append(f.filename)
        add_recent(dest)
    return jsonify({"ok": True, "saved": saved})

@app.route("/api/search")
@login_required
def api_search():
    q       = request.args.get("q","").strip().lower()
    start   = safe_path(request.args.get("path","/"))
    content = request.args.get("content","false") == "true"
    if not q or not start: return jsonify({"results":[]})
    results = []
    try:
        for rd, dirs, files in os.walk(start):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in dirs+files:
                if q in name.lower():
                    info = file_info(os.path.join(rd, name))
                    if info: results.append(info)
            if content:
                for name in files:
                    full = os.path.join(rd, name)
                    try:
                        with open(full,"r",encoding="utf-8",errors="ignore") as fh:
                            for i, line in enumerate(fh, 1):
                                if q in line.lower():
                                    info = file_info(full)
                                    if info:
                                        info["match_line"] = i
                                        info["match_text"] = line.strip()[:120]
                                        results.append(info)
                                    break
                    except: pass
            if len(results) >= 200: break
    except: pass
    return jsonify({"results": results})

@app.route("/api/storage")
@login_required
def api_storage():
    try:
        s   = shutil.disk_usage(ROOT)
        pct = round(s.used/s.total*100) if s.total else 0
        return jsonify({"total":s.total,"used":s.used,"free":s.free,
            "total_str":human_size(s.total),"used_str":human_size(s.used),
            "free_str":human_size(s.free),"pct":pct})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/storage_analytics")
@login_required
def api_storage_analytics():
    path = safe_path(request.args.get("path", ROOT))
    results = []
    try:
        for name in os.listdir(path):
            full = os.path.join(path, name)
            try:
                if os.path.isdir(full):
                    size = sum(os.path.getsize(os.path.join(dp,f))
                               for dp,_,fs in os.walk(full)
                               for f in fs if os.path.isfile(os.path.join(dp,f)))
                else:
                    size = os.path.getsize(full)
                results.append({"name":name,"size":size,"size_str":human_size(size),"is_dir":os.path.isdir(full)})
            except: pass
        results.sort(key=lambda x:x["size"], reverse=True)
        return jsonify({"items": results[:20]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/props")
@login_required
def api_props():
    path = safe_path(request.args.get("path",""))
    if not path: return jsonify({"error":"Invalid"}), 400
    try:
        stat = os.stat(path)
        info = file_info(path)
        info.update({
            "atime": datetime.fromtimestamp(stat.st_atime).strftime("%Y-%m-%d %H:%M:%S"),
            "ctime": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            "inode": stat.st_ino, "uid": stat.st_uid, "gid": stat.st_gid,
            "mode":  oct(stat.st_mode)
        })
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chmod", methods=["POST"])
@login_required
def api_chmod():
    d    = request.get_json(silent=True) or {}
    path = safe_path(d.get("path",""))
    mode = d.get("mode","")
    if not path or not re.match(r"^[0-7]{3}$", mode):
        return jsonify({"error":"Invalid"}), 400
    try:
        os.chmod(path, int(mode,8))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/compress", methods=["POST"])
@login_required
def api_compress():
    d     = request.get_json(silent=True) or {}
    paths = d.get("paths",[])
    dest  = safe_path(d.get("dest","/"))
    name  = d.get("name","archive.zip")
    if not dest or not paths: return jsonify({"error":"Invalid"}), 400
    out = os.path.join(dest, name if name.endswith(".zip") else name+".zip")
    try:
        with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as zf:
            for rel in paths:
                p = safe_path(rel)
                if not p: continue
                if os.path.isdir(p):
                    for rd,_,files in os.walk(p):
                        for f in files:
                            fp = os.path.join(rd,f)
                            zf.write(fp, os.path.relpath(fp, os.path.dirname(p)))
                else:
                    zf.write(p, os.path.basename(p))
        return jsonify({"ok": True, "out": out})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/extract", methods=["POST"])
@login_required
def api_extract():
    d    = request.get_json(silent=True) or {}
    path = safe_path(d.get("path",""))
    dest = safe_path(d.get("dest","/"))
    if not path or not dest: return jsonify({"error":"Invalid"}), 400
    try:
        n = path.lower()
        if n.endswith(".zip"):
            with zipfile.ZipFile(path) as zf: zf.extractall(dest)
        elif any(n.endswith(x) for x in [".tar.gz",".tgz",".tar.bz2",".tar.xz",".tar"]):
            with tarfile.open(path) as tf: tf.extractall(dest)
        elif n.endswith(".tar.zst"):
            subprocess.run(f"tar --zstd -xf '{path}' -C '{dest}'", shell=True, check=True)
        elif n.endswith(".7z"):
            r2 = subprocess.run(f"7z x '{path}' -o'{dest}' -y", shell=True, capture_output=True, text=True)
            if r2.returncode != 0: return jsonify({"error":"pkg install p7zip"}), 400
        elif n.endswith(".rar"):
            r2 = subprocess.run(f"unrar x -y '{path}' '{dest}'", shell=True, capture_output=True, text=True)
            if r2.returncode != 0: return jsonify({"error":"pkg install unrar"}), 400
        else:
            return jsonify({"error":"Unsupported format"}), 400
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/preview")
@login_required
def api_preview():
    path = safe_path(request.args.get("path",""))
    if not path or not os.path.isfile(path):
        return jsonify({"error":"Not found"}), 404
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return send_file(path, mimetype=mime)

# ══════════════════════════════════════════════════
# CODE RUNNER
# ══════════════════════════════════════════════════
def detect_imports(code):
    stdlib = {"os","sys","re","json","time","datetime","math","random","string",
              "pathlib","subprocess","threading","collections","itertools","functools",
              "hashlib","base64","io","tempfile","shutil","zipfile","tarfile",
              "http","urllib","email","html","xml","csv","sqlite3","logging",
              "argparse","typing","dataclasses","abc","enum","copy","pprint","ast"}
    found   = re.findall(r"^(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)", code, re.MULTILINE)
    return [m for m in set(found) if m not in stdlib]

@app.route("/api/run", methods=["POST"])
@login_required
def api_run():
    d        = request.get_json(silent=True) or {}
    path     = safe_path(d.get("path","")) if d.get("path") else None
    code     = d.get("code","")
    run_type = d.get("type","auto")
    stdin_d  = d.get("stdin","")
    timeout  = int(d.get("timeout", 60))
    bg       = d.get("background", False)
    args     = d.get("args","")

    if path and os.path.isfile(path) and not code:
        with open(path,"r",encoding="utf-8",errors="replace") as f: code=f.read()
        ext = os.path.splitext(path)[1].lower()
        if run_type == "auto":
            run_type = {"py":"python","js":"node","sh":"shell","bash":"shell"}.get(ext.lstrip("."),"python")
    elif run_type == "auto":
        run_type = "python"

    if run_type == "html": return jsonify({"ok":True,"html":code,"type":"html"})

    missing = detect_imports(code) if run_type == "python" else []
    suffix  = {"python":".py","node":".js","shell":".sh"}.get(run_type,".py")
    tf_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w",suffix=suffix,delete=False,encoding="utf-8") as tf:
            tf.write(code); tf_path = tf.name
        if run_type == "shell":
            os.chmod(tf_path, 0o755)
            cmd = ["/bin/bash", tf_path] + (args.split() if args else [])
        elif run_type == "node":
            cmd = ["node", tf_path] + (args.split() if args else [])
        else:
            cmd = ["python3", tf_path] + (args.split() if args else [])

        cwd_run = os.path.dirname(path) if path else ROOT

        if bg:
            jid = hashlib.sha256(os.urandom(8)).hexdigest()[:8]
            def run_bg():
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                      input=stdin_d, cwd=cwd_run)
                BG_JOBS[jid].update({"done":True,"stdout":proc.stdout,
                                     "stderr":proc.stderr,"returncode":proc.returncode})
            BG_JOBS[jid] = {"done":False,"stdout":"","stderr":"","returncode":None}
            threading.Thread(target=run_bg, daemon=True).start()
            return jsonify({"ok":True,"background":True,"job_id":jid,"type":"bg"})

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              input=stdin_d, cwd=cwd_run)
        return jsonify({"ok":True,"stdout":proc.stdout,"stderr":proc.stderr,
                        "returncode":proc.returncode,"type":"text","missing_pkgs":missing})
    except subprocess.TimeoutExpired:
        return jsonify({"ok":False,"error":f"Timeout ({timeout}s) — use BG mode","type":"text","missing_pkgs":missing})
    except FileNotFoundError as e:
        return jsonify({"ok":False,"error":str(e)+" — interpreter not found","type":"text"})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e),"type":"text"})
    finally:
        if tf_path:
            try: os.unlink(tf_path)
            except: pass

@app.route("/api/job/<job_id>")
@login_required
def api_job(job_id):
    job = BG_JOBS.get(job_id)
    if not job: return jsonify({"error":"Not found"}), 404
    return jsonify(job)

@app.route("/api/terminal", methods=["POST"])
@login_required
def api_terminal():
    d   = request.get_json(silent=True) or {}
    cmd = d.get("cmd","").strip()
    cwd = safe_path(d.get("cwd", ROOT)) or ROOT
    if not cmd: return jsonify({"output":""})
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd=cwd)
        return jsonify({"output": proc.stdout+proc.stderr, "returncode": proc.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({"output":"Timeout (60s)","returncode":-1})
    except Exception as e:
        return jsonify({"output": str(e), "returncode":-1})

@app.route("/api/log_tail")
@login_required
def api_log_tail():
    path  = safe_path(request.args.get("path",""))
    lines = int(request.args.get("lines", 50))
    if not path or not os.path.isfile(path):
        return jsonify({"error":"Not found"}), 404
    try:
        proc = subprocess.run(f"tail -n {lines} '{path}'", shell=True, capture_output=True, text=True)
        return jsonify({"content": proc.stdout})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/sysinfo")
@login_required
def api_sysinfo():
    try:
        cpu  = subprocess.run("top -bn1 | grep 'Cpu' | awk '{print $2}'", shell=True, capture_output=True, text=True).stdout.strip()
        mem  = subprocess.run("free -m | awk 'NR==2{printf \"%s %s\",$3,$2}'", shell=True, capture_output=True, text=True).stdout.strip()
        upt  = subprocess.run("uptime -p", shell=True, capture_output=True, text=True).stdout.strip()
        disk = shutil.disk_usage(ROOT)
        mem_parts = mem.split() if mem else ["0","1"]
        used_m  = int(mem_parts[0]) if mem_parts else 0
        total_m = int(mem_parts[1]) if len(mem_parts)>1 else 1
        cpu_val = 0
        m = re.findall(r"[\d.]+", cpu)
        if m: cpu_val = float(m[0])
        return jsonify({
            "cpu_pct":   cpu_val,
            "mem_used":  used_m, "mem_total": total_m,
            "mem_pct":   round(used_m/total_m*100) if total_m else 0,
            "uptime":    upt,
            "disk_pct":  round(disk.used/disk.total*100) if disk.total else 0,
            "disk_free": human_size(disk.free),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/processes")
@login_required
def api_processes():
    try:
        proc = subprocess.run("ps aux --no-header 2>/dev/null || ps aux",
                              shell=True, capture_output=True, text=True, timeout=5)
        procs = []
        for line in proc.stdout.strip().split("\n")[:60]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                procs.append({"pid":parts[1],"cpu":parts[2],"mem":parts[3],"cmd":parts[10]})
        return jsonify({"processes": procs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/kill", methods=["POST"])
@login_required
def api_kill():
    pid = str((request.get_json(silent=True) or {}).get("pid",""))
    if not pid.isdigit(): return jsonify({"error":"Invalid"}), 400
    try:
        os.kill(int(pid), signal.SIGTERM)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ══════════════════════════════════════════════════
# DOWNLOAD MANAGER
# ══════════════════════════════════════════════════
@app.route("/api/dl_start", methods=["POST"])
@login_required
def api_dl_start():
    d          = request.get_json(silent=True) or {}
    url        = d.get("url","").strip()
    dest       = safe_path(d.get("dest", DL_DIR))
    quality    = d.get("quality","best")
    audio_only = d.get("audio_only", False)
    if not url: return jsonify({"error":"No URL"}), 400

    jid = hashlib.sha256(os.urandom(8)).hexdigest()[:8]
    DL_PROGRESS[jid] = {"status":"starting","percent":0,"speed":"","filename":"","error":"","done":False}

    def do_dl():
        try:
            fmt = "-x --audio-format mp3" if audio_only else (
                f"-f 'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best'"
                if quality.isdigit() else "-f best")
            cmd = f"yt-dlp {fmt} --newline -o '{dest}/%(title)s.%(ext)s' '{url}' 2>&1"
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                line = line.strip()
                pct  = re.search(r"(\d+\.?\d*)%", line)
                spd  = re.search(r"at\s+([\d.]+\s*\w+/s)", line)
                fn   = re.search(r"\[download\] Destination: (.+)", line)
                if pct:  DL_PROGRESS[jid]["percent"]  = float(pct.group(1))
                if spd:  DL_PROGRESS[jid]["speed"]    = spd.group(1)
                if fn:   DL_PROGRESS[jid]["filename"] = os.path.basename(fn.group(1))
                DL_PROGRESS[jid]["status"] = "downloading"
            proc.wait()
            if proc.returncode == 0:
                DL_PROGRESS[jid].update({"done":True,"status":"done","percent":100})
            else:
                fname = url.split("/")[-1].split("?")[0] or "download"
                dest_file = os.path.join(dest, fname)
                r2 = subprocess.run(f"wget -O '{dest_file}' '{url}'",
                                    shell=True, capture_output=True, text=True, timeout=300)
                if r2.returncode == 0:
                    DL_PROGRESS[jid].update({"done":True,"status":"done","percent":100,"filename":fname})
                else:
                    DL_PROGRESS[jid].update({"done":True,"status":"error","error":r2.stderr[:200]})
        except Exception as e:
            DL_PROGRESS[jid].update({"done":True,"status":"error","error":str(e)})

    threading.Thread(target=do_dl, daemon=True).start()
    return jsonify({"ok": True, "job_id": jid})

@app.route("/api/dl_status/<jid>")
@login_required
def api_dl_status(jid):
    return jsonify(DL_PROGRESS.get(jid, {"error":"Not found"}))

# ══════════════════════════════════════════════════
# HTTP SERVER / TUNNEL
# ══════════════════════════════════════════════════
@app.route("/api/httpserver/start", methods=["POST"])
@login_required
def api_httpserver_start():
    d    = request.get_json(silent=True) or {}
    path = safe_path(d.get("path", ROOT))
    port = int(d.get("port", 8081))
    if port in HTTP_SERVERS:
        return jsonify({"error":"Already running on port "+str(port)}), 400
    try:
        import socket
        ip = socket.gethostbyname(socket.gethostname())
    except: ip = "127.0.0.1"
    proc = subprocess.Popen(f"python3 -m http.server {port}", shell=True, cwd=path,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    HTTP_SERVERS[port] = proc
    return jsonify({"ok":True,"url":f"http://{ip}:{port}","port":port})

@app.route("/api/httpserver/stop", methods=["POST"])
@login_required
def api_httpserver_stop():
    port = int((request.get_json(silent=True) or {}).get("port", 8081))
    proc = HTTP_SERVERS.pop(port, None)
    if proc: proc.terminate()
    return jsonify({"ok": True})

@app.route("/api/tunnel/start", methods=["POST"])
@login_required
def api_tunnel_start():
    d       = request.get_json(silent=True) or {}
    service = d.get("service","cloudflared")
    port    = int(d.get("port", 8080))
    cfg     = load_cfg()

    if service in TUNNEL_PROCS:
        try: TUNNEL_PROCS[service].terminate()
        except: pass

    try:
        if service == "cloudflared":
            which = subprocess.run("which cloudflared", shell=True, capture_output=True, text=True)
            if not which.stdout.strip():
                subprocess.run(
                    "pkg install cloudflared -y 2>&1 || "
                    "(wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 "
                    "-O $PREFIX/bin/cloudflared && chmod +x $PREFIX/bin/cloudflared)",
                    shell=True, capture_output=True, text=True, timeout=60)

            proc = subprocess.Popen(
                f"cloudflared tunnel --url http://localhost:{port}",
                shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            TUNNEL_PROCS[service] = proc

            url = ""
            for _ in range(40):
                line = proc.stdout.readline()
                m = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
                if m: url = m.group(0); break
                time.sleep(0.5)

            return jsonify({"ok":bool(url),"url":url or "Starting… retry in a moment","service":"cloudflared"})

        elif service == "ngrok":
            token = cfg.get("ngrok_token","")
            if not token:
                return jsonify({"error":"ngrok auth token required","need_token":True}), 400
            which = subprocess.run("which ngrok", shell=True, capture_output=True, text=True)
            if not which.stdout.strip():
                return jsonify({"error":"ngrok not installed. pkg install ngrok","need_install":True}), 400
            subprocess.run(f"ngrok config add-authtoken {token}", shell=True, capture_output=True)
            proc = subprocess.Popen(f"ngrok http {port}", shell=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            TUNNEL_PROCS[service] = proc
            time.sleep(3)
            try:
                import urllib.request
                resp = urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=5)
                data = json.loads(resp.read())
                url  = data["tunnels"][0]["public_url"]
                return jsonify({"ok":True,"url":url,"service":"ngrok"})
            except:
                return jsonify({"ok":True,"url":"http://localhost:4040","service":"ngrok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/tunnel/stop", methods=["POST"])
@login_required
def api_tunnel_stop():
    service = (request.get_json(silent=True) or {}).get("service","cloudflared")
    proc = TUNNEL_PROCS.pop(service, None)
    if proc:
        try: proc.terminate()
        except: pass
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════
# MISC APIS
# ══════════════════════════════════════════════════
@app.route("/api/tags", methods=["GET"])
@login_required
def api_tags_get():
    return jsonify(load_tags())

@app.route("/api/tags", methods=["POST"])
@login_required
def api_tags_set():
    d    = request.get_json(silent=True) or {}
    path = d.get("path","")
    tags = d.get("tags",[])
    data = load_tags()
    if tags: data[path] = tags
    else:    data.pop(path, None)
    save_tags(data)
    return jsonify({"ok": True})

@app.route("/api/recent")
@login_required
def api_recent():
    try:
        with open(RECENT_FILE) as f: recent = json.load(f)
        items = []
        for p in recent[:20]:
            if os.path.exists(p):
                info = file_info(p)
                if info: items.append(info)
        return jsonify({"items": items})
    except:
        return jsonify({"items": []})

@app.route("/api/notes", methods=["GET"])
@login_required
def api_notes_get():
    try:
        with open(NOTES_FILE) as f: return jsonify(json.load(f))
    except: return jsonify({"notes": []})

@app.route("/api/notes", methods=["POST"])
@login_required
def api_notes_set():
    data = request.get_json(silent=True) or {}
    with open(NOTES_FILE,"w") as f: json.dump(data, f, ensure_ascii=False)
    return jsonify({"ok": True})

@app.route("/api/cron", methods=["GET"])
@login_required
def api_cron_get():
    try:
        proc = subprocess.run("crontab -l", shell=True, capture_output=True, text=True)
        return jsonify({"crontab": proc.stdout, "error": proc.stderr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cron", methods=["POST"])
@login_required
def api_cron_set():
    d = request.get_json(silent=True) or {}
    cron = d.get("crontab","")
    try:
        with tempfile.NamedTemporaryFile(mode="w",suffix=".cron",delete=False) as tf:
            tf.write(cron); tf_path=tf.name
        subprocess.run(f"crontab {tf_path}", shell=True, check=True)
        os.unlink(tf_path)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/encrypt", methods=["POST"])
@login_required
def api_encrypt():
    d    = request.get_json(silent=True) or {}
    path = safe_path(d.get("path",""))
    pwd  = d.get("password","")
    if not path or not pwd: return jsonify({"error":"Invalid"}), 400
    try:
        proc = subprocess.run(
            f"openssl enc -aes-256-cbc -pbkdf2 -in '{path}' -out '{path}.enc' -k '{pwd}'",
            shell=True, capture_output=True, text=True)
        if proc.returncode == 0:
            os.remove(path)
            return jsonify({"ok":True,"out":path+".enc"})
        return jsonify({"error": proc.stderr}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/decrypt", methods=["POST"])
@login_required
def api_decrypt():
    d    = request.get_json(silent=True) or {}
    path = safe_path(d.get("path",""))
    pwd  = d.get("password","")
    out  = path[:-4] if path.endswith(".enc") else path+"_dec"
    try:
        proc = subprocess.run(
            f"openssl enc -aes-256-cbc -pbkdf2 -d -in '{path}' -out '{out}' -k '{pwd}'",
            shell=True, capture_output=True, text=True)
        if proc.returncode == 0:
            return jsonify({"ok":True,"out":out})
        return jsonify({"error":"Wrong password or corrupted file"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pkg", methods=["POST"])
@login_required
def api_pkg():
    d      = request.get_json(silent=True) or {}
    mgr    = d.get("mgr","pip")
    action = d.get("action","install")
    pkg    = d.get("pkg","").strip()
    if not pkg: return jsonify({"error":"No package"}), 400
    cmds = {
        "pip": {"install":f"pip install {pkg} --break-system-packages","uninstall":f"pip uninstall -y {pkg}","list":"pip list"},
        "apt": {"install":f"apt install -y {pkg}","uninstall":f"apt remove -y {pkg}","list":"apt list --installed 2>/dev/null"},
        "npm": {"install":f"npm install -g {pkg}","uninstall":f"npm uninstall -g {pkg}","list":"npm list -g --depth=0"},
    }
    cmd = cmds.get(mgr,{}).get(action)
    if not cmd: return jsonify({"error":"Invalid"}), 400
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180)
        return jsonify({"ok":proc.returncode==0,"output":proc.stdout+proc.stderr})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500

@app.route("/api/git", methods=["POST"])
@login_required
def api_git():
    d   = request.get_json(silent=True) or {}
    cmd = d.get("cmd","status")
    cwd = safe_path(d.get("path", ROOT)) or ROOT
    allowed = ["status","log --oneline","diff","branch","pull","fetch","stash","clone","init","remote","add","commit"]
    if not any(cmd.startswith(a) for a in allowed):
        return jsonify({"error":"Not allowed"}), 403
    try:
        proc = subprocess.run(f"git {cmd}", shell=True, capture_output=True,
                              text=True, timeout=120, cwd=cwd)
        return jsonify({"output":proc.stdout+proc.stderr,"returncode":proc.returncode})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/git/clone", methods=["POST"])
@login_required
def api_git_clone():
    d    = request.get_json(silent=True) or {}
    url  = d.get("url","").strip()
    dest = safe_path(d.get("dest", ROOT)) or ROOT
    name = d.get("name","").strip()
    if not url: return jsonify({"error":"No URL"}), 400
    cmd = f"git clone {url}" + (f" {name}" if name else "")
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=300, cwd=dest)
        return jsonify({"ok":proc.returncode==0,"output":proc.stdout+proc.stderr})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}), 500

@app.route("/api/bookmarks")
@login_required
def api_bookmarks_get():
    return jsonify({"bookmarks": load_bookmarks()})

@app.route("/api/bookmarks", methods=["POST"])
@login_required
def api_bookmarks_set():
    bm = (request.get_json(silent=True) or {}).get("bookmarks")
    if bm is None: return jsonify({"error":"No data"}), 400
    save_bookmarks(bm)
    return jsonify({"ok": True})

@app.route("/api/share")
@login_required
def api_share():
    path = safe_path(request.args.get("path",""))
    if not path or not os.path.isfile(path):
        return jsonify({"error":"Not found"}), 404
    try:
        subprocess.Popen(["termux-share", path])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/qr")
@login_required
def api_qr():
    text = request.args.get("text","")
    if not text: return jsonify({"error":"No text"}), 400
    return jsonify({"ok":True,"qr_url":f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={text}"})

# ══════════════════════════════════════════════════
# SERVE HTML
# ══════════════════════════════════════════════════
@app.route("/")
def index():
    if os.path.exists(HTML_FILE):
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html")
    return Response("""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:40px;background:#0f0f13;color:#f0f0f5">
        <h2 style="color:#a78bfa">⚠ VrDesk V1.4</h2>
        <p>Frontend file not found!</p>
        <p>Make sure <code>vrdesk_v1.4.html</code> is in the same folder as this script.</p>
        <p style="color:#9090aa">Expected: """ + HTML_FILE + """</p>
        </body></html>""", mimetype="text/html")

if __name__ == "__main__":
    print(f"\n{'═'*50}")
    print(f"  VrDesk V{VERSION} — Ultimate Edition")
    print(f"{'═'*50}")
    print(f"  URL     : http://localhost:8080")
    print(f"  HTML    : {HTML_FILE}")
    print(f"  PIN     : 1234 (change in Settings)")
    print(f"{'═'*50}")
    print(f"  Optional installs:")
    print(f"  pip install yt-dlp")
    print(f"  pkg install p7zip unrar cloudflared")
    print(f"{'═'*50}\n")
    app.run(host="0.0.0.0", port=8080, debug=False)
