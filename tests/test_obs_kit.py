"""Checks for the streamer kit's OBS generator.

The generated files are only useful if OBS can actually load them, and a
malformed scene collection fails silently - OBS just shows an empty collection.
These tests assert the structural invariants OBS relies on: every scene item
points at a real source, every browser source points at an overlay file that
exists, and the profile carries the settings we claim to have chosen.
"""

import configparser
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "streaming" / "setup"))

import make_obs_kit as kit  # noqa: E402


class ChooseTierTests(unittest.TestCase):
    def test_a_fat_pipe_gets_the_top_tier(self):
        width, height, fps, kbps, label = kit.choose_tier(50, 60, "twitch")
        self.assertEqual((width, height, fps), (1920, 1080, 60))
        self.assertEqual(label, "1080p60")
        self.assertEqual(kbps, kit.SERVICE_MAX_KBPS["twitch"])

    def test_youtube_may_spend_more_than_twitch_on_the_same_line(self):
        twitch = kit.choose_tier(50, 60, "twitch")[3]
        youtube = kit.choose_tier(50, 60, "youtube")[3]
        self.assertGreater(youtube, twitch)

    def test_a_thin_pipe_steps_down_instead_of_dropping_frames(self):
        width, height, fps, kbps, _ = kit.choose_tier(3, 60, "twitch")
        self.assertLessEqual(width, 1280)
        # 65% of 3 Mbps, minus the audio track.
        self.assertLessEqual(kbps + 160, 3 * 1000 * 0.65)

    def test_max_fps_is_respected(self):
        for upload in (5, 12, 50):
            self.assertEqual(kit.choose_tier(upload, 30, "twitch")[2], 30)

    def test_a_hopeless_connection_still_returns_something_usable(self):
        width, height, fps, kbps, _ = kit.choose_tier(0.5, 60, "twitch")
        self.assertEqual((width, height), (854, 480))
        self.assertGreaterEqual(kbps, 800)

    def test_bitrate_never_exceeds_the_platform_ceiling(self):
        for service, ceiling in kit.SERVICE_MAX_KBPS.items():
            for upload in (2, 6, 15, 40, 200):
                kbps = kit.choose_tier(upload, 60, service)[3]
                self.assertLessEqual(kbps, ceiling, "%s at %s Mbps" % (service, upload))


class SceneCollectionTests(unittest.TestCase):
    def setUp(self):
        self.overlays = REPO_ROOT / "streaming" / "overlays"

    def build(self, target="windows", handle="tester"):
        return kit.build_scene_collection("Test Kit", target, self.overlays,
                                          1920, 1080, handle)

    def test_every_scene_item_points_at_a_real_source(self):
        for target in kit.SOURCE_IDS:
            collection = self.build(target)
            known = {s["uuid"] for s in collection["sources"]}
            for source in collection["sources"]:
                for item in source["settings"].get("items", []):
                    self.assertIn(item["source_uuid"], known,
                                  "%s: dangling item %r" % (target, item["name"]))

    def test_uuids_are_unique(self):
        collection = self.build()
        uuids = [s["uuid"] for s in collection["sources"]]
        for source in collection["sources"]:
            uuids.extend(f["uuid"] for f in source.get("filters", []))
        self.assertEqual(len(uuids), len(set(uuids)))

    def test_source_names_are_unique(self):
        # OBS keys sources by name in its UI; duplicates silently collide.
        collection = self.build()
        names = [s["name"] for s in collection["sources"]]
        self.assertEqual(len(names), len(set(names)))

    def test_scene_order_matches_the_scenes_that_exist(self):
        collection = self.build()
        scenes = {s["name"] for s in collection["sources"] if s["id"] == "scene"}
        ordered = {entry["name"] for entry in collection["scene_order"]}
        self.assertEqual(scenes, ordered)
        self.assertIn(collection["current_scene"], scenes)

    def test_every_browser_source_points_at_an_overlay_that_exists(self):
        collection = self.build()
        found = 0
        for source in collection["sources"]:
            if source["id"] != kit.BROWSER_ID:
                continue
            found += 1
            path = Path(source["settings"]["local_file"])
            self.assertTrue(path.is_file(), "missing overlay: %s" % path)
        self.assertEqual(found, 4)

    def test_the_handle_reaches_the_overlays(self):
        # The overlays read their branding from the query string, which OBS's
        # local-file mode cannot carry - so a handle has to flip the source
        # into URL mode or it silently never shows up on screen.
        collection = self.build(handle="tester")
        for source in collection["sources"]:
            if source["id"] != kit.BROWSER_ID:
                continue
            self.assertFalse(source["settings"]["is_local_file"])
            self.assertIn("handle=tester", source["settings"]["url"])
            self.assertTrue(source["settings"]["url"].startswith("file://"))

    def test_no_handle_leaves_the_sources_in_plain_local_file_mode(self):
        collection = self.build(handle="")
        for source in collection["sources"]:
            if source["id"] != kit.BROWSER_ID:
                continue
            self.assertTrue(source["settings"]["is_local_file"])
            self.assertNotIn("url", source["settings"])

    def test_the_mic_ships_with_cleanup_filters(self):
        collection = self.build()
        mic = next(s for s in collection["sources"] if s["name"] == "Mic")
        ids = {f["id"] for f in mic["filters"]}
        self.assertIn("noise_suppress_filter_v2", ids)
        self.assertIn("compressor_filter", ids)

    def test_audio_sources_are_on_the_mix_and_video_sources_are_not(self):
        collection = self.build()
        by_name = {s["name"]: s for s in collection["sources"]}
        self.assertEqual(by_name["Mic"]["mixers"], 255)
        self.assertEqual(by_name["Game Audio"]["mixers"], 255)
        self.assertEqual(by_name["Game Capture"]["mixers"], 0)
        self.assertEqual(by_name["Webcam"]["mixers"], 0)

    def test_macos_omits_the_desktop_audio_source_it_cannot_provide(self):
        collection = self.build("macos")
        names = {s["name"] for s in collection["sources"]}
        self.assertNotIn("Game Audio", names)

    def test_the_collection_serialises_to_json(self):
        json.dumps(self.build())


