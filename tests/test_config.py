"""Unit tests for Settings and environment variable management."""
import os
import unittest
from pydantic import ValidationError
from app.core.config import Settings, get_settings, clear_settings_cache


class TestConfig(unittest.TestCase):
    """Test suite verifying configuration validation and behavior."""

    def setUp(self):
        clear_settings_cache()

    def tearDown(self):
        clear_settings_cache()

    def test_default_settings(self):
        """Verify default configuration values."""
        settings = Settings()
        self.assertEqual(settings.PROJECT_NAME, "API Sentinel")
        self.assertEqual(settings.VERSION, "0.1.0")
        self.assertEqual(settings.ENVIRONMENT, "development")
        self.assertEqual(settings.PORT, 8000)
        self.assertEqual(settings.DEFAULT_TIMEOUT_SECONDS, 10.0)
        self.assertFalse(settings.is_production)
        self.assertFalse(settings.is_ai_enabled)

    def test_database_url_validation_success(self):
        """Verify supported database URLs pass validation."""
        s1 = Settings(DATABASE_URL="sqlite:///./test.db")
        self.assertTrue(s1.DATABASE_URL.startswith("sqlite://"))

        s2 = Settings(DATABASE_URL="postgresql://user:pass@localhost:5432/db")
        self.assertTrue(s2.DATABASE_URL.startswith("postgresql://"))

    def test_database_url_validation_failure(self):
        """Verify unsupported database URLs raise ValidationError."""
        with self.assertRaises(ValidationError):
            Settings(DATABASE_URL="mysql://user:pass@localhost/db")

    def test_timeout_validation_failure(self):
        """Verify non-positive timeout values raise ValidationError."""
        with self.assertRaises(ValidationError):
            Settings(DEFAULT_TIMEOUT_SECONDS=0)

        with self.assertRaises(ValidationError):
            Settings(DEFAULT_TIMEOUT_SECONDS=-5.0)

    def test_environment_override(self):
        """Verify environment variables override defaults."""
        os.environ["PROJECT_NAME"] = "Custom Sentinel"
        os.environ["PORT"] = "9000"
        os.environ["ENVIRONMENT"] = "production"
        os.environ["GEMINI_API_KEY"] = "mock_api_key_123"

        try:
            settings = Settings()
            self.assertEqual(settings.PROJECT_NAME, "Custom Sentinel")
            self.assertEqual(settings.PORT, 9000)
            self.assertTrue(settings.is_production)
            self.assertTrue(settings.is_ai_enabled)
        finally:
            os.environ.pop("PROJECT_NAME", None)
            os.environ.pop("PORT", None)
            os.environ.pop("ENVIRONMENT", None)
            os.environ.pop("GEMINI_API_KEY", None)

    def test_cached_settings_identity(self):
        """Verify get_settings returns cached singleton instance."""
        s1 = get_settings()
        s2 = get_settings()
        self.assertIs(s1, s2)


if __name__ == "__main__":
    unittest.main()
