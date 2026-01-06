from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.core.exceptions import TimeSeriesException
from app.services.time_series_service import TimeSeriesService


class TestTimeSeriesServiceCoverage:
    @pytest.fixture
    def service(self, mock_db_session):
        return TimeSeriesService(mock_db_session)

    def test_get_int_id_hash_fallback(self, service):
        """Test _get_int_id hashing behavior for non-integer IDs (Lines 63-70)."""
        # "test" hash -> determinstic check
        # blake2b("test") -> int
        import hashlib

        expected_hash_bytes = hashlib.blake2b(b"test", digest_size=8).digest()
        expected_int = int.from_bytes(
            expected_hash_bytes, byteorder="big", signed=False
        )

        result = service._get_int_id("test")
        assert result == expected_int
        assert service._get_int_id("123") == 123

    def test_get_stations_json_error(self, service):
        """Test get_stations handling invalid JSON (Lines 186-188)."""
        with patch("app.services.time_series_service.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.side_effect = (
                requests.exceptions.JSONDecodeError("Fail", "doc", 0)
            )

            with pytest.raises(TimeSeriesException) as exc:
                service.get_stations()
            assert "invalid JSON" in str(exc.value)

    def test_get_station_json_error(self, service):
        """Test get_station handling invalid JSON (Lines 207-209)."""
        with patch("app.services.time_series_service.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.side_effect = ValueError("Fail")

            with pytest.raises(TimeSeriesException) as exc:
                service.get_station("ST_1")
            assert "invalid JSON" in str(exc.value)

    def test_delete_station_json_error(self, service):
        """Warning: This might just raise the error, checking implementation (Lines 258-262)."""
        with patch("app.services.time_series_service.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.side_effect = ValueError("Fail")

            # The code re-raises validation/value errors after logging
            with pytest.raises(ValueError):
                service.delete_station("ST_1")

    def test_get_metadata_json_error(self, service):
        """Test get_time_series_metadata invalid JSON (Lines 323-327)."""
        with patch("app.services.time_series_service.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.side_effect = ValueError("Fail")

            # Should return empty list based on implementation
            res = service.get_time_series_metadata()
            assert res == []

    def test_get_metadata_request_exception(self, service):
        """Test get_time_series_metadata request failure (Lines 375-377)."""
        with patch("app.services.time_series_service.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("Net Fail")

            with pytest.raises(TimeSeriesException) as exc:
                service.get_time_series_metadata()
            assert "Failed to fetch metadata" in str(exc.value)

    def test_get_metadata_general_exception(self, service):
        """Test get_time_series_metadata unexpected error (Lines 378-380)."""
        with patch("app.services.time_series_service.requests.get") as mock_get:
            mock_get.side_effect = RuntimeError("Boom")

            with pytest.raises(TimeSeriesException) as exc:
                service.get_time_series_metadata()
            assert "Unexpected error" in str(exc.value)

    def test_create_data_point_json_error(self, service):
        """Test create_data_point datastream lookup JSON error (Lines 475-479)."""
        mock_pt = MagicMock(
            station_id="ST1", parameter="WL", value=10.0, timestamp=datetime.now()
        )
        # Mock parameter to be string or enum
        mock_pt.parameter = "WL"

        with patch("app.services.time_series_service.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.side_effect = ValueError("Fail")

            with pytest.raises(TimeSeriesException):  # Wrapped in generic catcher?
                # No, checking line 479 `raise` -> re-raises ValueError
                # And line 533 catches Exception -> raises TimeSeriesException
                service.create_data_point(mock_pt)

    def test_create_data_point_not_found(self, service):
        """Test create_data_point datastream not found (Lines 483-487)."""
        mock_pt = MagicMock(
            station_id="ST1", parameter="WL", value=10, timestamp=datetime.now()
        )
        mock_pt.parameter = "WL"

        with patch("app.services.time_series_service.requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            # Returns empty value list
            mock_get.return_value.json.return_value = {"value": []}

            with pytest.raises(TimeSeriesException) as exc:
                service.create_data_point(mock_pt)
            assert "found" in str(exc.value)  # "Datastream ... not found"

    def test_aggregate_time_series_validation(self, service):
        """Test aggregation validation error (Lines 790-794)."""
        # Mock get_time_series_data to raise ValueError
        with patch.object(
            service, "get_time_series_data", side_effect=ValueError("Bad params")
        ):
            from app.schemas.time_series import TimeSeriesAggregation

            req = TimeSeriesAggregation(
                series_id="S1",
                start_time=datetime.now(),
                end_time=datetime.now(),
                aggregation_interval="1h",
                aggregation_method="mean",
            )
            with pytest.raises(ValueError):
                service.aggregate_time_series(req)

    def test_aggregate_time_series_general_error(self, service):
        """Test aggregation general error (Lines 795-797)."""
        with patch.object(
            service, "get_time_series_data", side_effect=RuntimeError("Boom")
        ):
            from app.schemas.time_series import TimeSeriesAggregation

            req = TimeSeriesAggregation(
                series_id="S1",
                start_time=datetime.now(),
                end_time=datetime.now(),
                aggregation_interval="1h",
                aggregation_method="mean",
            )
            with pytest.raises(TimeSeriesException):
                service.aggregate_time_series(req)
