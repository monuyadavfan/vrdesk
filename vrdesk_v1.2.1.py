#!/usr/bin/env python3
"""
 ██╗   ██╗██████╗ ██████╗ ███████╗███████╗██╗  ██╗
 ██║   ██║██╔══██╗██╔══██╗██╔════╝██╔════╝██║ ██╔╝
 ██║   ██║██████╔╝██║  ██║█████╗  ███████╗█████╔╝
 ╚██╗ ██╔╝██╔══██╗██║  ██║██╔══╝  ╚════██║██╔═██╗
  ╚████╔╝ ██║  ██║██████╔╝███████╗███████║██║  ██╗
   ╚═══╝  ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝
  V1.2 — Hacker Edition
  ─────────────────────────────────────────────────
  Install : pip install flask
  Run     : python vrdesk_v1.2.py
  Open    : http://localhost:8080
  PIN     : 1234  (change PIN_HASH below)
"""

from flask import Flask, request, jsonify, send_file, Response
import os, shutil, mimetypes, subprocess, json, hashlib
import zipfile, tarfile, re, signal, tempfile
from pathlib import Path
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)

ROOT     = os.path.expanduser("~")
VERSION  = "1.2"
PIN_HASH = hashlib.sha256(b"1234").hexdigest()
SESSIONS = {}

BOOKMARKS_FILE = os.path.join(ROOT, ".vrdesk_bookmarks.json")
DEFAULT_BOOKMARKS = [
    {"icon":"🏠","name":"Home",      "path":"/"},
    {"icon":"📦","name":"Storage",   "path":"/storage/emulated/0"},
    {"icon":"⬇", "name":"Downloads","path":"/storage/emulated/0/Download"},
    {"icon":"📷","name":"DCIM",      "path":"/storage/emulated/0/DCIM"},
    {"icon":"🔧","name":"/usr",      "path":"/usr"},
    {"icon":"⚙", "name":"Termux",   "path":"/data/data/com.termux"},
    {"icon":"💨","name":"/tmp",      "path":"/tmp"},
]

# ── Helpers ────────────────────────────────────────────────────────────────────
def safe_path(rel):
    if not rel: return ROOT
    path = os.path.realpath(os.path.join(ROOT, rel.lstrip("/")))
    if not path.startswith(ROOT): return None
    return path

def file_info(path):
    try:
        stat   = os.stat(path)
        name   = os.path.basename(path)
        is_dir = os.path.isdir(path)
        ext    = os.path.splitext(name)[1].lower() if not is_dir else ""
        return {
            "name":     name,
            "path":     path.replace(ROOT,"",1) or "/",
            "is_dir":   is_dir,
            "size":     stat.st_size,
            "size_str": human_size(stat.st_size),
            "mtime":    datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "perms":    oct(stat.st_mode)[-3:],
            "ext":      ext,
            "mime":     mimetypes.guess_type(path)[0] or "",
        }
    except: return None

def human_size(b):
    for u in ["B","KB","MB","GB"]:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def login_required(f):
    @wraps(f)
    def dec(*a,**kw):
        tok = request.cookies.get("vrd_tok") or request.headers.get("X-VrDesk-Token")
        if tok not in SESSIONS: return jsonify({"error":"Unauthorized"}),401
        return f(*a,**kw)
    return dec

def load_bookmarks():
    try:
        with open(BOOKMARKS_FILE) as f: return json.load(f)
    except: return DEFAULT_BOOKMARKS[:]

def save_bookmarks(data):
    with open(BOOKMARKS_FILE,"w") as f: json.dump(data,f,ensure_ascii=False)

# ── Auth ───────────────────────────────────────────────────────────────────────
@app.route("/api/login",methods=["POST"])
def api_login():
    pin = request.json.get("pin","")
    if hashlib.sha256(pin.encode()).hexdigest() == PIN_HASH:
        tok = hashlib.sha256(os.urandom(32)).hexdigest()
        SESSIONS[tok] = True
        r = jsonify({"ok":True,"token":tok})
        r.set_cookie("vrd_tok",tok,max_age=86400*7)
        return r
    return jsonify({"error":"Wrong PIN"}),403

@app.route("/api/logout",methods=["POST"])
def api_logout():
    tok = request.cookies.get("vrd_tok")
    SESSIONS.pop(tok,None)
    r = jsonify({"ok":True})
    r.delete_cookie("vrd_tok")
    return r

@app.route("/api/check_auth")
def api_check_auth():
    tok = request.cookies.get("vrd_tok") or request.headers.get("X-VrDesk-Token")
    return jsonify({"ok": tok in SESSIONS})

# ── File System ────────────────────────────────────────────────────────────────
@app.route("/api/list")
@login_required
def api_list():
    rel  = request.args.get("path","/")
    path = safe_path(rel)
    if not path or not os.path.isdir(path):
        return jsonify({"error":"Invalid path"}),400
    try:
        items = []
        for name in sorted(os.listdir(path)):
            info = file_info(os.path.join(path,name))
            if info: items.append(info)
        items.sort(key=lambda x:(not x["is_dir"],x["name"].lower()))
        return jsonify({"items":items,"root":ROOT})
    except PermissionError:
        return jsonify({"error":"Permission denied"}),403

@app.route("/api/read")
@login_required
def api_read():
    path = safe_path(request.args.get("path",""))
    if not path or not os.path.isfile(path):
        return jsonify({"error":"Not a file"}),400
    if os.path.getsize(path) > 5*1024*1024:
        return jsonify({"error":"File too large (>5MB)"}),400
    try:
        with open(path,"r",encoding="utf-8",errors="replace") as f:
            return jsonify({"content":f.read()})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/write",methods=["POST"])
@login_required
def api_write():
    data = request.json
    path = safe_path(data.get("path",""))
    if not path: return jsonify({"error":"Invalid"}),400
    try:
        with open(path,"w",encoding="utf-8") as f: f.write(data.get("content",""))
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/delete",methods=["POST"])
@login_required
def api_delete():
    paths = request.json.get("paths",[])
    if not paths:
        p = request.json.get("path","")
        paths = [p] if p else []
    errs = []
    for rel in paths:
        path = safe_path(rel)
        if not path: errs.append(rel); continue
        try:
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
        except Exception as e: errs.append(str(e))
    return jsonify({"ok":not errs,"errors":errs})

@app.route("/api/rename",methods=["POST"])
@login_required
def api_rename():
    d = request.json
    src = safe_path(d.get("path",""))
    nn  = d.get("new_name","").strip()
    if not src or not nn or "/" in nn: return jsonify({"error":"Invalid"}),400
    try:
        os.rename(src, os.path.join(os.path.dirname(src),nn))
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/move",methods=["POST"])
@login_required
def api_move():
    d = request.json
    src = safe_path(d.get("src",""))
    dst = safe_path(d.get("dst_dir",""))
    if not src or not dst: return jsonify({"error":"Invalid"}),400
    try:
        shutil.move(src, os.path.join(dst,os.path.basename(src)))
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/copy",methods=["POST"])
@login_required
def api_copy():
    d = request.json
    src = safe_path(d.get("src",""))
    dst = safe_path(d.get("dst_dir",""))
    if not src or not dst: return jsonify({"error":"Invalid"}),400
    try:
        out = os.path.join(dst,os.path.basename(src))
        shutil.copytree(src,out) if os.path.isdir(src) else shutil.copy2(src,out)
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/mkdir",methods=["POST"])
@login_required
def api_mkdir():
    d = request.json
    p = safe_path(d.get("path",""))
    n = d.get("name","").strip()
    if not p or not n: return jsonify({"error":"Invalid"}),400
    try:
        os.makedirs(os.path.join(p,n),exist_ok=True)
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/touch",methods=["POST"])
@login_required
def api_touch():
    d = request.json
    p = safe_path(d.get("path",""))
    n = d.get("name","").strip()
    if not p or not n: return jsonify({"error":"Invalid"}),400
    try:
        Path(os.path.join(p,n)).touch()
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/download")
@login_required
def api_download():
    path = safe_path(request.args.get("path",""))
    if not path or not os.path.isfile(path):
        return jsonify({"error":"Not found"}),404
    return send_file(path,as_attachment=True)

@app.route("/api/upload",methods=["POST"])
@login_required
def api_upload():
    dst = safe_path(request.form.get("path","/"))
    if not dst: return jsonify({"error":"Invalid"}),400
    saved = []
    for f in request.files.getlist("files"):
        f.save(os.path.join(dst,f.filename))
        saved.append(f.filename)
    return jsonify({"ok":True,"saved":saved})

@app.route("/api/search")
@login_required
def api_search():
    q   = request.args.get("q","").strip().lower()
    start = safe_path(request.args.get("path","/"))
    content = request.args.get("content","false")=="true"
    if not q or not start: return jsonify({"results":[]})
    results = []
    try:
        for rd,dirs,files in os.walk(start):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in dirs+files:
                if q in name.lower():
                    info = file_info(os.path.join(rd,name))
                    if info: results.append(info)
            if content:
                for name in files:
                    full = os.path.join(rd,name)
                    try:
                        with open(full,"r",encoding="utf-8",errors="ignore") as fh:
                            for i,line in enumerate(fh,1):
                                if q in line.lower():
                                    info = file_info(full)
                                    if info:
                                        info["match_line"]=i
                                        info["match_text"]=line.strip()[:120]
                                        results.append(info)
                                    break
                    except: pass
            if len(results)>=200: break
    except: pass
    return jsonify({"results":results})

@app.route("/api/storage")
@login_required
def api_storage():
    try:
        s = shutil.disk_usage(ROOT)
        pct = round(s.used/s.total*100) if s.total else 0
        return jsonify({"total":s.total,"used":s.used,"free":s.free,
            "total_str":human_size(s.total),"used_str":human_size(s.used),
            "free_str":human_size(s.free),"pct":pct})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/props")
@login_required
def api_props():
    path = safe_path(request.args.get("path",""))
    if not path: return jsonify({"error":"Invalid"}),400
    try:
        stat = os.stat(path)
        info = file_info(path)
        info.update({
            "atime":datetime.fromtimestamp(stat.st_atime).strftime("%Y-%m-%d %H:%M:%S"),
            "ctime":datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            "inode":stat.st_ino,"uid":stat.st_uid,"gid":stat.st_gid,
            "mode":oct(stat.st_mode)
        })
        return jsonify(info)
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/chmod",methods=["POST"])
@login_required
def api_chmod():
    d = request.json
    path = safe_path(d.get("path",""))
    mode = d.get("mode","")
    if not path or not re.match(r"^[0-7]{3}$",mode):
        return jsonify({"error":"Invalid"}),400
    try:
        os.chmod(path,int(mode,8))
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/compress",methods=["POST"])
@login_required
def api_compress():
    d = request.json
    paths = d.get("paths",[])
    dest  = safe_path(d.get("dest","/"))
    name  = d.get("name","archive.zip")
    if not dest or not paths: return jsonify({"error":"Invalid"}),400
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
                            zf.write(fp,os.path.relpath(fp,os.path.dirname(p)))
                else:
                    zf.write(p,os.path.basename(p))
        return jsonify({"ok":True,"out":out.replace(ROOT,"",1)})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/extract",methods=["POST"])
