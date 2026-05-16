"""
Tests for app/services/aws_cost_service.py

Strategy:
  - The `aws_service` fixture (conftest.py) builds an AwsCostService with a
    fake boto3 client — no real AWS calls ever happen.
  - Async methods are tested with @pytest.mark.anyio (anyio is already installed).
  - Sync paths (credential validation, error mapping) are tested as plain functions.
"""

import pytest
from datetime import date
from unittest.mock import MagicMock
from botocore.exceptions import ClientError

from app.services.aws_cost_service import AwsCostService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client_error(code: str, message: str = "An error occurred") -> ClientError:
    """Build a boto3 ClientError with a specific AWS error code."""
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "GetCostAndUsage",
    )


# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

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
                    # Amount "0" — should be filtered out
                    "Metrics": {"UnblendedCost": {"Amount": "0", "Unit": "USD"}},
                },
            ],
        }
    ]
}


# ---------------------------------------------------------------------------
# Credential validation (sync — tested on __init__)
# ---------------------------------------------------------------------------

def test_empty_access_key_raises_value_error():
    """
    Passing an empty access key to __init__ should raise ValueError immediately.
    We catch bad credentials at construction time, not at the first API call.
    """
    with pytest.raises(ValueError, match="missing"):
        AwsCostService(aws_access_key_id="", aws_secret_access_key="secret")


def test_empty_secret_key_raises_value_error():
    """Same check for an empty secret key."""
    with pytest.raises(ValueError, match="missing"):
        AwsCostService(aws_access_key_id="AKIAIOSFODNN7EXAMPLE", aws_secret_access_key="")


# ---------------------------------------------------------------------------
# get_daily_costs — happy path
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_daily_costs_returns_correct_shape(aws_service):
    """
    get_daily_costs should return a list of dicts, each with date/cost/service.
    """
    aws_service._client.get_cost_and_usage.return_value = SAMPLE_RESPONSE

    results = await aws_service.get_daily_costs(days=1)

    assert isinstance(results, list)
    assert len(results) > 0
    for row in results:
        assert "date"    in row
        assert "cost"    in row
        assert "service" in row


@pytest.mark.anyio
async def test_get_daily_costs_parses_values_correctly(aws_service):
    """
    Dates should be strings, costs should be floats (not strings),
    and service names should pass through unchanged.
    """
    aws_service._client.get_cost_and_usage.return_value = SAMPLE_RESPONSE

    results = await aws_service.get_daily_costs(days=1)
    ec2 = next(r for r in results if r["service"] == "Amazon EC2")

    assert ec2["date"]    == "2026-05-08"
    assert ec2["cost"]    == 18.50
    assert ec2["service"] == "Amazon EC2"


@pytest.mark.anyio
async def test_get_daily_costs_filters_zero_cost_entries(aws_service):
    """
    Services with Amount "0" should not appear in the results.
    They add noise without adding information to the dashboard.
    """
    aws_service._client.get_cost_and_usage.return_value = SAMPLE_RESPONSE

    results = await aws_service.get_daily_costs(days=1)
    service_names = [r["service"] for r in results]

    assert "AWS Lambda" not in service_names


@pytest.mark.anyio
async def test_get_daily_costs_empty_response_returns_empty_list(aws_service):
    """
    When AWS returns no data (Cost Explorer just enabled), return [] not crash.
    """
    aws_service._client.get_cost_and_usage.return_value = {"ResultsByTime": []}

    results = await aws_service.get_daily_costs(days=7)

    assert results == []


# ---------------------------------------------------------------------------
# get_cost_by_service — happy path
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_cost_by_service_aggregates_by_service(aws_service):
    """
    get_cost_by_service should return one entry per service (not per day),
    with costs summed across the date range.
    """
    aws_service._client.get_cost_and_usage.return_value = SAMPLE_RESPONSE

    results = await aws_service.get_cost_by_service(
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 8),
    )

    assert isinstance(results, list)
    for row in results:
        assert "service" in row
        assert "cost"    in row
        # Each row covers a service, not a day — no "date" key
        assert "date" not in row


@pytest.mark.anyio
async def test_get_cost_by_service_sorted_by_cost_descending(aws_service):
    """
    Results should be sorted most expensive first — matches dashboard pie chart order.
    """
    aws_service._client.get_cost_and_usage.return_value = SAMPLE_RESPONSE

    results = await aws_service.get_cost_by_service(
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 8),
    )

    costs = [r["cost"] for r in results]
    assert costs == sorted(costs, reverse=True)


# ---------------------------------------------------------------------------
# AWS API error handling
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_access_denied_raises_permission_error(aws_service):
    """AccessDeniedException → PermissionError with a fix instruction."""
    aws_service._client.get_cost_and_usage.side_effect = make_client_error(
        "AccessDeniedException",
        "User is not authorized to perform: ce:GetCostAndUsage",
    )

    with pytest.raises(PermissionError, match="permission"):
        await aws_service.get_daily_costs()


@pytest.mark.anyio
async def test_invalid_access_key_raises_value_error(aws_service):
    """InvalidClientTokenId → ValueError pointing at the .env file."""
    aws_service._client.get_cost_and_usage.side_effect = make_client_error(
        "InvalidClientTokenId",
        "The security token included in the request is invalid.",
    )

    with pytest.raises(ValueError, match="invalid"):
        await aws_service.get_daily_costs()


@pytest.mark.anyio
async def test_wrong_secret_key_raises_value_error(aws_service):
    """SignatureDoesNotMatch → ValueError about the secret key."""
    aws_service._client.get_cost_and_usage.side_effect = make_client_error(
        "SignatureDoesNotMatch",
        "The request signature we calculated does not match.",
    )

    with pytest.raises(ValueError, match="wrong"):
        await aws_service.get_daily_costs()


@pytest.mark.anyio
async def test_cost_explorer_not_enabled_raises_permission_error(aws_service):
    """OptInRequired → PermissionError with enable instructions."""
    aws_service._client.get_cost_and_usage.side_effect = make_client_error(
        "OptInRequired",
        "Use of service 'ce' requires opting in.",
    )

    with pytest.raises(PermissionError, match="not enabled"):
        await aws_service.get_daily_costs()


@pytest.mark.anyio
async def test_unexpected_aws_error_raises_runtime_error(aws_service):
    """Any unrecognised error code should become a RuntimeError — never swallowed."""
    aws_service._client.get_cost_and_usage.side_effect = make_client_error(
        "ServiceUnavailableException",
        "AWS is having a bad day.",
    )

    with pytest.raises(RuntimeError):
        await aws_service.get_daily_costs()
