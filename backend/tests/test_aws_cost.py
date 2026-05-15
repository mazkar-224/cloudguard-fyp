"""
Tests for app/services/aws_cost.py

Strategy:
  - `@mock_aws` (from moto) intercepts all boto3 network calls so nothing
    ever reaches real AWS, even if something slips past our mocks.
  - `patch("app.services.aws_cost.boto3.client")` controls exactly what the
    mocked client returns, letting us simulate any AWS response we want.
  - The `fake_aws_settings` fixture in conftest.py handles credentials for
    every test automatically — no real .env needed.
"""

import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from moto import mock_aws

from app.services.aws_cost import get_daily_costs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client_error(code: str, message: str = "An error occurred") -> ClientError:
    """
    Build a boto3 ClientError with a specific AWS error code.

    boto3 raises ClientError for any HTTP 4xx/5xx response from AWS.
    The error code (e.g. "AccessDeniedException") is what our code inspects
    to decide which exception to re-raise.
    """
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "GetCostAndUsage",
    )


def make_mock_ce_client(response: dict) -> MagicMock:
    """
    Return a MagicMock that looks like a boto3 CE client.
    `get_cost_and_usage` will return `response` when called.
    """
    mock_ce = MagicMock()
    mock_ce.get_cost_and_usage.return_value = response
    return mock_ce


# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