@login_required
def api_extract():
    d    = request.json
    path = safe_path(d.get("path",""))
    dest = safe_path(d.get("dest","/"))
    if not path or not dest: return jsonify({"error":"Invalid"}),400
    try:
        if path.endswith(".zip"):
            with zipfile.ZipFile(path) as zf: zf.extractall(dest)
        elif path.endswith((".tar.gz",".tgz",".tar.bz2",".tar")):
            with tarfile.open(path) as tf: tf.extractall(dest)
        else:
            return jsonify({"error":"Unsupported format"}),400
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/run",methods=["POST"])
@login_required
def api_run():
    d        = request.json
    path     = safe_path(d.get("path",""))
    code     = d.get("code","")
    run_type = d.get("type","auto")
    stdin_d  = d.get("stdin","")
    if path and os.path.isfile(path) and not code:
        with open(path,"r",encoding="utf-8",errors="replace") as f: code=f.read()
        ext = os.path.splitext(path)[1].lower()
        if run_type=="auto":
            run_type={"py":"python","js":"node","sh":"shell","bash":"shell"}.get(ext.lstrip("."),"python")
    elif run_type=="auto": run_type="python"
    if run_type=="html": return jsonify({"ok":True,"html":code,"type":"html"})
    suffix = {"python":".py","node":".js","shell":".sh"}.get(run_type,".py")
    tf_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w",suffix=suffix,delete=False,encoding="utf-8") as tf:
            tf.write(code); tf_path=tf.name
        if run_type=="shell": os.chmod(tf_path,0o755); cmd=["/bin/bash",tf_path]
        elif run_type=="node": cmd=["node",tf_path]
        else: cmd=["python3",tf_path]
        proc = subprocess.run(cmd,capture_output=True,text=True,timeout=30,input=stdin_d,
                              cwd=os.path.dirname(path) if path else ROOT)
        return jsonify({"ok":True,"stdout":proc.stdout,"stderr":proc.stderr,
                        "returncode":proc.returncode,"type":"text"})
    except subprocess.TimeoutExpired:
        return jsonify({"ok":False,"error":"Timeout (30s)","type":"text"})
    except FileNotFoundError as e:
        return jsonify({"ok":False,"error":str(e)+" — interpreter not found","type":"text"})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e),"type":"text"})
    finally:
        if tf_path:
            try: os.unlink(tf_path)
            except: pass

@app.route("/api/terminal",methods=["POST"])
@login_required
def api_terminal():
    d   = request.json
    cmd = d.get("cmd","").strip()
    cwd = safe_path(d.get("cwd","/")) or ROOT
    if not cmd: return jsonify({"output":""})
    try:
        proc = subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=30,cwd=cwd)
        return jsonify({"output":proc.stdout+proc.stderr,"returncode":proc.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({"output":"Timeout (30s)","returncode":-1})
    except Exception as e:
        return jsonify({"output":str(e),"returncode":-1})

@app.route("/api/git",methods=["POST"])
@login_required
def api_git():
    d   = request.json
    cmd = d.get("cmd","status")
    cwd = safe_path(d.get("path","/")) or ROOT
    allowed = ["status","log --oneline","diff","branch","pull","fetch","stash","clone","init","remote"]
    if not any(cmd.startswith(a) for a in allowed):
        return jsonify({"error":"Not allowed"}),403
    try:
        proc = subprocess.run(f"git {cmd}",shell=True,capture_output=True,text=True,timeout=60,cwd=cwd)
        return jsonify({"output":proc.stdout+proc.stderr,"returncode":proc.returncode})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/git/clone",methods=["POST"])
@login_required
def api_git_clone():
    d    = request.json
    url  = d.get("url","").strip()
    dest = safe_path(d.get("dest","/")) or ROOT
    name = d.get("name","").strip()
    if not url: return jsonify({"error":"No URL"}),400
    cmd = f"git clone {url}"
    if name: cmd += f" {name}"
    try:
        proc = subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=120,cwd=dest)
        ok = proc.returncode==0
        return jsonify({"ok":ok,"output":proc.stdout+proc.stderr})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500

@app.route("/api/processes")
@login_required
def api_processes():
    try:
        proc = subprocess.run("ps aux --no-header 2>/dev/null || ps aux",
                              shell=True,capture_output=True,text=True,timeout=5)
        procs=[]
        for line in proc.stdout.strip().split("\n")[:60]:
            parts=line.split(None,10)
            if len(parts)>=11:
                procs.append({"pid":parts[1],"cpu":parts[2],"mem":parts[3],"cmd":parts[10]})
        return jsonify({"processes":procs})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/kill",methods=["POST"])
@login_required
def api_kill():
    pid = str(request.json.get("pid",""))
    if not pid.isdigit(): return jsonify({"error":"Invalid PID"}),400
    try:
        os.kill(int(pid),signal.SIGTERM)
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

@app.route("/api/preview")
@login_required
def api_preview():
    path = safe_path(request.args.get("path",""))
    if not path or not os.path.isfile(path):
        return jsonify({"error":"Not found"}),404
    mime = mimetypes.guess_type(path)[0] or ""
    if any(mime.startswith(t) for t in ["image/","video/","audio/"]):
        return send_file(path,mimetype=mime)
    return jsonify({"error":"Not previewable"}),400

@app.route("/api/qr")
@login_required
def api_qr():
    text = request.args.get("text","")
    if not text: return jsonify({"error":"No text"}),400
    return jsonify({"ok":True,
        "qr_url":f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={text}"})

@app.route("/api/share")
@login_required
def api_share():
    path = safe_path(request.args.get("path",""))
    if not path or not os.path.isfile(path):
        return jsonify({"error":"Not found"}),404
    try:
        subprocess.Popen(["termux-share",path])
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/bookmarks")
@login_required
def api_bookmarks_get():
    return jsonify({"bookmarks":load_bookmarks()})

@app.route("/api/bookmarks",methods=["POST"])
@login_required
def api_bookmarks_set():
    bm = request.json.get("bookmarks")
    if bm is None: return jsonify({"error":"No data"}),400
    save_bookmarks(bm)
    return jsonify({"ok":True})

@app.route("/api/pkg",methods=["POST"])
@login_required
def api_pkg():
    d      = request.json
    mgr    = d.get("mgr","pip")
    action = d.get("action","install")
    pkg    = d.get("pkg","").strip()
    if not pkg: return jsonify({"error":"No package"}),400
    cmds = {
        "pip":   {"install":f"pip install {pkg} --break-system-packages",
                  "uninstall":f"pip uninstall -y {pkg}",
                  "list":"pip list"},
        "apt":   {"install":f"apt install -y {pkg}",
                  "uninstall":f"apt remove -y {pkg}",
                  "list":"apt list --installed 2>/dev/null"},
        "npm":   {"install":f"npm install -g {pkg}",
                  "uninstall":f"npm uninstall -g {pkg}",
                  "list":"npm list -g --depth=0"},
    }
    cmd = cmds.get(mgr,{}).get(action)
    if not cmd: return jsonify({"error":"Invalid"}),400
    try:
        proc = subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=120)
        return jsonify({"ok":proc.returncode==0,"output":proc.stdout+proc.stderr})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500


# ── Frontend ───────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>VrDesk V1.2</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}

:root{
  --ui:'Inter',system-ui,sans-serif;
  --mono:'JetBrains Mono',monospace;

  /* Win11 / Android 16 palette */
  --accent    :#7B5EA7;
  --accent2   :#5B8DEF;
  --grad      :linear-gradient(135deg,#7B5EA7,#5B8DEF);
  --grad2     :linear-gradient(135deg,#a78bfa,#60a5fa);
  --grad-soft :linear-gradient(135deg,rgba(123,94,167,.18),rgba(91,141,239,.18));

  /* Backgrounds — Mica/Acrylic */
  --bg        :#0f0f13;
  --bg-blur   :rgba(15,15,20,.72);
  --bg-card   :rgba(255,255,255,.055);
  --bg-hover  :rgba(255,255,255,.085);
  --bg-active :rgba(123,94,167,.22);
  --bg-input  :rgba(0,0,0,.35);

  /* Borders */
  --border    :rgba(255,255,255,.08);
  --border-hi :rgba(123,94,167,.6);

  /* Text */
  --text      :#f0f0f5;
  --text-sub  :#9090aa;
  --text-dim  :#4a4a5a;

  /* Semantic */
  --green :#4ade80;
  --red   :#f87171;
  --yellow:#fbbf24;
  --blue  :#60a5fa;
  --pink  :#f472b6;

  --radius:14px;
  --radius-sm:8px;
  --sw:230px;
  --blur:blur(20px) saturate(180%);
}

/* Light theme */
body.light{
  --bg        :#f3f3f8;
  --bg-blur   :rgba(243,243,248,.82);
  --bg-card   :rgba(255,255,255,.7);
  --bg-hover  :rgba(0,0,0,.045);
  --bg-active :rgba(123,94,167,.12);
  --bg-input  :rgba(255,255,255,.9);
  --border    :rgba(0,0,0,.07);
  --border-hi :rgba(123,94,167,.5);
  --text      :#1a1a2e;
  --text-sub  :#6b6b80;
  --text-dim  :#aaaabc;
}

/* Scrollbar */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(123,94,167,.35);border-radius:99px}
::-webkit-scrollbar-thumb:hover{background:rgba(123,94,167,.6)}

body{
  font-family:var(--ui);
  background:var(--bg);
  color:var(--text);
  height:100vh;
  display:flex;flex-direction:column;
  overflow:hidden;
  -webkit-font-smoothing:antialiased;
  /* Animated mesh gradient bg */
  background-image:
    radial-gradient(ellipse 80% 60% at 20% 10%, rgba(123,94,167,.15) 0%, transparent 60%),
    radial-gradient(ellipse 60% 80% at 80% 90%, rgba(91,141,239,.12) 0%, transparent 60%),
    radial-gradient(ellipse 40% 40% at 60% 40%, rgba(244,114,182,.07) 0%, transparent 50%);
  background-attachment:fixed;
}

/* ════════════════════════════════════════
   LOGIN
════════════════════════════════════════ */
#login-screen{
  position:fixed;inset:0;z-index:999;
  display:flex;align-items:center;justify-content:center;
  background:var(--bg);
  background-image:
    radial-gradient(ellipse 80% 60% at 20% 10%, rgba(123,94,167,.2) 0%,transparent 60%),
    radial-gradient(ellipse 60% 80% at 80% 90%, rgba(91,141,239,.15) 0%,transparent 60%);
}
.login-wrap{
  display:flex;flex-direction:column;
  align-items:center;gap:28px;
  animation:floatUp .6s cubic-bezier(.34,1.56,.64,1) both;
}
.login-logo{
  display:flex;flex-direction:column;align-items:center;gap:8px;
}
.login-logo .brand{
  font-size:48px;font-weight:700;letter-spacing:-1px;
  background:var(--grad2);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;background-clip:text;
  line-height:1;
}
.login-logo .tagline{
  font-size:12px;color:var(--text-sub);
  letter-spacing:3px;text-transform:uppercase;
}
.login-card{
  background:var(--bg-card);
  backdrop-filter:var(--blur);
  -webkit-backdrop-filter:var(--blur);
  border:1px solid var(--border);
  border-radius:24px;
  padding:36px 40px;
  min-width:300px;
  display:flex;flex-direction:column;gap:16px;align-items:center;
  box-shadow:0 32px 80px rgba(0,0,0,.4),inset 0 1px 0 rgba(255,255,255,.1);
}
#pin-input{
  width:100%;
  background:var(--bg-input);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);
  color:var(--text);
  font-family:var(--mono);
  font-size:26px;font-weight:500;
  padding:14px 20px;outline:none;
  text-align:center;letter-spacing:14px;
  transition:all .25s;
}
#pin-input:focus{
  border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(123,94,167,.2);
}
#login-btn{
  width:100%;padding:13px;
  background:var(--grad);
  border:none;border-radius:var(--radius-sm);
  color:#fff;
  font-family:var(--ui);
  font-size:14px;font-weight:600;
  cursor:pointer;letter-spacing:.5px;
  transition:all .2s;
  box-shadow:0 4px 20px rgba(123,94,167,.4);
}
#login-btn:hover{transform:translateY(-1px);box-shadow:0 6px 28px rgba(123,94,167,.55)}
#login-btn:active{transform:translateY(0)}
#login-err{color:var(--red);font-size:12px;min-height:16px;font-weight:500}
.login-hint{font-size:11px;color:var(--text-dim)}

