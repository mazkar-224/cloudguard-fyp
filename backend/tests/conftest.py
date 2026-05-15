import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def fake_aws_settings():
    """
    Replace the real `settings` object with a fake one for every test.

    Why this is needed:
        aws_cost.py imports `settings` at the top of the file. Those settings
        are loaded from your real .env file. We don't want tests touching real
        credentials or failing when .env is missing (e.g. in CI).

    How it works:
        `patch("app.services.aws_cost.settings")` swaps out the settings object
        that aws_cost.py is already holding — without touching config.py itself.
        `autouse=True` means this fixture runs automatically for every test in
        this folder, so we never forget to apply it.

    The fixture yields the mock object so individual tests can modify it
    (e.g. set aws_access_key_id to "" to test the missing-credentials path).
    """
    with patch("app.services.aws_cost.settings") as mock_settings:
        mock_settings.aws_access_key_id     = "AKIAIOSFODNN7EXAMPLE"
        mock_settings.aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        mock_settings.aws_default_region    = "us-east-1"
        yield mock_settings  # tests that need to modify settings receive this object