# A realistic AWS response: two services with real costs, one with $0.
# Mirrors exactly what boto3 returns for a GroupBy=SERVICE daily query.
SAMPLE_RESPONSE = {
    "ResultsByTime": [
        {
            "TimePeriod": {"Start": "2026-05-08", "End": "2026-05-09"},
            "Groups": [
                {
                    "Keys": ["Amazon EC2"],
                    "Metrics": {"UnblendedCost": {"Amount": "18.50", "Unit": "USD"}},
                },
                {
                    "Keys": ["Amazon S3"],
                    "Metrics": {"UnblendedCost": {"Amount": "4.25", "Unit": "USD"}},
                },
                {
                    "Keys": ["AWS Lambda"],
                    # Amount "0" — should be filtered out by get_daily_costs()
                    "Metrics": {"UnblendedCost": {"Amount": "0", "Unit": "USD"}},
                },
            ],
        }
    ]
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@mock_aws
def test_happy_path_returns_correct_shape():
    """
    When AWS returns valid cost data, the result should be a list of dicts
    with exactly the keys: date, cost, service.
    """
    with patch("app.services.aws_cost.boto3.client") as mock_boto3:
        mock_boto3.return_value = make_mock_ce_client(SAMPLE_RESPONSE)

        results = get_daily_costs(days=1)

    assert isinstance(results, list)
    assert len(results) > 0

    for row in results:
        assert "date"    in row
        assert "cost"    in row
        assert "service" in row


@mock_aws
def test_happy_path_parses_values_correctly():
    """
    Dates, service names, and costs should be parsed and typed correctly.
    The raw AWS response has costs as strings — we convert them to floats.
    """
    with patch("app.services.aws_cost.boto3.client") as mock_boto3:
        mock_boto3.return_value = make_mock_ce_client(SAMPLE_RESPONSE)

        results = get_daily_costs(days=1)

    ec2 = next(r for r in results if r["service"] == "Amazon EC2")

    assert ec2["date"]    == "2026-05-08"  # string, not a datetime object
    assert ec2["cost"]    == 18.50         # float, not a string
    assert ec2["service"] == "Amazon EC2"  # service name passed through as-is


# ---------------------------------------------------------------------------
# Zero-cost filtering
# ---------------------------------------------------------------------------

@mock_aws
def test_zero_cost_entries_are_filtered_out():
    """
    Services with Amount "0" should not appear in the results.
    They add noise without adding information to the dashboard.
    """
    with patch("app.services.aws_cost.boto3.client") as mock_boto3:
        mock_boto3.return_value = make_mock_ce_client(SAMPLE_RESPONSE)

        results = get_daily_costs(days=1)

    service_names = [r["service"] for r in results]
    assert "AWS Lambda" not in service_names


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------

@mock_aws
def test_empty_results_returns_empty_list():
    """
    When AWS returns no days (e.g. Cost Explorer just enabled, no data yet),
    the function should return an empty list — not crash or raise.
    """
    empty_response = {"ResultsByTime": []}

    with patch("app.services.aws_cost.boto3.client") as mock_boto3:
        mock_boto3.return_value = make_mock_ce_client(empty_response)

        results = get_daily_costs(days=7)

    assert results == []


# ---------------------------------------------------------------------------
# Missing credentials
# ---------------------------------------------------------------------------

def test_empty_access_key_raises_value_error(fake_aws_settings):
    """
    If AWS_ACCESS_KEY_ID is an empty string in .env, we raise a ValueError
    before even calling boto3 — so the error message is clear and specific.

    `fake_aws_settings` is the mock from conftest.py. We modify it here to
    simulate a misconfigured .env.
    """
    fake_aws_settings.aws_access_key_id = ""

    with pytest.raises(ValueError, match="missing"):
        get_daily_costs()


def test_empty_secret_key_raises_value_error(fake_aws_settings):
    """
    Same as above but for AWS_SECRET_ACCESS_KEY being empty.
    """
    fake_aws_settings.aws_secret_access_key = ""

    with pytest.raises(ValueError, match="missing"):
        get_daily_costs()


# ---------------------------------------------------------------------------
# AWS API errors
# ---------------------------------------------------------------------------

@mock_aws
def test_access_denied_raises_permission_error():
    """
    If the IAM user lacks ce:GetCostAndUsage permission, AWS returns
    AccessDeniedException. We convert that to a Python PermissionError
    with a human-readable fix instruction.
    """
    with patch("app.services.aws_cost.boto3.client") as mock_boto3:
        mock_ce = MagicMock()
        mock_boto3.return_value = mock_ce
        mock_ce.get_cost_and_usage.side_effect = make_client_error(
            "AccessDeniedException",
            "User is not authorized to perform: ce:GetCostAndUsage",
        )

        with pytest.raises(PermissionError, match="permission"):
            get_daily_costs()


@mock_aws
def test_invalid_access_key_raises_value_error():
    """
    An invalid AWS_ACCESS_KEY_ID causes InvalidClientTokenId.
    We convert it to a ValueError pointing at the .env file.
    """
    with patch("app.services.aws_cost.boto3.client") as mock_boto3:
        mock_ce = MagicMock()
        mock_boto3.return_value = mock_ce
        mock_ce.get_cost_and_usage.side_effect = make_client_error(
            "InvalidClientTokenId",
            "The security token included in the request is invalid.",
        )

        with pytest.raises(ValueError, match="invalid"):
            get_daily_costs()


@mock_aws
def test_wrong_secret_key_raises_value_error():
    """
    A wrong AWS_SECRET_ACCESS_KEY causes SignatureDoesNotMatch.
    """
    with patch("app.services.aws_cost.boto3.client") as mock_boto3:
        mock_ce = MagicMock()
        mock_boto3.return_value = mock_ce
        mock_ce.get_cost_and_usage.side_effect = make_client_error(
            "SignatureDoesNotMatch",
            "The request signature we calculated does not match the signature you provided.",
        )

        with pytest.raises(ValueError, match="wrong"):
            get_daily_costs()


@mock_aws
def test_cost_explorer_not_enabled_raises_permission_error():
    """
    If Cost Explorer hasn't been enabled in the AWS Console, AWS returns
    OptInRequired. We convert it to a PermissionError with setup instructions.
    """
    with patch("app.services.aws_cost.boto3.client") as mock_boto3:
        mock_ce = MagicMock()
        mock_boto3.return_value = mock_ce
        mock_ce.get_cost_and_usage.side_effect = make_client_error(
            "OptInRequired",
            "Use of service 'ce' requires opting in.",
        )

        with pytest.raises(PermissionError, match="not enabled"):
            get_daily_costs()


@mock_aws
def test_unexpected_aws_error_raises_runtime_error():
    """
    Any error code we haven't explicitly handled should become a RuntimeError.
    This ensures we never silently swallow an unknown AWS error.
    """
    with patch("app.services.aws_cost.boto3.client") as mock_boto3:
        mock_ce = MagicMock()
        mock_boto3.return_value = mock_ce
        mock_ce.get_cost_and_usage.side_effect = make_client_error(
            "ServiceUnavailableException",
            "AWS is having a bad day.",
        )

        with pytest.raises(RuntimeError):
            get_daily_costs()
