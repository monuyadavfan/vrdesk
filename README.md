<div align="center">

# 🖥️ VrDesk V1.4

### Ultimate File Manager for Termux & NetHunter

**Browser-based · Glassmorphism UI · Built for Mobile Power Users**

![Version](https://img.shields.io/badge/version-1.4-7B5EA7?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Termux%20%7C%20NetHunter-5B8DEF?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.x-4ade80?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-f472b6?style=for-the-badge)
![Made by](https://img.shields.io/badge/made%20by-%40monuyadavfan-fbbf24?style=for-the-badge)

</div>

---

## ✨ What is VrDesk?

VrDesk turns your **Termux** into a powerful, desktop-grade file manager — right inside your phone browser. No PC needed. Just open the URL and start working!

---

## 🚀 Full Setup Guide — Termux Se Lekar VrDesk Run Tak

### Step 1 — Termux Install Karo

1. **F-Droid** se Termux download karo (recommended):
   - 👉 https://f-droid.org/packages/com.termux/
   - Play Store wala Termux outdated hai — use mat karo!

2. Install hone ke baad Termux open karo

---

### Step 2 — Termux Setup Karo

Termux open karo aur yeh commands ek ek karke chalaao:

```bash
# Packages update karo
pkg update && pkg upgrade -y

# Storage permission do (zaroor karo!)
termux-setup-storage

# Basic tools install karo
pkg install python git wget curl -y
```

> ⚠️ `termux-setup-storage` chalane ke baad phone mein permission popup aayega — **Allow** karo

---

### Step 3 — VrDesk Files Download Karo

```bash
# Ek folder banao
mkdir ~/vrdesk
cd ~/vrdesk
```

Ab **dono files** is folder mein daalo:
- `vrdesk_v1.4.py`
- `vrdesk_v1.4.html`

**GitHub se clone karne ka option (agar repo hai):**
```bash
git clone https://github.com/monuyadavfan/vrdesk.git
cd vrdesk
```

---

### Step 4 — Python Dependencies Install Karo

```bash
cd ~/vrdesk

# Flask install karo (required)
pip install flask

# yt-dlp install karo (video download ke liye)
pip install yt-dlp

# Ya ek saath dono:
pip install -r requirements.txt
```

---

### Step 5 — Optional Tools Install Karo

Yeh optional hain lekin kuch features ke liye zaroori hain:

```bash
# .7z files extract karne ke liye
pkg install p7zip -y

# .rar files extract karne ke liye
pkg install unrar -y

# Cloudflared tunnel ke liye (public URL banane ke liye)
pkg install cloudflared -y

# Termux share feature ke liye
pkg install termux-api -y
apt install termux-api -y
```

---

### Step 6 — VrDesk Run Karo

```bash
cd ~/vrdesk
python vrdesk_v1.4.py
```

Yeh output dikhega:
```
══════════════════════════════════════════════════
  VrDesk V1.4 — Ultimate Edition
══════════════════════════════════════════════════
  URL     : http://localhost:8080
  HTML    : /data/data/com.termux/files/home/vrdesk/vrdesk_v1.4.html
  PIN     : 1234 (change in Settings)
══════════════════════════════════════════════════
```

---

### Step 7 — Browser Mein Kholo

Apne phone ke browser mein yeh URL kholo:

```
http://localhost:8080
```

**Default PIN:** `1234`

> 💡 **Tip:** VrDesk ko same WiFi network ke doosre devices se bhi access kar sakte ho!
> Apna phone IP pata karo: `ip addr show wlan0`
> Phir kisi bhi device par: `http://<phone-ip>:8080`

---

## 📁 File Structure

```
vrdesk/
├── vrdesk_v1.4.py      ← Backend (Flask server + all APIs)
├── vrdesk_v1.4.html    ← Frontend (complete UI)
├── requirements.txt    ← Python dependencies
└── README.md           ← Yeh file
```

> ⚠️ **Zaroori:** `.py` aur `.html` dono ek hi folder mein honi chahiye!

---

## 🌟 Features — V1.4

| Category | Features |
|----------|---------|
| 📂 **File Manager** | Browse, create, rename, move, copy, delete |
| 🗑️ **Recycle Bin** | Delete hone par trash mein, restore kar sako |
| 📝 **Editor** | Built-in code editor — Python, JS, Shell, HTML |
| ▶️ **Code Runner** | Files yahi se run karo, output dekho |
| 🎬 **Media Viewer** | Image, Video, Audio, PDF viewer |
| 📊 **CSV Viewer** | Table format mein CSV dekho |
| 📄 **Markdown Preview** | README files rendered dekho |
| ⬇️ **Video Downloader** | YouTube, Instagram, TikTok, Facebook + direct links |
| 📦 **Archive Support** | ZIP, TAR, 7Z, RAR compress/extract |
| 🌐 **Tunnel Manager** | Cloudflared + ngrok public URL |
| 🌐 **LAN Server** | Folder share karo local network mein |
| ⌨️ **Terminal** | Built-in terminal popup |
| ⌬ **Git Manager** | Clone, status, pull, log — sab GUI se |
| 📦 **Package Manager** | pip / apt / npm install GUI se |
| 🏷️ **File Tags** | Custom tags lagao files par |
| 🔐 **Encryption** | AES-256 se files encrypt/decrypt karo |
| 📊 **Dashboard** | CPU, RAM, Storage live monitor |
| 📊 **Storage Analytics** | Kaun sa folder kitna space le raha hai |
| 🗂️ **Multi-tab** | Multiple folders ek saath |
| 🎨 **5 Themes** | Dark, Light, Dracula, Nord, Catppuccin |
| 📝 **Quick Notes** | Sticky notes — files se alag |
| ⏰ **Cron Manager** | Scheduled tasks GUI se |
| ✏️ **Bulk Rename** | Pattern se multiple files rename |
| 🔖 **Bookmarks** | Favorite folders quick access |
| 📱 **Storage Access** | Phone storage + Downloads + DCIM sab |

---

## ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `` ` `` | Terminal toggle |
| `F1` | Dashboard |
| `F2` | Rename |
| `F5` | Refresh |
| `Ctrl+C` | Copy |
| `Ctrl+X` | Cut |
| `Ctrl+V` | Paste |
| `Delete` | Move to Trash |
| `Escape` | Close modal |

---

## 🔐 Default PIN Change Karna

1. VrDesk kholo → **⚙ Set** button → Settings
2. "Change PIN" section mein:
   - Current PIN: `1234`
   - New PIN: apna naya PIN daalo
3. Save karo — automatically logout hoga
4. Naye PIN se login karo

---

## 📱 Access From Other Devices (Same WiFi)

```bash
# Apna phone ka IP pata karo
ip addr show wlan0
# ya
ifconfig wlan0
```

Phir kisi bhi device (laptop, tablet) par:
```
http://<phone-ip>:8080
```

---

## 🌐 Public URL Banana (Tunnel)

```bash
# Cloudflared install karo
pkg install cloudflared -y

# VrDesk mein Tunnel button click karo
# Cloudflared select karo → Start Tunnel
# Public URL mil jayega!
```

---

## 🎬 Video Download Karna

1. Topbar mein **⬇ DL** button click karo
2. URL paste karo (YouTube/Instagram/TikTok/Facebook/direct link)
3. Quality choose karo
4. **Start Download** click karo

**Supported Sites (1000+):**
- YouTube, Instagram, TikTok, Facebook, Twitter/X
- Vimeo, Dailymotion, Reddit aur bahut saare
- Direct MP4/MP3/ZIP links bhi kaam karte hain

---

## ❗ Common Errors & Solutions

| Error | Solution |
|-------|---------|
| `ModuleNotFoundError: flask` | `pip install flask` chalaao |
| `ModuleNotFoundError: yt-dlp` | `pip install yt-dlp` chalaao |
| `.html file not found` | `.py` aur `.html` ek folder mein rakhho |
| `Permission denied` | `termux-setup-storage` chalaao |
| `Port already in use` | `pkill -f vrdesk` phir dobara run karo |
| `7z not found` | `pkg install p7zip` chalaao |
| `unrar not found` | `pkg install unrar` chalaao |
| Tunnel nahi chal raha | `pkg install cloudflared` chalaao |

---

## 🔄 Background Mein Chalana

Termux band karne par bhi VrDesk chalta rahe:

```bash
# nohup se background mein chalao
nohup python vrdesk_v1.4.py &

# Band karna ho to
pkill -f vrdesk_v1.4.py
```

---

## 📋 Quick Commands Reference

```bash
# VrDesk start karo
cd ~/vrdesk && python vrdesk_v1.4.py

# Background mein start karo
cd ~/vrdesk && nohup python vrdesk_v1.4.py &

# Band karo
pkill -f vrdesk_v1.4.py

# Update karo (agar git use kar rahe ho)
cd ~/vrdesk && git pull

# Dependencies update karo
pip install --upgrade flask yt-dlp
```

---

<div align="center">

### 💜 Made with ❤️ by [@monuyadavfan](https://github.com/monuyadavfan)

⭐ **Agar VrDesk useful laga to GitHub par Star zaroor do!** ⭐

</div>