/* ════════════════════════════════════════
   TOPBAR
════════════════════════════════════════ */
#topbar{
  background:var(--bg-blur);
  backdrop-filter:var(--blur);
  -webkit-backdrop-filter:var(--blur);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;
  padding:0 14px;height:52px;gap:8px;
  flex-shrink:0;
  position:relative;z-index:10;
}
.logo{
  display:flex;align-items:center;gap:6px;
  flex-shrink:0;text-decoration:none;
}
.logo-icon{
  width:30px;height:30px;border-radius:8px;
  background:var(--grad);
  display:flex;align-items:center;justify-content:center;
  font-size:15px;font-weight:700;color:#fff;
  box-shadow:0 2px 10px rgba(123,94,167,.4);
  animation:logoPulse 3s ease-in-out infinite;
  flex-shrink:0;
}
.logo-text{
  font-size:15px;font-weight:700;
  background:var(--grad2);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;letter-spacing:.5px;
  animation:gradShift 4s ease infinite;
  background-size:200% 200%;
}
.logo-ver{
  font-size:9px;color:var(--text-dim);
  font-weight:500;letter-spacing:.5px;
  align-self:flex-end;margin-bottom:3px;
}
#pathbar{
  flex:1;min-width:60px;
  background:var(--bg-input);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);
  color:var(--text);
  font-family:var(--mono);
  font-size:12px;padding:6px 12px;
  outline:none;transition:all .2s;
}
#pathbar:focus{border-color:var(--border-hi);box-shadow:0 0 0 3px rgba(123,94,167,.15)}
#searchbox{
  background:var(--bg-input);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);
  color:var(--text);
  font-family:var(--ui);
  font-size:12px;padding:6px 12px 6px 32px;
  outline:none;width:170px;flex-shrink:0;
  transition:all .2s;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' fill='%239090aa' viewBox='0 0 16 16'%3E%3Cpath d='M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.868-3.834zm-5.242 1.656a5 5 0 1 1 0-10 5 5 0 0 1 0 10z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;
  background-position:10px center;
}
#searchbox:focus{border-color:var(--border-hi);width:210px;box-shadow:0 0 0 3px rgba(123,94,167,.15)}
#searchbox::placeholder{color:var(--text-dim)}
.topbtn{
  background:var(--bg-card);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);
  color:var(--text-sub);
  font-family:var(--ui);
  font-size:12px;font-weight:500;
  padding:6px 12px;cursor:pointer;
  white-space:nowrap;flex-shrink:0;
  transition:all .2s;
  backdrop-filter:blur(8px);
}
.topbtn:hover{
  background:var(--bg-hover);
  border-color:var(--border-hi);
  color:var(--text);
  transform:translateY(-1px);
  box-shadow:0 4px 12px rgba(0,0,0,.2);
}
.topbtn:active{transform:translateY(0)}
#clk{
  color:var(--text-sub);
  font-family:var(--mono);
  font-size:12px;white-space:nowrap;
  flex-shrink:0;font-weight:500;
}

/* ════════════════════════════════════════
   TABS
════════════════════════════════════════ */
#tabs-bar{
  background:var(--bg-blur);
  backdrop-filter:var(--blur);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;
  padding:0 10px;gap:2px;
  flex-shrink:0;overflow-x:auto;height:38px;
}
.tab{
  display:flex;align-items:center;gap:6px;
  padding:5px 14px;font-size:12px;font-weight:500;
  cursor:pointer;border-radius:8px;
  color:var(--text-sub);white-space:nowrap;
  transition:all .2s;max-width:160px;
  border:1px solid transparent;
}
.tab:hover{background:var(--bg-hover);color:var(--text)}
.tab.active{
  background:var(--bg-active);
  border-color:var(--border-hi);
  color:var(--text);
}
.tab .tcls{
  color:var(--text-dim);font-size:12px;
  padding:1px 3px;border-radius:4px;
  transition:all .15s;
}
.tab .tcls:hover{color:var(--red);background:rgba(248,113,113,.15)}
#add-tab{
  background:transparent;border:1px solid var(--border);
  border-radius:6px;color:var(--text-sub);
  font-size:16px;cursor:pointer;padding:2px 10px;
  transition:all .2s;flex-shrink:0;
}
#add-tab:hover{background:var(--bg-hover);color:var(--text);border-color:var(--border-hi)}

/* ════════════════════════════════════════
   LAYOUT
════════════════════════════════════════ */
#body{display:flex;flex:1;overflow:hidden;gap:0}

/* ════════════════════════════════════════
   SIDEBAR
════════════════════════════════════════ */
#sidebar{
  width:var(--sw);
  background:var(--bg-blur);
  backdrop-filter:var(--blur);
  border-right:1px solid var(--border);
  overflow-y:auto;flex-shrink:0;
  display:flex;flex-direction:column;
  padding:8px;gap:2px;
}
.sb-label{
  font-size:10px;font-weight:600;
  color:var(--text-dim);letter-spacing:1.5px;
  text-transform:uppercase;
  padding:8px 8px 4px;margin-top:4px;
}
.bmark{
  display:flex;align-items:center;gap:10px;
  padding:8px 10px;font-size:12px;font-weight:500;
  color:var(--text-sub);cursor:pointer;
  border-radius:var(--radius-sm);
  border:1px solid transparent;
  transition:all .2s;
  white-space:nowrap;overflow:hidden;
}
.bmark:hover{
  background:var(--bg-hover);
  color:var(--text);
  border-color:var(--border);
  transform:translateX(2px);
}
.bmark.active-bm{
  background:var(--bg-active);
  border-color:var(--border-hi);
  color:var(--text);
}
.bmark .bico{font-size:15px;flex-shrink:0}
.bmark .bname{flex:1;overflow:hidden;text-overflow:ellipsis}
.bmark .bdel{
  opacity:0;font-size:11px;padding:2px 4px;
  border-radius:4px;flex-shrink:0;
  transition:all .15s;
}
.bmark:hover .bdel{opacity:1;color:var(--text-dim)}
.bmark .bdel:hover{color:var(--red) !important;background:rgba(248,113,113,.15)}
.bmark-add{
  border:1px dashed var(--border) !important;
  color:var(--text-dim) !important;
  margin-top:4px;
}
.bmark-add:hover{border-color:var(--border-hi) !important;color:var(--accent) !important}

#storage-wrap{
  margin-top:auto;
  padding:12px;
  background:var(--bg-card);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);
  margin:auto 0 0;
}
.stor-row{
  display:flex;justify-content:space-between;
  font-size:11px;color:var(--text-sub);margin-bottom:8px;font-weight:500;
}
.stor-track{
  background:rgba(0,0,0,.2);
  border-radius:99px;height:5px;overflow:hidden;
}
.stor-fill{
  height:100%;border-radius:99px;
  background:var(--grad);transition:width .5s cubic-bezier(.4,0,.2,1);
}
.stor-free{font-size:10px;color:var(--text-dim);margin-top:5px}

/* ════════════════════════════════════════
   MAIN
════════════════════════════════════════ */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden}

/* Toolbar */
#toolbar{
  background:var(--bg-blur);
  backdrop-filter:var(--blur);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;
  padding:7px 10px;gap:4px;
  flex-wrap:wrap;flex-shrink:0;
}
.tbtn{
  background:var(--bg-card);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);
  color:var(--text-sub);
  font-family:var(--ui);
  font-size:12px;font-weight:500;
  padding:5px 11px;cursor:pointer;
  display:flex;align-items:center;gap:4px;
  white-space:nowrap;
  transition:all .2s cubic-bezier(.34,1.56,.64,1);
  backdrop-filter:blur(8px);
}
.tbtn:hover{
  background:var(--bg-hover);
  border-color:var(--border-hi);
  color:var(--text);
  transform:translateY(-1px);
  box-shadow:0 4px 12px rgba(0,0,0,.2);
}
.tbtn:active{transform:scale(.96) translateY(0)}
.tbtn.danger:hover{
  background:rgba(248,113,113,.12);
  border-color:var(--red);color:var(--red);
}
.tbtn:disabled{opacity:.3;cursor:not-allowed;pointer-events:none}
.tbtn.accent{
  background:var(--grad-soft);
  border-color:var(--border-hi);color:var(--text);
}
.tsep{width:1px;height:20px;background:var(--border);margin:0 2px;flex-shrink:0}

/* Column headers */
#header-row{
  display:grid;
  grid-template-columns:16px 20px 1fr 80px 56px 70px;
  align-items:center;padding:6px 16px;
  font-size:10px;font-weight:600;
  color:var(--text-dim);
  border-bottom:1px solid var(--border);
  gap:8px;letter-spacing:.8px;
  flex-shrink:0;user-select:none;
  text-transform:uppercase;
}

/* Files area */
#files-area{flex:1;overflow-y:auto;padding:8px}
#files-list{display:flex;flex-direction:column;gap:2px}

