"""Tests for the salience decay background job."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSalienceDecayJob:
    """Tests for the daily salience decay job."""

    @pytest.mark.asyncio
    async def test_job_processes_all_users(self) -> None:
        """The job should update salience for all users."""
        from src.jobs.salience_decay import run_salience_decay_job

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=[
                {"id": "user-1"},
                {"id": "user-2"},
                {"id": "user-3"},
            ]
        )

        mock_salience_service = MagicMock()
        mock_salience_service.update_all_salience = AsyncMock(return_value=5)

        with patch("src.jobs.salience_decay.SupabaseClient") as mock_client:
            mock_client.get_client.return_value = mock_db
            with patch("src.jobs.salience_decay.SalienceService", return_value=mock_salience_service):
                result = await run_salience_decay_job()

        # Should have called update for each user
        assert mock_salience_service.update_all_salience.call_count == 3
        assert result["users_processed"] == 3

    @pytest.mark.asyncio
    async def test_job_returns_total_updates(self) -> None:
        """The job should return total number of updated records."""
        from src.jobs.salience_decay import run_salience_decay_job

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=[{"id": "user-1"}, {"id": "user-2"}]
        )

        mock_salience_service = MagicMock()
        mock_salience_service.update_all_salience = AsyncMock(side_effect=[10, 5])

        with patch("src.jobs.salience_decay.SupabaseClient") as mock_client:
            mock_client.get_client.return_value = mock_db
            with patch("src.jobs.salience_decay.SalienceService", return_value=mock_salience_service):
                result = await run_salience_decay_job()

        assert result["records_updated"] == 15

    @pytest.mark.asyncio
    async def test_job_continues_on_user_error(self) -> None:
        """If one user fails, job should continue with others."""
        from src.jobs.salience_decay import run_salience_decay_job

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(
            data=[{"id": "user-1"}, {"id": "user-2"}]
        )

        mock_salience_service = MagicMock()
        mock_salience_service.update_all_salience = AsyncMock(
            side_effect=[Exception("DB error"), 5]
        )

        with patch("src.jobs.salience_decay.SupabaseClient") as mock_client:
            mock_client.get_client.return_value = mock_db
            with patch("src.jobs.salience_decay.SalienceService", return_value=mock_salience_service):
                result = await run_salience_decay_job()

        # Should still process second user
        assert result["users_processed"] == 2
        assert result["errors"] == 1