class ProfileTests(unittest.TestCase):
    def test_basic_ini_carries_the_chosen_settings(self):
        text = kit.build_basic_ini("Test Kit", 2560, 1440, 1920, 1080, 60,
                                   6000, "nvenc", Path("/tmp/recordings"))
        parser = configparser.ConfigParser()
        parser.read_string(text)
        self.assertEqual(parser["Output"]["Mode"], "Simple")
        self.assertEqual(parser["Video"]["BaseCX"], "2560")
        self.assertEqual(parser["Video"]["OutputCX"], "1920")
        self.assertEqual(parser["Video"]["FPSCommon"], "60")
        self.assertEqual(parser["SimpleOutput"]["VBitrate"], "6000")
        self.assertEqual(parser["SimpleOutput"]["StreamEncoder"], "nvenc")

    def test_the_service_file_never_contains_a_stream_key(self):
        # A key committed to disk by a setup script is a key that ends up in a
        # screenshot. OBS asks for it interactively instead.
        for service in kit.SERVICE_NAMES:
            blob = json.dumps(kit.build_service_json(service)).lower()
            self.assertNotIn("key", blob)


class EndToEndTests(unittest.TestCase):
    def test_generating_a_kit_writes_the_three_files_obs_needs(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = kit.parse_args([
                "--upload-mbps", "20",
                "--target-platform", "linux",
                "--service", "twitch",
                "--name", "My Kit",
                "--out", tmp,
            ])
            summary = kit.build_kit(args)

            self.assertTrue((summary["profile_dir"] / "basic.ini").is_file())
            self.assertTrue((summary["profile_dir"] / "service.json").is_file())
            self.assertTrue(summary["scene_file"].is_file())

            collection = json.loads(summary["scene_file"].read_text())
            self.assertEqual(collection["name"], "My Kit")
            self.assertEqual(summary["profile_dir"].name, "My_Kit")

    def test_install_copies_into_an_obs_config_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "generated"
            fake_obs = Path(tmp) / "obs-studio"
            (fake_obs / "basic" / "profiles").mkdir(parents=True)
            (fake_obs / "basic" / "scenes").mkdir(parents=True)

            args = kit.parse_args(["--upload-mbps", "20", "--target-platform", "linux",
                                   "--out", str(root)])
            kit.build_kit(args)

            original = kit.obs_config_dir
            kit.obs_config_dir = lambda target: fake_obs
            try:
                kit.install(root, "linux", "Starter_Kit")
            finally:
                kit.obs_config_dir = original

            self.assertTrue((fake_obs / "basic" / "profiles" / "Starter_Kit" / "basic.ini").is_file())
            self.assertTrue((fake_obs / "basic" / "scenes" / "Starter_Kit.json").is_file())

    def test_a_bad_canvas_is_rejected_rather_than_guessed_at(self):
        with self.assertRaises(SystemExit):
            kit.resolve_canvas("huge")


if __name__ == "__main__":
    unittest.main()