.file-row{
  display:grid;
  grid-template-columns:16px 20px 1fr 80px 56px 70px;
  align-items:center;
  padding:7px 16px;font-size:13px;
  cursor:pointer;
  border-radius:var(--radius-sm);
  border:1px solid transparent;
  gap:8px;user-select:none;
  transition:all .18s cubic-bezier(.4,0,.2,1);
  position:relative;
}
.file-row::before{
  content:'';
  position:absolute;left:0;top:0;bottom:0;
  width:0;border-radius:8px 0 0 8px;
  background:var(--grad);
  transition:width .2s;
}
.file-row:hover{
  background:var(--bg-hover);
  border-color:var(--border);
  transform:translateX(2px);
}
.file-row:hover::before{width:2px}
.file-row.selected{
  background:var(--bg-active);
  border-color:var(--border-hi);
  transform:translateX(2px);
}
.file-row.selected::before{width:3px}
.fchk{width:13px;height:13px;accent-color:var(--accent);cursor:pointer}
.ficon{font-size:16px;text-align:center}
.fname{
  white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;font-weight:500;
}
.fname.dir{color:var(--yellow)}
.fname.exec{color:var(--green)}
.fname.hidden{color:var(--text-dim);font-weight:400}
.fsize{
  color:var(--text-sub);text-align:right;
  font-size:11px;font-family:var(--mono);
}
.fperms{
  color:var(--text-dim);font-size:11px;
  text-align:center;font-family:var(--mono);
}
.fdate{
  color:var(--text-dim);font-size:11px;
  text-align:right;font-family:var(--mono);
}

#up-row{
  display:flex;align-items:center;gap:10px;
  padding:7px 16px;font-size:13px;
  color:var(--text-sub);cursor:pointer;
  border-radius:var(--radius-sm);
  border:1px solid transparent;
  transition:all .18s;
}
#up-row:hover{
  background:var(--bg-hover);
  border-color:var(--border);
  color:var(--yellow);transform:translateX(2px);
}

/* Status bar */
#statusbar{
  background:var(--bg-blur);
  backdrop-filter:var(--blur);
  border-top:1px solid var(--border);
  display:flex;align-items:center;
  padding:0 16px;height:28px;
  font-size:11px;color:var(--text-dim);
  gap:16px;flex-shrink:0;
  font-family:var(--mono);
}
.dot{
  width:7px;height:7px;border-radius:50%;
  background:var(--grad);display:inline-block;
  animation:dotPulse 2s ease-in-out infinite;
  box-shadow:0 0 6px rgba(123,94,167,.5);
}

/* ════════════════════════════════════════
   TERMINAL POPUP
════════════════════════════════════════ */
#terminal-modal{
  display:none;
  position:fixed;bottom:0;left:0;right:0;
  height:340px;
  background:var(--bg-blur);
  backdrop-filter:var(--blur);
  -webkit-backdrop-filter:var(--blur);
  border-top:1px solid var(--border);
  box-shadow:0 -12px 48px rgba(0,0,0,.4);
  z-index:150;flex-direction:column;
  border-radius:20px 20px 0 0;
  transform:translateY(100%);
  transition:transform .35s cubic-bezier(.34,1.3,.64,1);
}
#terminal-modal.open{display:flex;transform:translateY(0)}
#term-titlebar{
  display:flex;align-items:center;
  padding:10px 16px;gap:10px;
  border-bottom:1px solid var(--border);
  flex-shrink:0;
}
.tdots{display:flex;gap:7px}
.tdot{
  width:12px;height:12px;border-radius:50%;
  cursor:pointer;transition:all .15s;
  flex-shrink:0;
}
.tdot:hover{transform:scale(1.2)}
.tdot.cl{background:#ff5f57}
.tdot.mn{background:#febc2e}
.tdot.mx{background:#28c840}
#term-title-text{
  font-size:12px;font-weight:500;
  color:var(--text-sub);flex:1;text-align:center;
}
#term-cwd{
  font-size:11px;color:var(--accent2);
  background:var(--bg-active);
  border:1px solid var(--border-hi);
  padding:2px 10px;border-radius:99px;
  font-family:var(--mono);
}
#term-output{
  flex:1;overflow-y:auto;
  padding:10px 16px;
  font-family:var(--mono);font-size:12px;
  line-height:1.7;color:var(--text);
  white-space:pre-wrap;word-break:break-all;
}
.t-cmd{color:var(--accent2);font-weight:500}
.t-out{color:var(--text)}
.t-err{color:var(--red)}
.t-info{color:var(--text-sub)}
.t-ok{color:var(--green)}
#term-input-row{
  display:flex;align-items:center;
  border-top:1px solid var(--border);
  padding:8px 16px;gap:10px;
  flex-shrink:0;
}
#term-prompt{
  color:var(--accent);font-weight:600;
  font-family:var(--mono);font-size:12px;
  white-space:nowrap;
}
#term-input{
  flex:1;background:transparent;border:none;
  color:var(--text);
  font-family:var(--mono);font-size:12px;
  outline:none;caret-color:var(--accent);
}
#term-input::placeholder{color:var(--text-dim)}

/* ════════════════════════════════════════
   MODAL
════════════════════════════════════════ */
#modal-overlay{
  display:none;position:fixed;inset:0;
  background:rgba(0,0,0,.6);
  z-index:200;align-items:center;justify-content:center;
  backdrop-filter:blur(8px);
}
#modal-overlay.show{display:flex}
#modal{
  background:var(--bg-blur);
  backdrop-filter:var(--blur);
  -webkit-backdrop-filter:var(--blur);
  border:1px solid var(--border);
  border-radius:20px;padding:0;
  min-width:360px;max-width:94vw;max-height:92vh;
  display:flex;flex-direction:column;
  box-shadow:0 32px 80px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.07);
  overflow:hidden;
  animation:modalIn .25s cubic-bezier(.34,1.56,.64,1) both;
}
#modal-header{
  display:flex;align-items:center;justify-content:space-between;
  padding:16px 20px;
  border-bottom:1px solid var(--border);
  flex-shrink:0;
}
#modal-title{
  font-size:14px;font-weight:600;color:var(--text);
}
#modal-close{
  width:28px;height:28px;
  background:var(--bg-hover);
  border:1px solid var(--border);
  border-radius:50%;
  color:var(--text-sub);font-size:14px;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  transition:all .15s;font-family:var(--ui);line-height:1;
}
#modal-close:hover{background:rgba(248,113,113,.15);color:var(--red);border-color:var(--red)}
#modal-body{overflow-y:auto;flex:1;padding:20px}
#modal input,#modal textarea,#modal select{
  width:100%;
  background:var(--bg-input);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);
  color:var(--text);
  font-family:var(--mono);
  font-size:12px;padding:9px 12px;
  outline:none;margin-bottom:12px;
  transition:all .2s;
}
#modal input:focus,#modal textarea:focus,#modal select:focus{
  border-color:var(--border-hi);
  box-shadow:0 0 0 3px rgba(123,94,167,.15);
}
#modal textarea{min-height:280px;resize:vertical;line-height:1.6}
#modal select{color:var(--text);font-family:var(--ui)}
#modal label{
  display:block;font-size:10px;font-weight:600;
  color:var(--text-dim);letter-spacing:1px;
  margin-bottom:5px;text-transform:uppercase;
}
.mbtn-row{
  display:flex;gap:8px;justify-content:flex-end;
  padding:14px 20px;
  border-top:1px solid var(--border);
  flex-shrink:0;
}
.mbtn{
  background:var(--bg-card);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);
  color:var(--text-sub);
  font-family:var(--ui);font-size:12px;font-weight:500;
  padding:8px 18px;cursor:pointer;
  transition:all .2s;
}
.mbtn:hover{
  background:var(--bg-hover);
  border-color:var(--border-hi);color:var(--text);
  transform:translateY(-1px);
}
.mbtn:active{transform:translateY(0)}
.mbtn.primary{
  background:var(--grad);
  border-color:transparent;color:#fff;
  box-shadow:0 4px 14px rgba(123,94,167,.4);
}
.mbtn.primary:hover{
  box-shadow:0 6px 20px rgba(123,94,167,.55);
  opacity:.92;
}
.mbtn.danger{border-color:rgba(248,113,113,.3);color:var(--red)}
.mbtn.danger:hover{
  background:rgba(248,113,113,.1);
  border-color:var(--red);
}

/* Run output */
.run-output{
  background:rgba(0,0,0,.3);
  border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:12px;
  font-family:var(--mono);font-size:11px;line-height:1.7;
  white-space:pre-wrap;max-height:220px;overflow-y:auto;
  color:var(--text);margin-top:10px;
}
.run-output.err{color:var(--red);border-color:rgba(248,113,113,.3)}

/* Props table */
.props-table{width:100%;border-collapse:collapse;font-size:12px}
.props-table tr{border-bottom:1px solid var(--border)}
.props-table td{padding:8px 10px}
.props-table td:first-child{
  color:var(--text-sub);width:110px;font-weight:500;font-size:11px;
}

/* Perm rows */
.perm-row{display:flex;align-items:center;gap:10px;margin-bottom:10px;font-size:12px}
.perm-row>label:first-child{width:65px;color:var(--text-sub);font-weight:500}
.perm-checks{display:flex;gap:16px}
.perm-checks label{
  display:flex;align-items:center;gap:5px;
  cursor:pointer;color:var(--text);
  font-family:var(--mono);
}

/* Upload */
#drop-zone{
  border:2px dashed var(--border);
  border-radius:var(--radius);padding:28px;
  text-align:center;color:var(--text-sub);
  font-size:13px;cursor:pointer;transition:all .2s;
}
#drop-zone:hover,#drop-zone.drag{
  border-color:var(--accent);
  background:var(--bg-active);color:var(--text);
}

/* Git */
.git-url-wrap{position:relative}
.git-paste-btn{
  position:absolute;right:10px;top:50%;
  transform:translateY(-62%);
  background:transparent;border:none;
  color:var(--text-sub);cursor:pointer;font-size:14px;
}
.git-paste-btn:hover{color:var(--accent)}
.git-out-box{
  background:rgba(0,0,0,.3);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:12px;
  font-family:var(--mono);font-size:11px;
  white-space:pre-wrap;max-height:180px;overflow-y:auto;
  color:var(--text);min-height:50px;margin-top:8px;
}

/* Pkg manager */
.pkg-tabs{display:flex;gap:4px;margin-bottom:14px}
.pkg-tab{
  padding:6px 16px;font-size:12px;font-weight:500;
  border:1px solid var(--border);
  border-radius:var(--radius-sm);cursor:pointer;
  color:var(--text-sub);transition:all .2s;
}
.pkg-tab.active,.pkg-tab:hover{
  background:var(--bg-active);
  border-color:var(--border-hi);color:var(--text);
}

/* Toast */
#toast{
  position:fixed;bottom:48px;right:16px;
  background:var(--bg-blur);
  backdrop-filter:var(--blur);
  border:1px solid var(--border);
  border-radius:12px;
  color:var(--text);
  padding:12px 18px;font-size:12px;font-weight:500;
  z-index:600;display:none;
  font-family:var(--ui);
  max-width:300px;
  box-shadow:0 8px 32px rgba(0,0,0,.4);
  animation:toastIn .25s cubic-bezier(.34,1.56,.64,1);
}
#toast.ok{border-left:3px solid var(--green)}
#toast.err{border-left:3px solid var(--red);color:var(--red)}
#toast.info{border-left:3px solid var(--blue)}
#toast.warn{border-left:3px solid var(--yellow)}

