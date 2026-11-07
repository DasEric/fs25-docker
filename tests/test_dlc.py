import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import common
import dlc
import install


IMG = "https://cdn20.giants-software.com/FarmingSimulator25/FarmingSimulator25_1_25_1_0_ESD.img"
DLC = "https://cdn20.giants-software.com/FarmingSimulator25/FarmingSimulator25_pumps_1_0_ESD.exe"
KEY = "ABCDE-12345-FGHIJ-67890"


def pe_fixture():
    return b"MZ" + b"\0" * 58 + (64).to_bytes(4, "little") + b"PE\0\0" + b"fixture"


def iso_fixture(data):
    sector = 2048

    def both(value, size):
        return value.to_bytes(size, "little") + value.to_bytes(size, "big")

    def record(name, lba, size, flags):
        return (bytes((33 + len(name) + (len(name) % 2 == 0), 0)) + both(lba, 4) + both(size, 4)
                + bytes((126, 11, 7, 12, 0, 0, 0, flags, 0, 0)) + both(1, 2) + bytes((len(name),))
                + name + (b"\0" if len(name) % 2 == 0 else b""))

    disc = bytearray(sector * 22)
    pvd = memoryview(disc)[16 * sector:17 * sector]
    pvd[:7] = b"\x01CD001\x01"
    pvd[8:72] = b"FS25 DLC FIXTURE".ljust(64)
    pvd[80:88] = both(22, 4)
    pvd[120:132] = both(1, 2) + both(1, 2) + both(sector, 2)
    pvd[132:140] = both(10, 4)
    pvd[140:144] = (18).to_bytes(4, "little")
    pvd[148:152] = (19).to_bytes(4, "big")
    root = record(b"\0", 20, sector, 2)
    pvd[156:190] = root
    pvd[881] = 1
    disc[17 * sector:17 * sector + 7] = b"\xffCD001\x01"
    for lba, order in ((18, "little"), (19, "big")):
        table = b"\x01\x00" + (20).to_bytes(4, order) + (1).to_bytes(2, order) + b"\0\0"
        disc[lba * sector:lba * sector + len(table)] = table
    directory = root + record(b"\x01", 20, sector, 2) + record(b"SETUP.EXE;1", 21, len(data), 0)
    disc[20 * sector:20 * sector + len(directory)] = directory
    disc[21 * sector:21 * sector + len(data)] = data
    return disc


