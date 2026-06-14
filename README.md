<div align="center">

# 🖥️ VrDesk

### A Beautiful, Modern File Manager for Termux & NetHunter

**Browser-based · Glassmorphism UI · Built for Mobile Power Users**

![Version](https://img.shields.io/badge/version-1.2-7B5EA7?style=for-the-badge)
![Platform](https://img.shields.io/badge/platform-Termux%20%7C%20NetHunter-5B8DEF?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-4ade80?style=for-the-badge)
![Made by](https://img.shields.io/badge/made%20by-%40monuyadavfan-f472b6?style=for-the-badge)

</div>

---

## ✨ Features

VrDesk turns your Termux file system into a slick, desktop-grade file manager — right inside your browser. No more typing `ls`, `cd`, `mv` for everything.

| 📂 File Management | 💻 Developer Tools | 🎨 Experience |
|---|---|---|
| Browse, create, rename, move, copy, delete | Built-in code editor + runner (Python, Node, Shell, HTML) | Glassmorphism, Win11/Android-style UI |
| Multi-select with checkboxes | Popup terminal — run any command | Dark & Light themes |
| ZIP compress / extract | Git clone, status, log, pull, push | Smooth animations everywhere |
| Upload & download files | Package manager — pip / apt / npm | Fully responsive (mobile to desktop) |
| Search by name or content | Process manager — view & kill | PIN-protected login |
| chmod permission manager | Live storage usage meter | Multi-tab navigation |
| File sharing via QR code / LAN link | | Persistent bookmarks |

---

## 🚀 Quick Start

### 1️⃣ Install dependencies

```bash
pkg update && pkg install python git -y
```

### 2️⃣ Clone this repo

```bash
git clone https://github.com/monuyadavfan/vrdesk.git
cd vrdesk
```

### 3️⃣ Install Python requirements

```bash
pip install -r requirements.txt
```

### 4️⃣ Run VrDesk

```bash
python vrdesk_v1.2.py
```

### 5️⃣ Open in browser

```
http://localhost:8080
```

> 🔑 **Default PIN:** `1234`
> Change it in the source by updating the `PIN_HASH` variable.

---

## 📱 Access from Other Devices (Same WiFi)

VrDesk runs on `0.0.0.0:8080`, so you can open it from any device on the same network:

```
http://<your-phone-ip>:8080
```

Find your phone's IP with:

```bash
ip addr show wlan0
```

---

## 🛠️ Built With

- 🐍 **Python 3** + **Flask** — lightweight backend
- 🎨 **HTML / CSS / JS** — no frontend build tools needed, single file
- 🔤 **Inter** + **JetBrains Mono** — modern typography

---

## ⚠️ Security Note

VrDesk gives full file system access (within your home directory) to anyone who has the PIN and can reach the server. Use it on **trusted networks only**, and change the default PIN before exposing it beyond `localhost`.

---

## 🤝 Contributing

Pull requests, ideas, and bug reports are welcome! Feel free to fork and customize VrDesk for your own setup.

---

<div align="center">

### 💚 Made with ❤️ by [@monuyadavfan](https://github.com/monuyadavfan)

⭐ **Star this repo if VrDesk made your Termux life easier!** ⭐

</div>