/* Context menu */
#ctx-menu{
  display:none;position:fixed;
  background:var(--bg-blur);
  backdrop-filter:var(--blur);
  -webkit-backdrop-filter:var(--blur);
  border:1px solid var(--border);
  border-radius:14px;z-index:400;
  min-width:185px;padding:6px;
  font-size:12px;font-weight:500;
  box-shadow:0 16px 48px rgba(0,0,0,.4);
  animation:ctxIn .15s ease both;
}
.cm{
  padding:8px 12px;cursor:pointer;
  color:var(--text-sub);
  display:flex;align-items:center;gap:10px;
  border-radius:var(--radius-sm);transition:all .15s;
}
.cm:hover{background:var(--bg-hover);color:var(--text)}
.cm .ci{font-size:14px;width:18px;text-align:center}
.cm.danger{color:var(--red)}
.cm.danger:hover{background:rgba(248,113,113,.1)}
.csep{border-top:1px solid var(--border);margin:5px 0}

/* ════════════════════════════════════════
   ANIMATIONS
════════════════════════════════════════ */
@keyframes floatUp{
  from{opacity:0;transform:translateY(24px) scale(.97)}
  to{opacity:1;transform:none}
}
@keyframes modalIn{
  from{opacity:0;transform:scale(.95) translateY(8px)}
  to{opacity:1;transform:none}
}
@keyframes ctxIn{
  from{opacity:0;transform:scale(.95)}
  to{opacity:1;transform:none}
}
@keyframes toastIn{
  from{opacity:0;transform:translateX(16px)}
  to{opacity:1;transform:none}
}
@keyframes dotPulse{
  0%,100%{box-shadow:0 0 6px rgba(123,94,167,.4)}
  50%{box-shadow:0 0 14px rgba(123,94,167,.8)}
}
@keyframes logoPulse{
  0%,100%{box-shadow:0 2px 10px rgba(123,94,167,.4)}
  50%{box-shadow:0 2px 20px rgba(123,94,167,.7)}
}
@keyframes gradShift{
  0%,100%{background-position:0% 50%}
  50%{background-position:100% 50%}
}

.file-row{
  animation:rowIn .14s ease both;
}
@keyframes rowIn{
  from{opacity:0;transform:translateX(-6px)}
  to{opacity:1;transform:none}
}

/* ════════════════════════════════════════
   RESPONSIVE
════════════════════════════════════════ */
@media(max-width:640px){
  :root{--sw:0px}
  #sidebar{display:none}
  #searchbox{display:none}
  .topbtn{padding:5px 8px;font-size:11px}
  .logo-text{font-size:13px}
  #header-row,.file-row{grid-template-columns:14px 18px 1fr 70px}
  .fperms,.fdate{display:none}
}
@media(max-width:380px){
  #header-row,.file-row{grid-template-columns:14px 18px 1fr}
  .fsize{display:none}
  .tbtn{padding:4px 8px;font-size:11px}
}
</style>
</head>
<body>

<!-- ════ LOGIN ════ -->
<div id="login-screen">
<div class="login-wrap">
  <div class="login-logo">
    <div class="brand">VrDesk</div>
    <div class="tagline">File Manager · V1.2</div>
  </div>
  <div class="login-card">
    <input id="pin-input" type="password" maxlength="8" placeholder="••••" autocomplete="off"/>
    <button id="login-btn" onclick="doLogin()">Unlock</button>
    <div id="login-err"></div>
    <div class="login-hint">Default PIN: 1234</div>
  </div>
</div>
</div>

<!-- ════ TOPBAR ════ -->
<div id="topbar" style="display:none">
  <div class="logo">
    <div class="logo-icon">V</div>
    <span class="logo-text">VrDesk</span>
    <span class="logo-ver">v1.2</span>
  </div>
  <input id="pathbar" type="text" value="/"/>
  <input id="searchbox" type="text" placeholder="Search files…"/>
  <button class="topbtn" onclick="toggleTheme()">◑</button>
  <button class="topbtn" onclick="toggleTerminal()" title="Terminal [`]">⌨ Term</button>
  <button class="topbtn" onclick="showGitPanel()">⌬ Git</button>
  <button class="topbtn" onclick="showPkg()">⬡ Pkg</button>
  <button class="topbtn" onclick="showProcesses()">⚙</button>
  <button class="topbtn" onclick="doLogout()">⏻</button>
  <span id="clk"></span>
</div>

<!-- ════ TABS ════ -->
<div id="tabs-bar" style="display:none"></div>

<!-- ════ BODY ════ -->
<div id="body" style="display:none">
  <div id="sidebar">
    <div class="sb-label">Bookmarks</div>
    <div id="bookmarks-list"></div>
    <div id="storage-wrap">
      <div class="stor-row">
        <span id="st-used">Storage</span>
        <span id="st-pct" style="color:var(--accent2)">—</span>
      </div>
      <div class="stor-track">
        <div class="stor-fill" id="stor-fill" style="width:0%"></div>
      </div>
      <div class="stor-free" id="st-free">—</div>
    </div>
  </div>

  <div id="main">
    <div id="toolbar">
      <button class="tbtn" onclick="navUp()">⬆ Up</button>
      <button class="tbtn" onclick="refresh()">↻</button>
      <div class="tsep"></div>
      <button class="tbtn" onclick="showMkdir()">📁 New</button>
      <button class="tbtn" onclick="showTouch()">📄 New</button>
      <div class="tsep"></div>
      <button class="tbtn" id="btn-edit"   onclick="editSelected()"     disabled>✎ Edit</button>
      <button class="tbtn" id="btn-run"    onclick="runSelected()"      disabled>▶ Run</button>
      <button class="tbtn" id="btn-rename" onclick="renameSelected()"   disabled>✏ Rename</button>
      <button class="tbtn" id="btn-copy"   onclick="copySelected()"     disabled>⎘ Copy</button>
      <button class="tbtn"                 onclick="pasteClipboard()">⎙ Paste</button>
      <button class="tbtn" id="btn-zip"    onclick="zipSelected()"      disabled>📦 Zip</button>
      <div class="tsep"></div>
      <button class="tbtn" id="btn-props"  onclick="showProps()"        disabled>ℹ Info</button>
      <button class="tbtn" id="btn-chmod"  onclick="showChmod()"        disabled>🔑 Perm</button>
      <button class="tbtn" id="btn-dl"     onclick="downloadSelected()" disabled>⬇ DL</button>
      <button class="tbtn"                 onclick="showUpload()">⬆ Upload</button>
      <div class="tsep"></div>
      <button class="tbtn danger" id="btn-del" onclick="deleteSelected()" disabled>✕ Delete</button>
    </div>

    <div id="header-row">
      <span></span><span></span>
      <span>Name</span>
      <span style="text-align:right">Size</span>
      <span style="text-align:center">Perms</span>
      <span style="text-align:right">Modified</span>
    </div>

    <div id="files-area"><div id="files-list"></div></div>

    <div id="statusbar">
      <span><span class="dot"></span> vrdesk</span>
      <span id="st-path" style="color:var(--accent2)">/</span>
      <span id="st-count">0 items</span>
      <span id="st-sel" style="color:var(--accent)"></span>
      <span id="st-multi" style="color:var(--blue)"></span>
    </div>
  </div>
</div>

<!-- ════ TERMINAL ════ -->
<div id="terminal-modal">
  <div id="term-titlebar">
    <div class="tdots">
      <span class="tdot cl" onclick="toggleTerminal()" title="Close"></span>
      <span class="tdot mn" onclick="toggleTerminal()" title="Hide"></span>
      <span class="tdot mx" onclick="termMax()" title="Maximize"></span>
    </div>
    <span id="term-title-text">Terminal</span>
    <span id="term-cwd">~</span>
  </div>
  <div id="term-output"></div>
  <div id="term-input-row">
    <span id="term-prompt">~ $</span>
    <input id="term-input" type="text" placeholder="type command…" autocomplete="off" spellcheck="false"/>
  </div>
</div>

<!-- ════ MODAL ════ -->
<div id="modal-overlay">
  <div id="modal">
    <div id="modal-header">
      <span id="modal-title"></span>
      <button id="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div id="modal-body"></div>
    <div class="mbtn-row" id="modal-btns"></div>
  </div>
</div>

<div id="toast"></div>
<div id="ctx-menu"></div>

<script>
let cwd="/",items=[],selected=null,multiSel=new Set();
let clipboard=null;
let tabs=[{id:1,path:"/"}],activeTab=1,nextTabId=2;
let termHistory=[],termIdx=0;
let vrToken=localStorage.getItem("vrd_token")||"";
let bookmarks=[];

async function checkAuth(){
  const r=await fetch("/api/check_auth",{headers:{"X-VrDesk-Token":vrToken}});
  const d=await r.json();
  if(d.ok) showApp();
}
function authH(){return{"X-VrDesk-Token":vrToken,"Content-Type":"application/json"};}
async function doLogin(){
  const pin=document.getElementById("pin-input").value;
  const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({pin})});
  const d=await r.json();
  if(d.ok){vrToken=d.token;localStorage.setItem("vrd_token",vrToken);showApp();}
  else{document.getElementById("login-err").textContent="Wrong PIN";document.getElementById("pin-input").value="";document.getElementById("pin-input").focus();}
}
document.getElementById("pin-input").addEventListener("keydown",e=>{
  if(e.key==="Enter")doLogin();
  document.getElementById("login-err").textContent="";
});
async function doLogout(){
  await fetch("/api/logout",{method:"POST",headers:authH()});
  localStorage.removeItem("vrd_token");location.reload();
}
function showApp(){
  document.getElementById("login-screen").style.display="none";
  ["topbar","tabs-bar","body"].forEach(id=>document.getElementById(id).style.display="");
  if(localStorage.getItem("vrd_theme")==="light")document.body.classList.add("light");
  loadBookmarks();renderTabs();nav("/");loadStorage();startClock();termBoot();
}

async function api(url,opts={}){
  if(!opts.headers)opts.headers={};
  opts.headers["X-VrDesk-Token"]=vrToken;
  if(opts.body&&typeof opts.body==="object"){opts.headers["Content-Type"]="application/json";opts.body=JSON.stringify(opts.body);}
  const r=await fetch(url,opts);
  if(r.status===401){location.reload();return{};}
  return r.json().catch(()=>({}));
}

async function nav(path){
  cwd=path;
  document.getElementById("pathbar").value=path;
  document.getElementById("st-path").textContent=path;
  document.getElementById("term-cwd").textContent=shortPath(path);
  document.getElementById("term-prompt").textContent=shortPath(path)+" $";
  selected=null;multiSel.clear();updateBtns();
  const data=await api("/api/list?path="+encodeURIComponent(path));
  if(data.error){toast(data.error,"err");return;}
  items=data.items||[];render(items);
  document.getElementById("st-count").textContent=items.length+" items";
  document.getElementById("st-sel").textContent="";
  document.getElementById("st-multi").textContent="";
  const tab=tabs.find(t=>t.id===activeTab);
  if(tab){tab.path=path;renderTabs();}
}
function shortPath(p){
  if(!p||p==="/")return"~";
  const parts=p.replace(/\/$/,"").split("/").filter(Boolean);
  if(parts.length<=2)return"~/"+parts.join("/");
  return"~/…/"+parts[parts.length-1];
}
function navUp(){const parts=cwd.replace(/\/$/,"").split("/").filter(Boolean);parts.pop();nav("/"+parts.join("/"));}
function refresh(){nav(cwd);}
document.getElementById("pathbar").addEventListener("keydown",e=>{if(e.key==="Enter")nav(e.target.value.trim()||"/");});

