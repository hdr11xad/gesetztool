#!/usr/bin/env python3
"""Normfinder als Desktop-Anwendung (GTK 4, libadwaita, WebKitGTK).

Zeigt den Normfinder in einem eigenen Fenster, vollständig offline aus einem
lokalen Datenordner. Ein kleiner HTTP-Server auf 127.0.0.1 (zufälliger Port)
liefert die erzeugten Seiten aus, genau wie Caddy auf dem Server.
"""
import os
import sys
import threading
from functools import partial
from pathlib import Path

sys.path.insert(0, os.environ.get("NORMFINDER_PKG", "/app/share/normfinder"))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
from gi.repository import Adw, Gio, GLib, Gtk, WebKit  # noqa: E402

from http.server import ThreadingHTTPServer  # noqa: E402

from normfinder.desktop import DataManager  # noqa: E402
from normfinder.devserver import Handler  # noqa: E402

APP_ID = "de.fsr_jura_halle.Normfinder"
BASE = "/normfinder/"


class Window(Adw.ApplicationWindow):
    def __init__(self, app, data: DataManager, port: int):
        super().__init__(application=app, title="Normfinder", default_width=1200, default_height=860)
        self.data = data
        self.local = f"http://127.0.0.1:{port}/"
        self.home = f"http://127.0.0.1:{port}{BASE}"

        self.view = WebKit.WebView()
        settings = self.view.get_settings()
        settings.set_enable_developer_extras(False)
        settings.set_enable_back_forward_navigation_gestures(True)
        self.view.connect("decide-policy", self.on_policy)
        self.view.connect("notify::title", lambda v, _p: self.set_title(v.get_title() or "Normfinder"))

        header = Adw.HeaderBar()
        back = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Zurück (Alt+←)")
        back.connect("clicked", lambda _b: self.view.go_back())
        fwd = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Vor (Alt+→)")
        fwd.connect("clicked", lambda _b: self.view.go_forward())
        home = Gtk.Button(icon_name="go-home-symbolic", tooltip_text="Startseite")
        home.connect("clicked", lambda _b: self.view.load_uri(self.home))
        for b in (back, fwd, home):
            header.pack_start(b)

        self.banner = Adw.Banner(button_label="Neu laden")
        self.banner.connect("button-clicked", lambda _b: (self.view.reload(), self.banner.set_revealed(False)))

        # Erster Start: Fortschritt statt leerer Seite
        self.status = Adw.StatusPage(icon_name=APP_ID, title="Gesetze werden geladen",
                                     description="Beim ersten Start lädt der Normfinder die Gesetze von "
                                                 "gesetze-im-internet.de. Die Kerngesetze sind in etwa "
                                                 "einer Minute bereit, das übrige Bundesrecht folgt im Hintergrund.")
        self.bar = Gtk.ProgressBar(show_text=True, width_request=420, halign=Gtk.Align.CENTER)
        self.status.set_child(self.bar)

        self.stack = Gtk.Stack()
        self.stack.add_named(self.status, "status")
        self.stack.add_named(self.view, "web")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.banner)
        box.append(self.stack)
        view = Adw.ToolbarView(content=box)
        view.add_top_bar(header)
        self.set_content(view)

        keys = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL)
        for accel, fn in (("<Alt>Left", self.view.go_back), ("<Alt>Right", self.view.go_forward),
                          ("<Control>r", self.view.reload), ("F5", self.view.reload)):
            keys.add_shortcut(Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string(accel),
                                           action=Gtk.CallbackAction.new(lambda *_a, f=fn: (f(), True)[1])))
        self.add_controller(keys)

        if data.ready():
            self.show_site()
        threading.Thread(target=self.work, daemon=True).start()

    # -- Seiten -----------------------------------------------------------

    def show_site(self):
        if self.stack.get_visible_child_name() != "web":
            self.view.load_uri(self.home)
            self.stack.set_visible_child_name("web")

    def on_policy(self, view, decision, kind):
        """Links nach außen (FSR-Website, amtliche Fassung …) im Standardbrowser öffnen."""
        if kind in (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
            uri = decision.get_navigation_action().get_request().get_uri()
            if not uri.startswith(self.local) and not uri.startswith("about:"):
                Gtk.UriLauncher.new(uri).launch(self, None, None, None)
                decision.ignore()
                return True
        return False

    # -- Hintergrundarbeit ------------------------------------------------

    def work(self):
        for step in self.data.plan():
            ok = self.data.run(step, lambda p: GLib.idle_add(self.progress, p))
            if step == "core" and ok:
                GLib.idle_add(self.show_site)
            elif step in ("full", "update") and ok and self.data.complete():
                GLib.idle_add(self.done, step)
            elif not ok:
                GLib.idle_add(self.failed, step)
                break

    def progress(self, p):
        if self.stack.get_visible_child_name() == "status":
            self.bar.set_text(p.text)
            if p.fraction is None:
                self.bar.pulse()
            else:
                self.bar.set_fraction(p.fraction)
        return False

    def done(self, step):
        if self.stack.get_visible_child_name() == "web":
            st = self.data.stats()
            self.banner.set_title(f"Alle {st.get('laws', '')} Gesetze sind jetzt verfügbar."
                                  if step == "full" else "Neue Gesetzesfassungen sind verfügbar.")
            self.banner.set_revealed(True)
        else:
            self.show_site()
        return False

    def failed(self, step):
        if self.data.ready():
            self.banner.set_title("Aktualisierung fehlgeschlagen – der bisherige Stand bleibt. "
                                  "Beim nächsten Start wird es erneut versucht.")
            self.banner.set_button_label("")
            self.banner.set_revealed(True)
            self.show_site()
        else:
            self.status.set_title("Laden fehlgeschlagen")
            self.status.set_description("Die Gesetze konnten nicht geladen werden. Bitte die "
                                        "Internetverbindung prüfen und den Normfinder neu starten.")
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        root = Path(GLib.get_user_data_dir()) / "normfinder"
        self.data = DataManager(root)
        handler = partial(Handler, root=self.data.site, base=BASE)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def do_activate(self):
        win = self.get_active_window() or Window(self, self.data, self.httpd.server_address[1])
        win.present()

    def do_shutdown(self):
        self.data.stop()  # laufendes Laden/Erzeugen beenden; der alte Stand bleibt gültig
        self.httpd.shutdown()
        Adw.Application.do_shutdown(self)


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
