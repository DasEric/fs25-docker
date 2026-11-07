import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

import common
import install
import server
from web import Forms, Web, start_payload


def iso_fixture(name=b"SETUP.EXE;1", content=b"fixture"):
    image = bytearray(22 * 2048)
    image[32768:32775] = b"\x01CD001\x01"
    image[32768 + 158:32768 + 162] = (20).to_bytes(4, "little")
    image[32768 + 166:32768 + 170] = (2048).to_bytes(4, "little")
    offset = 20 * 2048
    image[offset] = 33 + len(name)
    image[offset + 2:offset + 6] = (21).to_bytes(4, "little")
    image[offset + 10:offset + 14] = len(content).to_bytes(4, "little")
    image[offset + 32] = len(name)
    image[offset + 33:offset + 33 + len(name)] = name
    image[21 * 2048:21 * 2048 + len(content)] = content
    return image


class InstallerTests(unittest.TestCase):
    def test_extract_primary_iso(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            disc = root / "disc.img"
            disc.write_bytes(iso_fixture())
            install.extract_iso(disc, root)
            self.assertEqual((root / "SETUP.EXE").read_bytes(), b"fixture")

    def test_invalid_and_unsafe_iso(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            disc = root / "disc.img"
            disc.write_bytes(iso_fixture(b"../BAD;1"))
            with self.assertRaisesRegex(common.Failure, "Invalid filename"):
                install.extract_iso(disc, root)
            disc.write_bytes(iso_fixture()[:-2048])
            with self.assertRaisesRegex(common.Failure, "Truncated"):
                install.extract_iso(disc, root)

    def test_download_hosts(self):
        self.assertTrue(install.allowed("https://cdn16.giants-software.com/FarmingSimulator25.img", install.cdn))
        for url in ("http://cdn16.giants-software.com/game.img", "https://evil.test/game.img",
                    "https://user@cdn16.giants-software.com/game.img", "https://cdn16.giants-software.com:8443/"):
            self.assertFalse(install.allowed(url, install.cdn))

    def test_failed_setup_restores_old_game_and_leaves_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root / "game"
            game.mkdir()
            for name in ("dedicatedServer.exe", "dedicatedServer.xml", "FarmingSimulator2025.exe"):
                (game / name).write_text("old")
            marker = game / ".fs25-install.json"
            marker.write_text(json.dumps({"source": "old.img", "proton": common.DEFAULT_PROTON}))
            unpacked = root / "unpacked"
            unpacked.mkdir()
            (unpacked / "Setup.exe").write_text("installer")
            with (patch.multiple(install, GAME=game, MARKER=marker, WORK=root / "work", SECRETS=root / ".secrets"),
                  patch.object(install, "drop_installer_root"),
                  patch.object(install, "secret", side_effect=lambda name: (
                      "https://cdn16.giants-software.com/new.img" if name == "download-url" else "")),
                  patch.object(install, "unpack", return_value=unpacked),
                  patch.object(install, "ensure_proton"),
                  patch.object(install, "run_setup", side_effect=common.Failure("fixture failure"))):
                with self.assertRaisesRegex(common.Failure, "fixture failure"):
                    install.install()
                self.assertEqual(install.installed()["source"], "old.img")
            self.assertEqual((game / "dedicatedServer.exe").read_text(), "old")
            self.assertTrue((unpacked / "Setup.exe").is_file())


class ConfigTests(unittest.TestCase):
    def test_xml_escapes_credentials_and_updates_ports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            web = root / "dedicatedServer.xml"
            web.write_text('<root><!-- retained --><webserver port="8080"><tls port="8443" active="false"/>'
                           '<initial_admin><username>admin</username><password>old</password>'
                           '</initial_admin></webserver></root>')
            game = root / "dedicated_server" / "dedicatedServerConfig.xml"
            game.parent.mkdir()
            game.write_text("<game><port>10823</port></game>")
            with patch.multiple(server, GAME=root, PROFILE=root):
                server.configure_web(18080, 18443, True, "a&b", "<&> password")
                self.assertTrue(server.configure_game_port(20823))
                self.assertEqual(server.web_password(), "<&> password")
            self.assertIn("a&amp;b", web.read_text())
            self.assertIn("<!-- retained -->", web.read_text())
            self.assertIn('active="true"', web.read_text())
            self.assertIn('port="18443"', web.read_text())
            self.assertIn("<port>20823</port>", game.read_text())

    def test_egg_schema_and_runtime_contract(self):
        root = Path(__file__).resolve().parents[1]
        egg = json.loads((root / "egg-farming-simulator-25.json").read_text(encoding="utf-8"))
        self.assertEqual(egg["meta"]["version"], "PTDL_v2")
        self.assertEqual(json.loads(egg["config"]["startup"])["done"], server.READY)
        self.assertEqual(egg["config"]["stop"], "^SIGTERM")
        self.assertEqual(egg["scripts"]["installation"]["script"],
                         "exec /usr/bin/python3 /opt/fs25/server.py install\n")
        runtime = next(iter(egg["docker_images"].values()))
        self.assertEqual(egg["scripts"]["installation"]["container"], runtime.removesuffix(":latest") + ":installer")
        variables = {item["env_variable"]: item["default_value"] for item in egg["variables"]}
        self.assertEqual(len(variables), len(egg["variables"]))
        self.assertEqual(variables["FS25_PROTON_VERSION"], common.DEFAULT_PROTON)
        self.assertEqual((variables["FS25_WEB_PORT"], variables["FS25_TLS_PORT"]), ("8080", "8443"))
        self.assertFalse(any("PASSWORD" in variable or "ACTIVATION" in variable for variable in variables))


LOGIN = '<form method="post"><input name="username"><input name="password"><button name="login">Login</button></form>'
CONFIGURE = """<form method="post">
<input type="hidden" name="csrf" value="session-token">
<input name="game_name" value="Farm &amp; Fields">
<input name="server_port" value="10823">
<input type="checkbox" name="crossplay_allowed" checked>
<input type="checkbox" name="other" value="yes" checked>
<select name="savegame"><option value="1">First<option selected value="2">Second</select>
<button name="start_server" value="Start">Start</button></form>"""
RUNNING = '<form method="post"><input type="hidden" name="csrf" value="session-token"><button name="stop_server">Stop</button></form>'


class WebTests(unittest.TestCase):
    def test_preserve_settings_and_override_only_nonempty(self):
        form = Forms(LOGIN + CONFIGURE).find("start_server")
        payload = parse_qs(start_payload(form, 20823, {"game_name": "", "crossplay_allowed": "false"}).decode())
        self.assertEqual(payload, {"csrf": ["session-token"], "game_name": ["Farm & Fields"],
                                   "server_port": ["20823"], "other": ["yes"],
                                   "savegame": ["2"], "start_server": ["Start"]})

    def test_login_autostart_and_graceful_stop(self):
        state = {"running": False, "login": False}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_page(self, page, cookie=False):
                self.send_response(200)
                if cookie:
                    self.send_header("Set-Cookie", "session=fixture; Path=/")
                self.end_headers()
                self.wfile.write(page.encode())

            def do_GET(self):
                self.send_page((RUNNING if state["running"] else CONFIGURE)
                               if self.headers.get("Cookie") == "session=fixture" else LOGIN)

            def do_POST(self):
                data = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
                if data.get("password") == ["p&ss"] and data.get("username") == ["admin"]:
                    state["login"] = True
                    self.send_page(CONFIGURE, cookie=True)
                elif self.headers.get("Cookie") == "session=fixture" and data.get("csrf") == ["session-token"]:
                    state["running"] = "start_server" in data
                    state["last"] = data
                    self.send_page(RUNNING if state["running"] else CONFIGURE)
                else:
                    self.send_page(LOGIN)

        class Process:
            def poll(self):
                return None

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as httpd:
            thread = threading.Thread(target=httpd.serve_forever)
            thread.start()
            try:
                client = Web(f"http://127.0.0.1:{httpd.server_port}")
                with contextlib.redirect_stdout(io.StringIO()) as log:
                    server.autostart(client, "admin", "p&ss", 20823, False, {"game_name": "Demo"}, Process())
                    self.assertTrue(state["running"] and state["login"])
                    self.assertEqual(state["last"]["server_port"], ["20823"])
                    self.assertEqual(state["last"]["game_name"], ["Demo"])
                    server.stop_game(client, "admin", "p&ss")
                    self.assertFalse(state["running"])
                self.assertIn(server.GAME_READY, log.getvalue())
                self.assertIn("stopped through the web interface", log.getvalue())
            finally:
                httpd.shutdown()
                thread.join()