function render(list){
  const fl=document.getElementById("files-list");fl.innerHTML="";
  if(cwd!=="/"){
    const up=document.createElement("div");up.id="up-row";
    up.innerHTML=`<span>📁</span><span style="color:var(--text-sub)">..</span>`;
    up.onclick=()=>navUp();fl.appendChild(up);
  }
  list.forEach((item,idx)=>{
    const row=document.createElement("div");
    const isSel=(selected&&selected.path===item.path)||multiSel.has(item.path);
    row.className="file-row"+(isSel?" selected":"");
    row.style.animationDelay=(idx*0.02)+"s";
    const icon=item.is_dir?"📁":fileIcon(item.ext,item.name);
    let cls=item.is_dir?"dir":(item.perms?.[2]==="x"?"exec":"");
    if(item.name.startsWith("."))cls+=" hidden";
    row.innerHTML=`
      <input type="checkbox" class="fchk" ${multiSel.has(item.path)?"checked":""}
             onclick="toggleMulti(event,'${esc(item.path)}')">
      <span class="ficon">${icon}</span>
      <span class="fname ${cls.trim()}">${esc(item.name)}</span>
      <span class="fsize">${item.is_dir?"":item.size_str}</span>
      <span class="fperms">${item.perms||"—"}</span>
      <span class="fdate">${item.mtime}</span>`;
    row.addEventListener("click",e=>{if(e.target.classList.contains("fchk"))return;selectItem(item,row);});
    row.addEventListener("dblclick",()=>{
      if(item.is_dir)nav(cwd==="/"?"/"+item.name:cwd+"/"+item.name);
      else editFile(item);
    });
    row.addEventListener("contextmenu",e=>{e.preventDefault();selectItem(item,row);showCtxMenu(e,item);});
    fl.appendChild(row);
  });
}

function fileIcon(ext,name){
  if(name&&name.startsWith("."))return"·";
  const m={".py":"🐍",".sh":"📜",".bash":"📜",".zsh":"📜",".js":"🟨",".ts":"🔷",".jsx":"🟦",".tsx":"🔷",".html":"🌐",".htm":"🌐",".css":"🎨",".scss":"🎨",".json":"{}",".xml":"<>",".yaml":"📋",".yml":"📋",".toml":"📋",".txt":"📄",".md":"📝",".log":"📋",".csv":"📊",".zip":"📦",".tar":"📦",".gz":"📦",".bz2":"📦",".7z":"📦",".rar":"📦",".jpg":"🖼",".jpeg":"🖼",".png":"🖼",".gif":"🖼",".svg":"🖼",".webp":"🖼",".mp3":"🎵",".wav":"🎵",".flac":"🎵",".mp4":"🎬",".mkv":"🎬",".avi":"🎬",".pdf":"📕",".apk":"🤖",".deb":"📦",".exe":"⚙",".c":"💻",".cpp":"💻",".h":"💻",".java":"☕",".kt":"💜",".rs":"🦀",".go":"🐹",".php":"🐘",".rb":"💎",".swift":"🍎",".db":"🗄",".sql":"🗄",".sqlite":"🗄",".env":"🔒"};
  return m[ext]||"📄";
}

function selectItem(item,row){
  document.querySelectorAll(".file-row.selected").forEach(r=>{if(!multiSel.has(r.dataset?.path))r.classList.remove("selected");});
  row.classList.add("selected");selected=item;updateBtns();
  document.getElementById("st-sel").textContent="› "+item.name;
}
function toggleMulti(e,path){
  e.stopPropagation();
  if(multiSel.has(path))multiSel.delete(path);else multiSel.add(path);
  document.getElementById("st-multi").textContent=multiSel.size>0?multiSel.size+" selected":"";
  updateBtns();
}
function updateBtns(){
  const has=!!selected||multiSel.size>0,isFile=!!selected&&!selected.is_dir;
  ["btn-rename","btn-copy","btn-del","btn-props","btn-chmod","btn-zip"].forEach(id=>{const el=document.getElementById(id);if(el)el.disabled=!has;});
  document.getElementById("btn-edit").disabled=!isFile;
  document.getElementById("btn-run").disabled=!isFile;
  document.getElementById("btn-dl").disabled=!isFile;
}

function renderTabs(){
  const bar=document.getElementById("tabs-bar");bar.innerHTML="";
  tabs.forEach(t=>{
    const div=document.createElement("div");
    div.className="tab"+(t.id===activeTab?" active":"");
    const name=t.path==="/"?"~":t.path.split("/").pop();
    div.innerHTML=`<span>${esc(name)}</span>${tabs.length>1?`<span class="tcls" onclick="closeTab(${t.id},event)">✕</span>`:""}`;
    div.addEventListener("click",e=>{if(e.target.classList.contains("tcls"))return;activeTab=t.id;nav(t.path);});
    bar.appendChild(div);
  });
  const add=document.createElement("button");add.id="add-tab";add.textContent="+";
  add.onclick=()=>{tabs.push({id:nextTabId,path:cwd});activeTab=nextTabId++;renderTabs();nav(cwd);};
  bar.appendChild(add);
}
function closeTab(id,e){
  e.stopPropagation();tabs=tabs.filter(t=>t.id!==id);
  if(activeTab===id)activeTab=tabs[0].id;renderTabs();
  nav(tabs.find(t=>t.id===activeTab).path);
}

async function loadBookmarks(){const r=await api("/api/bookmarks");bookmarks=r.bookmarks||[];renderBookmarks();}
async function saveBM(){await api("/api/bookmarks",{method:"POST",body:{bookmarks}});}
function renderBookmarks(){
  const el=document.getElementById("bookmarks-list");el.innerHTML="";
  bookmarks.forEach((b,i)=>{
    const d=document.createElement("div");d.className="bmark";
    d.innerHTML=`<span class="bico">${b.icon}</span><span class="bname">${esc(b.name)}</span><span class="bdel" onclick="rmBM(${i},event)">✕</span>`;
    d.addEventListener("click",e=>{if(!e.target.classList.contains("bdel"))nav(b.path);});
    el.appendChild(d);
  });
  const add=document.createElement("div");add.className="bmark bmark-add";
  add.innerHTML=`<span class="bico">＋</span><span class="bname">Bookmark this folder</span>`;
  add.onclick=async()=>{
    const name=cwd.split("/").pop()||"Home";
    bookmarks.push({icon:"📁",name,path:cwd});
    await saveBM();renderBookmarks();toast("Bookmark saved","ok");
  };
  el.appendChild(add);
}
async function rmBM(i,e){e.stopPropagation();bookmarks.splice(i,1);await saveBM();renderBookmarks();}

async function loadStorage(){
  const d=await api("/api/storage");if(d.error)return;
  document.getElementById("st-used").textContent=d.used_str+" / "+d.total_str;
  document.getElementById("st-pct").textContent=d.pct+"%";
  document.getElementById("stor-fill").style.width=d.pct+"%";
  document.getElementById("stor-fill").style.background=d.pct>80?"var(--red)":d.pct>60?"var(--yellow)":"var(--grad)";
  document.getElementById("st-free").textContent="Free: "+d.free_str;
}

function showModal(title,bodyHTML,btns){
  document.getElementById("modal-title").textContent=title;
  document.getElementById("modal-body").innerHTML=bodyHTML;
  const br=document.getElementById("modal-btns");br.innerHTML="";
  btns.forEach(b=>{const btn=document.createElement("button");btn.className="mbtn"+(b.primary?" primary":"")+(b.danger?" danger":"");btn.textContent=b.label;btn.onclick=b.action;br.appendChild(btn);});
  document.getElementById("modal-overlay").classList.add("show");
}
function closeModal(){document.getElementById("modal-overlay").classList.remove("show");}
document.getElementById("modal-overlay").addEventListener("click",e=>{if(e.target===document.getElementById("modal-overlay"))closeModal();});
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeModal();});

function showMkdir(){
  showModal("New Folder",`<label>Folder Name</label><input id="mi" type="text" placeholder="my-folder"/>`,
    [{label:"Cancel",action:closeModal},{label:"Create",primary:true,action:async()=>{
      const name=document.getElementById("mi").value.trim();if(!name)return;
      const r=await api("/api/mkdir",{method:"POST",body:{path:cwd,name}});
      closeModal();if(r.ok){toast("Folder created","ok");refresh();}else toast(r.error,"err");
    }}]);
  setTimeout(()=>document.getElementById("mi")?.focus(),60);
}
function showTouch(){
  showModal("New File",`<label>File Name</label><input id="mi" type="text" placeholder="script.py"/>`,
    [{label:"Cancel",action:closeModal},{label:"Create",primary:true,action:async()=>{
      const name=document.getElementById("mi").value.trim();if(!name)return;
      const r=await api("/api/touch",{method:"POST",body:{path:cwd,name}});
      closeModal();if(r.ok){toast("File created","ok");refresh();}else toast(r.error,"err");
    }}]);
  setTimeout(()=>document.getElementById("mi")?.focus(),60);
}

async function editFile(item){
  const path=item?item.path:(selected?selected.path:null);if(!path)return;
  const r=await api("/api/read?path="+encodeURIComponent(path));
  if(r.error){toast(r.error,"err");return;}
  const fname=path.split("/").pop();
  const ext=fname.split(".").pop().toLowerCase();
  const typeMap={py:"python",js:"node",sh:"shell",bash:"shell",html:"html",htm:"html"};
  showModal("Edit — "+fname,
    `<div style="display:flex;gap:8px;margin-bottom:10px;align-items:center">
       <select id="rts"><option value="python">🐍 Python</option><option value="node">🟨 Node.js</option><option value="shell">📜 Shell</option><option value="html">🌐 HTML</option></select>
       <button class="mbtn primary" style="padding:6px 14px;white-space:nowrap" onclick="runFromEditor()">▶ Run</button>
     </div>
     <textarea id="editor" spellcheck="false">${esc(r.content)}</textarea>
     <div id="run-result"></div>`,
    [{label:"Close",action:closeModal},{label:"💾 Save",primary:true,action:async()=>{
      const content=document.getElementById("editor").value;
      const wr=await api("/api/write",{method:"POST",body:{path,content}});
      if(wr.ok){toast("Saved","ok");closeModal();refresh();}else toast(wr.error,"err");
    }}]);
  const sel=document.getElementById("rts");if(sel&&typeMap[ext])sel.value=typeMap[ext];
}
async function runFromEditor(){
  const code=document.getElementById("editor")?.value;
  const type=document.getElementById("rts")?.value||"python";
  const rd=document.getElementById("run-result");if(!code||!rd)return;
  rd.innerHTML=`<div class="run-output" style="color:var(--text-sub)">⏳ Running…</div>`;
  const r=await api("/api/run",{method:"POST",body:{code,type}});
  if(r.type==="html"){
    rd.innerHTML=`<div style="font-size:10px;color:var(--text-sub);margin:8px 0 4px">HTML Preview</div>
      <iframe srcdoc="${esc(r.html||code)}" style="width:100%;height:260px;border:1px solid var(--border);border-radius:8px;background:#fff"></iframe>`;
    return;
  }
  const out=(r.stdout||"")+(r.stderr||"")||r.error||"(no output)";
  rd.innerHTML=`<pre class="run-output${r.stderr||!r.ok?" err":""}">${esc(out)}</pre>`;
}
function editSelected(){if(selected)editFile(selected);}
function runSelected(){if(selected&&!selected.is_dir)editFile(selected);}

