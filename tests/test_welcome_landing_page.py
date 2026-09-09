"""Unit and Integration tests for Welcome Landing Page (/welcome) and ThreeUI assets."""
import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestWelcomeLandingPage(unittest.TestCase):
    """Test suite for Welcome Landing Page (/welcome) and static assets."""

    def setUp(self):
        self.client = TestClient(app)

    def test_welcome_page_endpoint(self):
        """Test GET /welcome returns 200 OK with HTML content."""
        response = self.client.get("/welcome")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        
        # Verify brand identity and fine-tuned copy
        content = response.text
        self.assertIn("API Sentinel", content)
        self.assertIn("Autonomous Quality.", content)
        self.assertIn("Zero Guesswork.", content)
        self.assertIn("SENTINEL", content)
        self.assertIn("Launch Cockpit", content)
        self.assertIn("302 Passing", content)
        self.assertIn("6 Dimensions", content)
        self.assertIn("AI Diagnoses. Rules Verify.", content)

    def test_welcome_page_threejs_and_shader_elements(self):
        """Test that Three.js canvas and liquid metal shaders are properly embedded."""
        response = self.client.get("/welcome")
        self.assertEqual(response.status_code, 200)
        content = response.text
        self.assertIn('id="scene"', content)
        self.assertIn('class="liquid-fx"', content)
        self.assertIn('data-liquid-metal="explore"', content)
        self.assertIn('data-liquid-metal="play"', content)
        self.assertIn('inner-green-assets/three.min.js', content)

    def test_static_asset_delivery(self):
        """Test that all required ThreeUI binary assets are delivered with HTTP 200."""
        # 1. Three.js runtime
        res_three = self.client.get("/inner-green-assets/three.min.js")
        self.assertEqual(res_three.status_code, 200)
        self.assertGreater(len(res_three.content), 500000)

        # 2. Font woff2
        res_font = self.client.get("/inner-green-assets/lexend-latin.woff2")
        self.assertEqual(res_font.status_code, 200)
        self.assertEqual(len(res_font.content), 39692)

        # 3. Card images
        res_img1 = self.client.get("/inner-green-assets/card-ecostove.jpg")
        self.assertEqual(res_img1.status_code, 200)
        self.assertEqual(len(res_img1.content), 290988)

        res_img2 = self.client.get("/inner-green-assets/card-ethos.jpg")
        self.assertEqual(res_img2.status_code, 200)
        self.assertEqual(len(res_img2.content), 316720)

    def test_landing_pages_asset_alias(self):
        """Test that /landing-pages/inner-green-assets alias delivers assets properly."""
        res_alias = self.client.get("/landing-pages/inner-green-assets/three.min.js")
        self.assertEqual(res_alias.status_code, 200)
        self.assertGreater(len(res_alias.content), 500000)


if __name__ == "__main__":
    unittest.main()
