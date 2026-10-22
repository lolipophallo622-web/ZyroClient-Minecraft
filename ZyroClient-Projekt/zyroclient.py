"""ZyroClient - Mod-Client für Minecraft mit Modrinth & CurseForge.

Start:  python zyroclient.py   (Python 3.9+, keine weiteren Pakete nötig)
Mods landen standardmäßig in ~/.minecraft/mods (im Tab Einstellungen änderbar),
funktionieren also mit jedem Launcher. CurseForge braucht einen kostenlosen
API-Key von https://console.curseforge.com
"""
import json, os, sys, threading, subprocess, urllib.request, urllib.parse
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

UA = {"User-Agent": "ZyroClient/1.0"}
CFG = os.path.join(os.path.expanduser("~"), ".zyroclient.json")
LOADERS = {"fabric": 4, "forge": 1, "quilt": 5, "neoforge": 6}  # CurseForge-IDs
VERSIONS = ["1.21.4", "1.21.1", "1.20.4", "1.20.1", "1.19.4", "1.18.2", "1.16.5", "1.12.2"]


def default_dir():
    base = os.environ.get("APPDATA") if sys.platform == "win32" else os.path.expanduser(
        "~/Library/Application Support" if sys.platform == "darwin" else "~")
    return os.path.join(base, "minecraft" if sys.platform != "linux" else ".minecraft", "mods")


def load_cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"cf_key": "", "mods_dir": default_dir()}


def save_cfg(c):
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(c, f)


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def download(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())


class Source:
    """Gemeinsame Schnittstelle: search() -> [(titel, id, info)], file() -> (url, name)"""


class Modrinth(Source):
    def search(self, q, ver, loader):
        facets = [["project_type:mod"], [f"versions:{ver}"], [f"categories:{loader}"]]
        url = "https://api.modrinth.com/v2/search?" + urllib.parse.urlencode(
            {"query": q, "limit": 25, "facets": json.dumps(facets)})
        return [(h["title"], h["project_id"], f'{h["downloads"]:,} Downloads – {h["description"]}')
                for h in get_json(url)["hits"]]

    def file(self, pid, ver, loader):
        qs = urllib.parse.urlencode({"game_versions": json.dumps([ver]), "loaders": json.dumps([loader])})
        vs = get_json(f"https://api.modrinth.com/v2/project/{pid}/version?{qs}")
        if not vs:
            raise RuntimeError("Keine passende Version gefunden.")
        f = next((x for x in vs[0]["files"] if x.get("primary")), vs[0]["files"][0])
        return f["url"], f["filename"]