function renameSelected(){
  if(!selected)return;
  showModal("Rename",`<input id="mi" type="text" value="${esc(selected.name)}"/>`,
    [{label:"Cancel",action:closeModal},{label:"Rename",primary:true,action:async()=>{
      const nn=document.getElementById("mi").value.trim();if(!nn)return;
      const r=await api("/api/rename",{method:"POST",body:{path:selected.path,new_name:nn}});
      closeModal();if(r.ok){toast("Renamed","ok");refresh();}else toast(r.error,"err");
    }}]);
  setTimeout(()=>{const i=document.getElementById("mi");i?.focus();i?.select();},60);
}
function copySelected(){const paths=multiSel.size>0?[...multiSel]:(selected?[selected.path]:[]);if(!paths.length)return;clipboard={paths,op:"copy"};toast(paths.length+" item(s) copied","info");}
function moveSelected(){const paths=multiSel.size>0?[...multiSel]:(selected?[selected.path]:[]);if(!paths.length)return;clipboard={paths,op:"move"};toast(paths.length+" item(s) cut","info");}
async function pasteClipboard(){
  if(!clipboard){toast("Nothing to paste","err");return;}
  const{paths,op}=clipboard;const ep=op==="copy"?"/api/copy":"/api/move";
  let ok=0,errs=[];
  for(const src of paths){const r=await api(ep,{method:"POST",body:{src,dst_dir:cwd}});if(r.ok)ok++;else errs.push(r.error);}
  if(!errs.length){toast((op==="copy"?"Pasted ":"Moved ")+ok,"ok");clipboard=null;}else toast(errs[0],"err");
  refresh();
}
function deleteSelected(){
  const paths=multiSel.size>0?[...multiSel]:(selected?[selected.path]:[]);if(!paths.length)return;
  const names=paths.map(p=>p.split("/").pop()).join(", ");
  showModal("Confirm Delete",
    `<p style="line-height:1.7;font-size:13px">Delete <strong style="color:var(--yellow)">${esc(names)}</strong>?<br><span style="color:var(--text-sub);font-size:12px">This cannot be undone.</span></p>`,
    [{label:"Cancel",action:closeModal},{label:"Delete",danger:true,action:async()=>{
      const r=await api("/api/delete",{method:"POST",body:{paths}});
      closeModal();if(r.ok){toast("Deleted","ok");selected=null;multiSel.clear();updateBtns();refresh();}
      else toast((r.errors||[]).join(", ")||"Error","err");
    }}]);
}
function zipSelected(){
  const paths=multiSel.size>0?[...multiSel]:(selected?[selected.path]:[]);if(!paths.length)return;
  showModal("Compress",
    `<p style="font-size:12px;color:var(--text-sub);margin-bottom:12px">${paths.length} item(s) selected</p>
     <label>Archive Name</label><input id="zn" type="text" value="archive.zip"/>`,
    [{label:"Cancel",action:closeModal},{label:"Compress",primary:true,action:async()=>{
      const name=document.getElementById("zn").value.trim()||"archive.zip";
      const r=await api("/api/compress",{method:"POST",body:{paths,dest:cwd,name}});
      closeModal();if(r.ok){toast("Compressed","ok");refresh();}else toast(r.error,"err");
    }}]);
}
async function extractSelected(){
  if(!selected)return;
  const r=await api("/api/extract",{method:"POST",body:{path:selected.path,dest:cwd}});
  if(r.ok){toast("Extracted","ok");refresh();}else toast(r.error,"err");
}
async function showProps(){
  const path=selected?selected.path:null;if(!path)return;
  const d=await api("/api/props?path="+encodeURIComponent(path));if(d.error){toast(d.error,"err");return;}
  const rows=[["Name",d.name],["Path",d.path],["Type",d.is_dir?"Directory":"File"],["Size",d.size_str],["Permissions",d.perms+" ("+d.mode+")"],["Modified",d.mtime],["Accessed",d.atime],["UID/GID",d.uid+"/"+d.gid],["MIME",d.mime||"—"]];
  showModal("Properties — "+d.name,
    `<table class="props-table">${rows.map(([k,v])=>`<tr><td>${k}</td><td style="font-family:var(--mono);font-size:11px">${esc(String(v))}</td></tr>`).join("")}</table>`,
    [{label:"Close",action:closeModal}]);
}
function showChmod(){
  if(!selected)return;
  const cur=selected.perms||"644";const bits=cur.split("").map(Number);
  let html=`<p style="font-size:12px;color:var(--text-sub);margin-bottom:12px">Current: <span style="font-family:var(--mono);color:var(--yellow)">${cur}</span></p>`;
  ["Owner","Group","Others"].forEach((lbl,i)=>{
    const b=bits[i]||0;
    html+=`<div class="perm-row"><label>${lbl}</label><div class="perm-checks">
      <label><input type="checkbox" id="p${i}r" ${b&4?"checked":""}> r</label>
      <label><input type="checkbox" id="p${i}w" ${b&2?"checked":""}> w</label>
      <label><input type="checkbox" id="p${i}x" ${b&1?"checked":""}> x</label>
    </div></div>`;
  });
  html+=`<p style="font-size:12px;color:var(--text-sub);margin-top:8px">Result: <span id="cp" style="font-family:var(--mono);color:var(--accent)">${cur}</span></p>`;
  showModal("Permissions — "+selected.name,html,
    [{label:"Cancel",action:closeModal},{label:"Apply",primary:true,action:async()=>{
      let mode="";
      for(let i=0;i<3;i++)mode+=((document.getElementById(`p${i}r`)?.checked?4:0)+(document.getElementById(`p${i}w`)?.checked?2:0)+(document.getElementById(`p${i}x`)?.checked?1:0));
      const r=await api("/api/chmod",{method:"POST",body:{path:selected.path,mode}});
      closeModal();if(r.ok){toast("Permissions set: "+mode,"ok");refresh();}else toast(r.error,"err");
    }}]);
  setTimeout(()=>{
    const up=()=>{let m="";for(let i=0;i<3;i++)m+=((document.getElementById(`p${i}r`)?.checked?4:0)+(document.getElementById(`p${i}w`)?.checked?2:0)+(document.getElementById(`p${i}x`)?.checked?1:0));const el=document.getElementById("cp");if(el)el.textContent=m;};
    document.querySelectorAll("[id^='p']").forEach(el=>el.addEventListener("change",up));
  },80);
}
function showUpload(){
  showModal("Upload Files",
    `<div id="drop-zone" onclick="document.getElementById('uinp').click()"><div style="font-size:32px;margin-bottom:8px">📂</div>Click or drag & drop files here</div>
     <input id="uinp" type="file" multiple style="display:none"/>
     <div id="upstat" style="font-size:12px;color:var(--text-sub);margin-top:10px"></div>`,
    [{label:"Close",action:closeModal}]);
  setTimeout(()=>{
    const inp=document.getElementById("uinp");
    inp?.addEventListener("change",()=>uploadFiles(inp.files));
    const dz=document.getElementById("drop-zone");
    dz?.addEventListener("dragover",e=>{e.preventDefault();dz.classList.add("drag");});
    dz?.addEventListener("dragleave",()=>dz.classList.remove("drag"));
    dz?.addEventListener("drop",e=>{e.preventDefault();dz.classList.remove("drag");uploadFiles(e.dataTransfer.files);});
  },80);
}
async function uploadFiles(files){
  const st=document.getElementById("upstat");const fd=new FormData();fd.append("path",cwd);
  for(const f of files)fd.append("files",f);
  if(st)st.textContent="Uploading "+files.length+" file(s)…";
  const r=await fetch("/api/upload",{method:"POST",headers:{"X-VrDesk-Token":vrToken},body:fd}).then(r=>r.json());
  if(r.ok){if(st)st.innerHTML=`<span style="color:var(--green)">✓ ${r.saved.join(", ")}</span>`;toast("Uploaded "+r.saved.length,"ok");refresh();}
  else{if(st)st.innerHTML=`<span style="color:var(--red)">Error: ${esc(r.error)}</span>`;toast(r.error,"err");}
}
async function shareSelected(){
  if(!selected)return;
  const r=await api("/api/share?path="+encodeURIComponent(selected.path));
  if(r.ok){toast("Share opened","ok");return;}
  const link=window.location.origin+"/api/download?path="+encodeURIComponent(selected.path);
  showModal("Share — "+selected.name,
    `<label>LAN Link</label><input type="text" value="${esc(link)}" readonly onclick="this.select()"/>
     <img id="qi" src="" style="display:none;border-radius:8px;margin-top:10px" width="200"/>`,
    [{label:"Close",action:closeModal}]);
  const qr=await api("/api/qr?text="+encodeURIComponent(link));
  if(qr.qr_url){const i=document.getElementById("qi");if(i){i.src=qr.qr_url;i.style.display="block";}}
}
function downloadSelected(){if(!selected||selected.is_dir)return;const a=document.createElement("a");a.href="/api/download?path="+encodeURIComponent(selected.path);a.click();}

function showGitPanel(){
  showModal("Git Manager",
    `<div style="display:flex;gap:4px;margin-bottom:12px;flex-wrap:wrap">
       ${["status","log --oneline -15","diff","branch","pull","fetch","stash list"].map(c=>`<button class="mbtn" style="padding:4px 10px;font-size:11px" onclick="runGit('${c}')">${c.split(" ")[0]}</button>`).join("")}
     </div>
     <label>Clone Repository</label>
     <div class="git-url-wrap">
       <input id="git-url" type="text" placeholder="https://github.com/user/repo.git"/>
       <button class="git-paste-btn" onclick="pasteGitUrl()">📋</button>
     </div>
     <label>Folder Name (optional)</label>
     <input id="git-name" type="text" placeholder="leave blank for default"/>
     <button class="mbtn primary" style="width:100%;padding:8px;margin-bottom:4px" onclick="doGitClone()">⬇ Clone to current folder</button>
     <div id="git-out" class="git-out-box">Ready…</div>`,
    [{label:"Close",action:closeModal}]);
}
async function runGit(cmd){
  const el=document.getElementById("git-out");if(el)el.textContent="Running: git "+cmd+"…";
  const r=await api("/api/git",{method:"POST",body:{cmd,path:cwd}});
  if(el)el.textContent=r.output||r.error||"(no output)";
}
async function pasteGitUrl(){
  try{const txt=await navigator.clipboard.readText();const el=document.getElementById("git-url");if(el)el.value=txt;}
  catch{toast("Clipboard denied","err");}
}
async function doGitClone(){
  const url=document.getElementById("git-url")?.value.trim();
  const name=document.getElementById("git-name")?.value.trim();
  const el=document.getElementById("git-out");
  if(!url){toast("Enter repo URL","err");return;}
  if(el)el.textContent="Cloning… please wait";toast("Cloning…","info");
  const r=await api("/api/git/clone",{method:"POST",body:{url,dest:cwd,name}});
  if(el)el.textContent=r.output||r.error||"Done";
  if(r.ok){toast("Cloned!","ok");refresh();}else toast("Clone failed","err");
}

