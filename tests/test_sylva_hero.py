"""Tests for the ThreeUI SylvaHero (Living Green) integration at /ui/welcome.

The animation guarantee rests on two facts these tests pin: the packaged files are served
byte-exact at their registered SHA-256s, and the branded derivative differs from the
canonical page only in text - every <script> and <style> block is byte-identical.
"""
import hashlib
import re
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

STATIC = Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "landing-pages"

# Registered SHA-256s from the ThreeUI source bundle (revision 05f359ce157a).
REGISTERED = {
    "inner-green-3d.html": "69c3694bd63f44ef9f007ebe4dac57a83e4402e0cdf6b54dd10b96dd4f05e197",
    "inner-green-assets/three.min.js": "8a5f7249903b54d30f79f708699d2fed2d6a1d0741a4cd41377d1f01bb5a2271",
    "inner-green-assets/card-ecostove.jpg": "70ce084084902bc502f00c366405b661ecdff90dee95d363b36a6e146829e433",
    "inner-green-assets/card-ethos.jpg": "337627390f499b3ae272cec9e2f83c817694a82f42e1aa10a7b26a2c7d679dff",
    "inner-green-assets/lexend-latin.woff2": "1ec8f6ee2750554b4bc59ff0b507d316a82a7ba37e0e5bebc41d3bd9b9faad46",
}
REGISTERED_BYTES = {
    "inner-green-assets/card-ecostove.jpg": 290988,
    "inner-green-assets/card-ethos.jpg": 316720,
    "inner-green-assets/lexend-latin.woff2": 39692,
}
FRAME_SANDBOX = (
    "allow-downloads allow-forms allow-modals allow-popups allow-same-origin allow-scripts "
    "allow-top-navigation-by-user-activation"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_blocks(html: str):
    """Every <script> and <style> block, in order - the parts that carry the animation."""
    return re.findall(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>", html, re.S)


class TestPackagedFilesAreExact(unittest.TestCase):
    """The registered files must be present at their exact registered hashes."""

    def test_01_every_registered_file_matches_its_sha256(self):
        for rel, expected in REGISTERED.items():
            with self.subTest(file=rel):
                self.assertEqual(sha256((STATIC / rel).read_bytes()), expected)

    def test_02_binary_assets_match_registered_byte_counts(self):
        for rel, size in REGISTERED_BYTES.items():
            with self.subTest(file=rel):
                self.assertEqual((STATIC / rel).stat().st_size, size)

    def test_03_manifest_agrees_with_files_on_disk(self):
        manifest = (STATIC / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
        listed = dict(line.split("  ", 1)[::-1] for line in manifest if line.strip())
        self.assertEqual(listed, REGISTERED)


class TestBrandedDerivativePreservesAnimation(unittest.TestCase):
    """sentinel-hero.html may change copy and links, never a byte of script or style."""

    @classmethod
    def setUpClass(cls):
        cls.canon = (STATIC / "inner-green-3d.html").read_text(encoding="utf-8")
        cls.branded = (STATIC / "sentinel-hero.html").read_text(encoding="utf-8")

    def test_04_script_and_style_blocks_are_byte_identical(self):
        self.assertEqual(code_blocks(self.canon), code_blocks(self.branded))
        self.assertEqual(len(code_blocks(self.canon)), 5)

    def test_05_three_runtime_reference_is_unchanged(self):
        self.assertIn('src="inner-green-assets/three.min.js"', self.branded)

    def test_06_authored_asset_paths_are_unchanged(self):
        for asset in ("card-ethos.jpg", "card-ecostove.jpg", "lexend-latin.woff2"):
            with self.subTest(asset=asset):
                self.assertIn(f"inner-green-assets/{asset}", self.branded)

    def test_07_copy_is_rebranded_and_links_point_into_the_app(self):
        self.assertIn(">SENTINEL</div>", self.branded)
        self.assertIn("<span>Dashboard</span>", self.branded)
        self.assertIn('href="/ui"', self.branded)
        self.assertIn('href="/docs"', self.branded)
        self.assertIn('href="/api/v1/health"', self.branded)
        self.assertNotIn(">SYLVA</div>", self.branded)
        self.assertNotIn("<span>Grove</span>", self.branded)

    def test_07b_dock_anchors_navigate_despite_authored_preventdefault(self):
        # The authored dock handler calls preventDefault unconditionally, so the anchors carry
        # inline handlers that navigate the top document after the pollen burst plays.
        dock = re.findall(r"<a class=\"dock-item[^>]*>", self.branded)
        self.assertEqual(len(dock), 5)
        for anchor in dock:
            with self.subTest(anchor=anchor[:60]):
                self.assertIn("onclick=", anchor)
                self.assertIn("window.top.location", anchor)


class TestHeroIsServed(unittest.TestCase):
    """The frame route and the static mount reproduce the ThreeUI /landing-pages/ contract."""

    def setUp(self):
        self.client = TestClient(app)

    def test_08_canonical_page_is_served_byte_exact(self):
        resp = self.client.get("/landing-pages/inner-green-3d.html")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertEqual(sha256(resp.content), REGISTERED["inner-green-3d.html"])

    def test_09_three_runtime_is_served_byte_exact(self):
        resp = self.client.get("/landing-pages/inner-green-assets/three.min.js")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("javascript", resp.headers["content-type"])
        self.assertEqual(sha256(resp.content), REGISTERED["inner-green-assets/three.min.js"])

    def test_10_binary_assets_are_served(self):
        for rel in REGISTERED_BYTES:
            with self.subTest(asset=rel):
                resp = self.client.get(f"/landing-pages/{rel}")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(len(resp.content), REGISTERED_BYTES[rel])

    def test_11_welcome_route_hosts_branded_page_in_frame(self):
        resp = self.client.get("/ui/welcome")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('src="/landing-pages/sentinel-hero.html"', resp.text)
        self.assertIn(f'sandbox="{FRAME_SANDBOX}"', resp.text)
        self.assertIn('loading="eager"', resp.text)
        self.assertIn('class="threeui-background landing-page-frame"', resp.text)
        self.assertIn('class="shader-frame"', resp.text)

    def test_12_exact_flag_serves_the_canonical_page(self):
        resp = self.client.get("/ui/welcome?exact=true")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('src="/landing-pages/inner-green-3d.html"', resp.text)

    def test_13_welcome_route_stays_out_of_the_openapi_contract(self):
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertNotIn("/ui/welcome", paths)

    def test_14_dashboard_nav_links_to_welcome(self):
        resp = self.client.get("/ui")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('href="/ui/welcome"', resp.text)


if __name__ == "__main__":
    unittest.main()