class CurseForge(Source):
    def __init__(self, key):
        self.h = {"x-api-key": key}

    def search(self, q, ver, loader):
        if not self.h["x-api-key"]:
            raise RuntimeError("Bitte zuerst den CurseForge-API-Key in den Einstellungen eintragen.")
        qs = urllib.parse.urlencode({"gameId": 432, "classId": 6, "searchFilter": q, "gameVersion": ver,
                                     "modLoaderType": LOADERS[loader], "pageSize": 25,
                                     "sortField": 2, "sortOrder": "desc"})
        d = get_json("https://api.curseforge.com/v1/mods/search?" + qs, self.h)["data"]
        return [(m["name"], m["id"], f'{m["downloadCount"]:,.0f} Downloads – {m["summary"]}') for m in d]

    def file(self, mid, ver, loader):
        qs = urllib.parse.urlencode({"gameVersion": ver, "modLoaderType": LOADERS[loader]})
        d = get_json(f"https://api.curseforge.com/v1/mods/{mid}/files?{qs}", self.h)["data"]
        if not d:
            raise RuntimeError("Keine passende Datei gefunden.")
        if not d[0].get("downloadUrl"):
            raise RuntimeError("Der Autor erlaubt keinen Download über Drittanbieter-Apps.")
        return d[0]["downloadUrl"], d[0]["fileName"]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ZyroClient")
        self.geometry("860x560")
        self.cfg = load_cfg()
        self.results = []
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        self.mods_tab, self.inst_tab, self.set_tab = ttk.Frame(tabs), ttk.Frame(tabs), ttk.Frame(tabs)
        tabs.add(self.mods_tab, text="Mods durchsuchen")
        tabs.add(self.inst_tab, text="Installiert")
        tabs.add(self.set_tab, text="Einstellungen")
        self.build_mods(); self.build_installed(); self.build_settings()
        self.status = tk.StringVar(value="Bereit.")
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill="x", padx=8, pady=4)

    # ---- Mods ----
    def build_mods(self):
        t = self.mods_tab
        bar = ttk.Frame(t); bar.pack(fill="x", padx=8, pady=8)
        self.src = ttk.Combobox(bar, values=["Modrinth", "CurseForge"], state="readonly", width=11)
        self.src.set("Modrinth"); self.src.pack(side="left")
        self.ver = ttk.Combobox(bar, values=VERSIONS, width=8); self.ver.set(VERSIONS[0]); self.ver.pack(side="left", padx=4)
        self.ldr = ttk.Combobox(bar, values=list(LOADERS), state="readonly", width=9)
        self.ldr.set("fabric"); self.ldr.pack(side="left")
        self.q = ttk.Entry(bar); self.q.pack(side="left", fill="x", expand=True, padx=4)
        self.q.bind("<Return>", lambda e: self.search())
        ttk.Button(bar, text="Suchen", command=self.search).pack(side="left")
        self.lb = tk.Listbox(t, activestyle="none"); self.lb.pack(fill="both", expand=True, padx=8)
        self.lb.bind("<Double-Button-1>", lambda e: self.install())
        ttk.Button(t, text="Ausgewählte Mod installieren", command=self.install).pack(pady=8)

    def provider(self):
        return Modrinth() if self.src.get() == "Modrinth" else CurseForge(self.cfg["cf_key"])

    def run(self, fn, done=None):
        def work():
            try:
                res = fn()
                self.after(0, lambda: done(res) if done else None)
            except Exception as e:
                self.after(0, lambda: (self.status.set("Fehler"), messagebox.showerror("ZyroClient", str(e))))
        threading.Thread(target=work, daemon=True).start()

    def search(self):
        p, v, l, q = self.provider(), self.ver.get(), self.ldr.get(), self.q.get()
        self.status.set("Suche läuft …")
        def done(res):
            self.results = res
            self.lb.delete(0, "end")
            for name, _, info in res:
                self.lb.insert("end", f"{name}  —  {info[:110]}")
            self.status.set(f"{len(res)} Ergebnisse.")
        self.run(lambda: p.search(q, v, l), done)

    def install(self):
        sel = self.lb.curselection()
        if not sel:
            return
        name, pid, _ = self.results[sel[0]]
        p, v, l = self.provider(), self.ver.get(), self.ldr.get()
        self.status.set(f"Installiere {name} …")
        def job():
            url, fn = p.file(pid, v, l)
            os.makedirs(self.cfg["mods_dir"], exist_ok=True)
            download(url, os.path.join(self.cfg["mods_dir"], fn))
            return fn
        def done(fn):
            self.status.set(f"Installiert: {fn}"); self.refresh_installed()
        self.run(job, done)

    # ---- Installiert ----
    def build_installed(self):
        t = self.inst_tab
        self.ilb = tk.Listbox(t); self.ilb.pack(fill="both", expand=True, padx=8, pady=8)
        row = ttk.Frame(t); row.pack(pady=8)
        ttk.Button(row, text="Entfernen", command=self.remove).pack(side="left", padx=4)
        ttk.Button(row, text="Ordner öffnen", command=self.open_dir).pack(side="left", padx=4)
        self.refresh_installed()

    def refresh_installed(self):
        self.ilb.delete(0, "end")
        d = self.cfg["mods_dir"]
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".jar"):
                    self.ilb.insert("end", f)

    def remove(self):
        sel = self.ilb.curselection()
        if sel and messagebox.askyesno("ZyroClient", "Mod wirklich löschen?"):
            os.remove(os.path.join(self.cfg["mods_dir"], self.ilb.get(sel[0])))
            self.refresh_installed()

    def open_dir(self):
        d = self.cfg["mods_dir"]; os.makedirs(d, exist_ok=True)
        if sys.platform == "win32": os.startfile(d)
        else: subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", d])

    # ---- Einstellungen ----
    def build_settings(self):
        t = self.set_tab
        ttk.Label(t, text="CurseForge API-Key:").pack(anchor="w", padx=12, pady=(12, 0))
        self.key = ttk.Entry(t, show="•"); self.key.insert(0, self.cfg["cf_key"]); self.key.pack(fill="x", padx=12)
        ttk.Label(t, text="Mods-Ordner:").pack(anchor="w", padx=12, pady=(12, 0))
        self.dir = ttk.Entry(t); self.dir.insert(0, self.cfg["mods_dir"]); self.dir.pack(fill="x", padx=12)
        ttk.Button(t, text="Ordner wählen …", command=lambda: self.pick()).pack(anchor="w", padx=12, pady=4)
        ttk.Button(t, text="Speichern", command=self.save).pack(anchor="w", padx=12, pady=12)

    def pick(self):
        d = filedialog.askdirectory()
        if d: self.dir.delete(0, "end"); self.dir.insert(0, d)

    def save(self):
        self.cfg = {"cf_key": self.key.get().strip(), "mods_dir": self.dir.get().strip()}
        save_cfg(self.cfg); self.refresh_installed(); self.status.set("Gespeichert.")


if __name__ == "__main__":
    App().mainloop()