function showPkg(){
  showModal("Package Manager",
    `<div class="pkg-tabs"><span class="pkg-tab active" onclick="setPkgMgr('pip',this)">pip</span><span class="pkg-tab" onclick="setPkgMgr('apt',this)">apt</span><span class="pkg-tab" onclick="setPkgMgr('npm',this)">npm</span></div>
     <input id="pkg-name" type="text" placeholder="package name…"/>
     <div style="display:flex;gap:6px;margin-bottom:10px">
       <button class="mbtn primary" style="flex:1" onclick="doPkg('install')">⬇ Install</button>
       <button class="mbtn danger"  style="flex:1" onclick="doPkg('uninstall')">✕ Remove</button>
       <button class="mbtn"         style="flex:1" onclick="doPkgList()">☰ List</button>
     </div>
     <pre id="pkg-out" style="background:rgba(0,0,0,.3);border:1px solid var(--border);border-radius:8px;padding:12px;font-size:10px;max-height:200px;overflow-y:auto;white-space:pre-wrap;color:var(--text);min-height:50px">Ready…</pre>`,
    [{label:"Close",action:closeModal}]);
}
let pkgMgr="pip";
function setPkgMgr(m,el){pkgMgr=m;document.querySelectorAll(".pkg-tab").forEach(t=>t.classList.remove("active"));el.classList.add("active");}
async function doPkg(action){
  const pkg=document.getElementById("pkg-name")?.value.trim();const out=document.getElementById("pkg-out");
  if(!pkg){toast("Enter package name","err");return;}
  if(out)out.textContent=action+"ing "+pkg+"…";
  const r=await api("/api/pkg",{method:"POST",body:{mgr:pkgMgr,action,pkg}});
  if(out)out.textContent=r.output||r.error||"Done";
  if(r.ok)toast(pkg+" "+action+"ed","ok");else toast("Failed","err");
}
async function doPkgList(){
  const out=document.getElementById("pkg-out");if(out)out.textContent="Loading…";
  const r=await api("/api/pkg",{method:"POST",body:{mgr:pkgMgr,action:"list",pkg:"_"}});
  if(out)out.textContent=r.output||r.error||"(empty)";
}

async function showProcesses(){
  const d=await api("/api/processes");const procs=d.processes||[];
  const rows=procs.map(p=>`<tr>
    <td style="color:var(--blue);font-family:var(--mono)">${esc(p.pid)}</td>
    <td style="color:var(--green)">${esc(p.cpu)}%</td>
    <td style="color:var(--text-sub)">${esc(p.mem)}%</td>
    <td style="overflow:hidden;max-width:180px;text-overflow:ellipsis;white-space:nowrap;font-size:11px;font-family:var(--mono)">${esc(p.cmd)}</td>
    <td><button class="mbtn danger" style="padding:3px 8px;font-size:11px" onclick="killPid('${esc(p.pid)}')">✕</button></td>
  </tr>`).join("");
  showModal("Processes",
    `<div style="overflow-y:auto;max-height:360px"><table style="width:100%;font-size:12px;border-collapse:collapse">
      <thead><tr style="color:var(--text-dim);font-size:10px;letter-spacing:.5px;text-transform:uppercase">
        <th style="text-align:left;padding:6px 4px">PID</th><th>CPU</th><th>MEM</th>
        <th style="text-align:left">CMD</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>`,
    [{label:"Close",action:closeModal}]);
}
async function killPid(pid){const r=await api("/api/kill",{method:"POST",body:{pid}});if(r.ok){toast("Killed "+pid,"ok");closeModal();}else toast(r.error,"err");}

function termBoot(){
  appendTerm(`<span class="t-ok">  VrDesk V1.2 — File Manager</span>`);
  appendTerm(`<span class="t-info">  Type 'help' for commands · 'clear' to clear</span>`);
  appendTerm(`<span class="t-info">  ───────────────────────────────────────</span>`);
}
function toggleTerminal(){
  const m=document.getElementById("terminal-modal");m.classList.toggle("open");
  if(m.classList.contains("open"))setTimeout(()=>document.getElementById("term-input").focus(),80);
}
function termMax(){
  const m=document.getElementById("terminal-modal");
  m.style.height=m.style.height==="100vh"?"340px":"100vh";
  m.style.borderRadius=m.style.height==="100vh"?"0":"20px 20px 0 0";
}
const termInput=document.getElementById("term-input");
termInput.addEventListener("keydown",async e=>{
  if(e.key==="Enter"){
    const cmd=termInput.value.trim();if(!cmd)return;
    termHistory.push(cmd);termIdx=termHistory.length;
    appendTerm(`<span class="t-cmd">${esc(shortPath(cwd))} $ ${esc(cmd)}</span>`);
    termInput.value="";
    if(cmd==="clear"){document.getElementById("term-output").innerHTML="";return;}
    if(cmd==="help"){appendTerm(`<span class="t-info">  cd, clear, ls, pwd, cat, git, python3, node, pip, apt</span>`);return;}
    if(cmd.startsWith("cd ")){const dest=cmd.slice(3).trim();const np=dest.startsWith("/")?dest:(cwd==="/"?"/"+dest:cwd+"/"+dest);nav(np);appendTerm(`<span class="t-ok">  → ${esc(np)}</span>`);return;}
    const r=await api("/api/terminal",{method:"POST",body:{cmd,cwd}});
    if(r.output){appendTerm(`<span class="${r.returncode!==0?"t-err":"t-out"}">${esc(r.output)}</span>`);}
  }else if(e.key==="ArrowUp"){if(termIdx>0){termIdx--;termInput.value=termHistory[termIdx];}e.preventDefault();}
  else if(e.key==="ArrowDown"){if(termIdx<termHistory.length-1){termIdx++;termInput.value=termHistory[termIdx];}else{termIdx=termHistory.length;termInput.value="";}e.preventDefault();}
});
function appendTerm(html){const el=document.getElementById("term-output");el.innerHTML+=html+"\n";el.scrollTop=el.scrollHeight;}

function showCtxMenu(e,item){
  const m=document.getElementById("ctx-menu");
  m.style.display="block";
  m.style.left=Math.min(e.clientX,window.innerWidth-200)+"px";
  m.style.top=Math.min(e.clientY,window.innerHeight-290)+"px";
  m.innerHTML=`
    ${item.is_dir?`<div class="cm" onclick="nav('${esc(item.path)}');hideCtx()"><span class="ci">📁</span>Open</div>`
      :`<div class="cm" onclick="editSelected();hideCtx()"><span class="ci">✎</span>Edit</div>
        <div class="cm" onclick="runSelected();hideCtx()"><span class="ci">▶</span>Run</div>`}
    <div class="csep"></div>
    <div class="cm" onclick="renameSelected();hideCtx()"><span class="ci">✏</span>Rename</div>
    <div class="cm" onclick="copySelected();hideCtx()"><span class="ci">⎘</span>Copy</div>
    <div class="cm" onclick="moveSelected();hideCtx()"><span class="ci">✂</span>Cut</div>
    <div class="cm" onclick="pasteClipboard();hideCtx()"><span class="ci">⎙</span>Paste here</div>
    <div class="csep"></div>
    <div class="cm" onclick="zipSelected();hideCtx()"><span class="ci">📦</span>Compress</div>
    ${!item.is_dir&&(item.ext===".zip"||item.name.endsWith(".tar.gz"))?`<div class="cm" onclick="extractSelected();hideCtx()"><span class="ci">📤</span>Extract</div>`:""}
    <div class="csep"></div>
    <div class="cm" onclick="showProps();hideCtx()"><span class="ci">ℹ</span>Properties</div>
    <div class="cm" onclick="showChmod();hideCtx()"><span class="ci">🔑</span>Permissions</div>
    <div class="csep"></div>
    ${!item.is_dir?`<div class="cm" onclick="shareSelected();hideCtx()"><span class="ci">⇧</span>Share</div>
      <div class="cm" onclick="downloadSelected();hideCtx()"><span class="ci">⬇</span>Download</div>`:""}
    <div class="csep"></div>
    <div class="cm danger" onclick="deleteSelected();hideCtx()"><span class="ci">✕</span>Delete</div>`;
}
function hideCtx(){document.getElementById("ctx-menu").style.display="none";}
document.addEventListener("click",hideCtx);

let _st;
document.getElementById("searchbox").addEventListener("input",function(){
  clearTimeout(_st);const q=this.value.trim();
  if(!q){render(items);document.getElementById("st-count").textContent=items.length+" items";return;}
  _st=setTimeout(async()=>{
    const r=await api("/api/search?q="+encodeURIComponent(q)+"&path="+encodeURIComponent(cwd));
    const res=r.results||[];render(res);
    document.getElementById("st-count").textContent=res.length+" results";
  },350);
});

function toggleTheme(){
  document.body.classList.toggle("light");
  localStorage.setItem("vrd_theme",document.body.classList.contains("light")?"light":"dark");
}

document.addEventListener("keydown",e=>{
  const f=document.activeElement;
  if(f.tagName==="INPUT"||f.tagName==="TEXTAREA")return;
  if((e.ctrlKey||e.metaKey)&&e.key==="v")pasteClipboard();
  if((e.ctrlKey||e.metaKey)&&e.key==="c")copySelected();
  if((e.ctrlKey||e.metaKey)&&e.key==="x")moveSelected();
  if(e.key==="Delete")deleteSelected();
  if(e.key==="F2")renameSelected();
  if(e.key==="F5"){e.preventDefault();refresh();}
  if(e.key==="`")toggleTerminal();
});

function startClock(){
  const el=document.getElementById("clk");
  setInterval(()=>{
    const n=new Date();
    el.textContent=[n.getHours(),n.getMinutes(),n.getSeconds()].map(x=>String(x).padStart(2,"0")).join(":");
  },1000);
}

function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");}
let _tt;
function toast(msg,type="ok"){
  const t=document.getElementById("toast");t.textContent=msg;t.className=type;
  t.style.display="block";clearTimeout(_tt);_tt=setTimeout(()=>t.style.display="none",3200);
}

checkAuth();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")

if __name__ == "__main__":
    print(f"\n  VrDesk V1.2 — Modern Edition")
    print(f"  URL : http://localhost:8080")
    print(f"  PIN : 1234\n")
    app.run(host="0.0.0.0", port=8080, debug=False)