class PanelSettingsTests(unittest.TestCase):
    def test_panel_base_key_overrides_protected_file_and_is_not_forwarded_to_proton(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "activation-key"
            source.write_text("FILE-KEY")
            source.chmod(0o600)
            with (patch.multiple(common, ROOT=root, SECRETS=root, PROTON=root / ".proton"),
                  patch.dict(os.environ, {"FS25_PRODUCT_KEY": "", "FS25_DOWNLOAD_URL": IMG,
                                          "FS25_DLC_PRODUCT_KEYS": "pumps=" + KEY,
                                          "FS25_DLC_INSTALL_SOURCES": "pumps=" + DLC})):
                self.assertEqual(common.product_key(), "FILE-KEY")
                with patch.dict(os.environ, {"FS25_PRODUCT_KEY": KEY}):
                    self.assertEqual(common.product_key(), KEY)
                    self.assertTrue(common.PANEL_PRIVATE.isdisjoint(common.proton_env(common.DEFAULT_PROTON)))

    def test_supplied_img_bypasses_portal_and_updates_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            extracted = root / "extracted"
            extracted.mkdir()
            (extracted / "Setup.exe").write_bytes(pe_fixture())
            game = root / "game"
            marker = game / ".fs25-install.json"

            def setup(exe, tag):
                self.assertEqual(exe, extracted / "Setup.exe")
                for name in ("dedicatedServer.exe", "FarmingSimulator2025.exe", "dedicatedServer.xml"):
                    (game / name).write_bytes(b"fixture")

            with (patch.multiple(install, GAME=game, MARKER=marker, WORK=root / "work", SECRETS=root / ".keys"),
                  patch.object(install, "drop_volume_root"),
                  patch.dict(os.environ, {"FS25_PRODUCT_KEY": KEY, "FS25_DOWNLOAD_URL": IMG}),
                  patch.object(install, "unpack", return_value=extracted) as unpack,
                  patch.object(install, "lookup") as lookup,
                  patch.object(install, "ensure_proton"),
                  patch.object(install, "run_setup", side_effect=setup),
                  contextlib.redirect_stdout(io.StringIO())):
                install.install(require_game=True)
                lookup.assert_not_called()
                unpack.assert_called_once_with(IMG, "FarmingSimulator25_1_25_1_0_ESD.img")
                self.assertEqual(install.installed()["source"], "FarmingSimulator25_1_25_1_0_ESD.img")


class DLCTests(unittest.TestCase):
    def test_amp_aliases_and_local_or_remote_sources(self):
        keys, sources = dlc.parse_entries("PUMPS=" + KEY + ";\nmercedes=" + KEY,
                                          "pumps=" + DLC + ";mercedes=extra/setup.img")
        self.assertEqual(list(keys), ["pumps", "mercedes"])
        self.assertEqual(sources, {"pumps": DLC, "mercedes": "extra/setup.img"})
        with self.assertRaisesRegex(common.Failure, "matching DLC key"):
            dlc.parse_entries("pumps=" + KEY, "other=" + DLC)
        with self.assertRaisesRegex(common.Failure, "Duplicate DLC key"):
            dlc.parse_entries(f"pumps={KEY};PUMPS={KEY}", "")

    def test_portal_discovery_excludes_the_base_and_other_hosts(self):
        parser = dlc.PortalLinks()
        parser.feed(f'<a href="{IMG}">base</a><a href="{DLC}?a=1&amp;b=2">dlc</a>'
                    '<a href="https://example.org/FarmingSimulator25_pumps_ESD.exe">external</a>')
        self.assertEqual(parser.links, {DLC + "?a=1&b=2"})

    def test_extract_img_with_real_7z_and_validate_pe(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / "dlc.img"
            image.write_bytes(iso_fixture(pe_fixture()))
            self.assertEqual(dlc.package_type(image), ".img")
            extracted = root / "extracted"
            extracted.mkdir()
            self.assertEqual(dlc.image_setup(image, extracted).read_bytes(), pe_fixture())

    def test_persistent_preparation_install_and_verified_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile = root / "profile"
            profile.mkdir()
            (profile / "AHC_63805.dat").write_text("fixture")
            (profile / "pdlc").mkdir()
            prefix = root / "compatdata" / "pfx"
            docs = prefix / "drive_c" / "users" / "steamuser" / "Documents" / "My Games"
            docs.mkdir(parents=True)
            (docs / "FarmingSimulator2025").symlink_to(profile, target_is_directory=True)
            (prefix / "system.reg").touch()
            inbox = root / "dlc-installers"
            (inbox / "extra").mkdir(parents=True)
            source = inbox / "extra" / "setup.exe"
            source.write_bytes(pe_fixture())
            outside = root / "outside.exe"
            outside.write_bytes(pe_fixture())
            (inbox / "outside.exe").symlink_to(outside)
            with self.assertRaisesRegex(common.Failure, "outside dlc-installers"):
                dlc.uploaded_file(inbox, "outside.exe")

            def fake_installer(exe, key, tag, env, timeout):
                self.assertEqual(exe.read_bytes(), pe_fixture())
                self.assertEqual(key, KEY)
                self.assertEqual(timeout, 1800)
                target = profile / "pdlc" / "pumps.dlc"
                target.write_bytes(b"installed content" * 6)
                return {"pumps.dlc": dlc.digest(target)}

            with (patch.multiple(dlc, ROOT=root, WORK=root / "work", PROFILE=profile),
                  patch.object(dlc, "compat", return_value=prefix.parent),
                  patch.dict(os.environ, {"FS25_DLC_PRODUCT_KEYS": "pumps=" + KEY,
                                          "FS25_DLC_INSTALL_SOURCES": "pumps=extra/setup.exe"}),
                  patch.object(dlc, "xvfb", side_effect=lambda *_: contextlib.nullcontext(":1")),
                  patch.object(dlc, "install_one", side_effect=fake_installer) as setup,
                  contextlib.redirect_stdout(io.StringIO()) as log):
                dlc.activate_configured(common.DEFAULT_PROTON, {})
                dlc.activate_configured(common.DEFAULT_PROTON, {})
                self.assertEqual(setup.call_count, 1)
                (profile / "pdlc" / "pumps.dlc").write_bytes(b"changed payload" * 6)
                dlc.activate_configured(common.DEFAULT_PROTON, {})
                self.assertEqual(setup.call_count, 2)
                self.assertIn("verified installed payload; skipping setup.", log.getvalue())
            for name in ("pending.json", "installed.json"):
                manifest = (root / "work" / "dlc" / name).read_text()
                self.assertNotIn(KEY, manifest)
                self.assertEqual(json.loads(manifest)["schema"], 1)

    def test_failure_does_not_write_completion_marker_and_stub_is_not_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile = root / "profile"
            (profile / "pdlc").mkdir(parents=True)
            (profile / "pdlc" / "stub.dlc").write_bytes(b"<dlcStub>" + b"x" * 100)
            (profile / "AHC_63805.dat").touch()
            prefix = root / "prefix" / "pfx"
            docs = prefix / "drive_c" / "users" / "steamuser" / "Documents" / "My Games"
            docs.mkdir(parents=True)
            (docs / "FarmingSimulator2025").symlink_to(profile)
            (prefix / "system.reg").touch()
            inbox = root / "dlc-installers"
            inbox.mkdir()
            (inbox / "setup.exe").write_bytes(pe_fixture())
            with (patch.multiple(dlc, ROOT=root, WORK=root / "work", PROFILE=profile),
                  patch.object(dlc, "compat", return_value=prefix.parent),
                  patch.object(dlc, "settings", return_value=({"test": KEY}, {"test": "setup.exe"}, 1800)),
                  patch.object(dlc, "xvfb", side_effect=lambda *_: contextlib.nullcontext(":1")),
                  patch.object(dlc, "install_one", side_effect=common.Failure("installer timeout")),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(dlc.payloads(), {})
                with self.assertRaisesRegex(common.Failure, "installer timeout"):
                    dlc.activate_configured(common.DEFAULT_PROTON, {})
            self.assertFalse((root / "work" / "dlc" / "installed.json").exists())

    def test_giants_success_requires_confirmed_dialog_title_and_text(self):
        listing = (
            "00100 #32770 10000000 0 0 Farming Simula\n"
            "  00102 Static 10000000 0 0 Installation s\n"
        )
        parent = "class='#32770' text='Farming Simulator 25 - Pumps'"
        child = "class='Static' text='Installation successful.'"
        def replies(details):
            return [Mock(returncode=0, stdout=value) for value in (listing, parent, details)]
        with patch.object(dlc.subprocess, "run", side_effect=replies(child)):
            self.assertTrue(dlc.success_dialog(common.DEFAULT_PROTON, {}))
        with patch.object(dlc.subprocess, "run", side_effect=replies("class='Static' text='Installation stopped.'")):
            self.assertFalse(dlc.success_dialog(common.DEFAULT_PROTON, {}))

    def test_dlc_dialog_takes_key_on_stdin_and_exit_one_requires_success(self):
        def run_tool(args, **kwargs):
            if args[1] == "search":
                return Mock(returncode=0, stdout=("100\n" if "FarmingSimulator2025" in args[-1] else "200\n"))
            return Mock(returncode=0)

        for success in (False, True):
            process = Mock(returncode=1)
            process.poll.side_effect = [None, 1]
            with (patch.object(dlc, "payloads", side_effect=[{}, {"pack.dlc": ("hash", 1)}]),
                  patch.object(dlc, "payload_stats", side_effect=[{}, {"pack.dlc": (100, 1)}]),
                  patch.object(dlc, "run_proton", return_value=process),
                  patch.object(dlc, "terminate"),
                  patch.object(dlc, "stop_wine"),
                  patch.object(dlc.time, "sleep"),
                  patch.object(dlc, "success_dialog", return_value=success),
                  patch.object(dlc.subprocess, "run", side_effect=run_tool) as tool,
                  contextlib.redirect_stdout(io.StringIO())):
                if success:
                    self.assertEqual(dlc.install_one(Path("test.exe"), KEY, common.DEFAULT_PROTON, {}, 1800),
                                     {"pack.dlc": "hash"})
                else:
                    with self.assertRaisesRegex(common.Failure, "exited with status 1"):
                        dlc.install_one(Path("test.exe"), KEY, common.DEFAULT_PROTON, {}, 1800)
                typed = next(call for call in tool.call_args_list if call.args[0][1] == "type")
                self.assertEqual(typed.args[0][-2:], ["--file", "-"])
                self.assertEqual(typed.kwargs["input"], KEY.replace("-", "").encode())
                self.assertNotIn(KEY.replace("-", ""), " ".join(typed.args[0]))
