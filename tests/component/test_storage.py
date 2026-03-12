"""Component tests for storage backends."""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from reagent.core.constants import Status
from reagent.core.exceptions import TraceNotFoundError
from reagent.schema.run import RunMetadata, CostSummary, TokenSummary, StepSummary
from reagent.schema.steps import LLMCallStep, ToolCallStep, ToolInput, TokenUsage
from reagent.storage.memory import MemoryStorage
from reagent.storage.jsonl import JSONLStorage
from reagent.storage.sqlite import SQLiteStorage
from reagent.storage.base import RunFilter, Pagination


class StorageTestBase:
    """Base class for storage backend tests."""

    storage_class = None

    def create_storage(self):
        """Override to create the specific storage backend."""
        raise NotImplementedError

    @pytest.fixture
    def storage(self):
        """Create storage instance for testing."""
        return self.create_storage()

    def create_sample_metadata(self, run_id=None, **kwargs):
        """Create sample run metadata."""
        run_id = run_id or uuid4()
        defaults = {
            "run_id": run_id,
            "name": "test-run",
            "project": "test-project",
            "start_time": datetime.utcnow(),
            "status": Status.RUNNING,
            "model": "gpt-4",
        }
        defaults.update(kwargs)
        return RunMetadata(**defaults)

    def create_sample_step(self, run_id, step_number=0):
        """Create a sample LLM step."""
        return LLMCallStep(
            run_id=run_id,
            step_number=step_number,
            timestamp_start=datetime.utcnow(),
            model="gpt-4",
            prompt="Hello",
            response="Hi there!",
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    # ===== Common Tests =====

    def test_save_and_load_run(self, storage):
        """Test saving and loading a run."""
        run_id = uuid4()
        metadata = self.create_sample_metadata(run_id)

        storage.save_run(run_id, metadata)
        loaded = storage.load_metadata(run_id)

        assert loaded.run_id == run_id
        assert loaded.name == "test-run"

    def test_save_and_load_steps(self, storage):
        """Test saving and loading steps."""
        run_id = uuid4()
        metadata = self.create_sample_metadata(run_id)
        storage.save_run(run_id, metadata)

        step1 = self.create_sample_step(run_id, 0)
        step2 = self.create_sample_step(run_id, 1)

        storage.save_step(run_id, step1)
        storage.save_step(run_id, step2)

        steps = list(storage.load_steps(run_id))
        assert len(steps) == 2

    def test_load_full_run(self, storage):
        """Test loading a complete run with steps."""
        run_id = uuid4()
        metadata = self.create_sample_metadata(run_id)
        storage.save_run(run_id, metadata)

        step = self.create_sample_step(run_id, 0)
        storage.save_step(run_id, step)

        run = storage.load_run(run_id)
        assert run.metadata.run_id == run_id
        assert len(run.steps) == 1

    def test_run_not_found(self, storage):
        """Test loading non-existent run."""
        with pytest.raises(TraceNotFoundError):
            storage.load_run(uuid4())

    def test_exists(self, storage):
        """Test exists check."""
        run_id = uuid4()
        assert storage.exists(run_id) is False

        metadata = self.create_sample_metadata(run_id)
        storage.save_run(run_id, metadata)

        assert storage.exists(run_id) is True

    def test_delete_run(self, storage):
        """Test deleting a run."""
        run_id = uuid4()
        metadata = self.create_sample_metadata(run_id)
        storage.save_run(run_id, metadata)

        assert storage.exists(run_id) is True
        result = storage.delete_run(run_id)
        assert result is True
        assert storage.exists(run_id) is False

    def test_delete_nonexistent_run(self, storage):
        """Test deleting non-existent run."""
        result = storage.delete_run(uuid4())
        assert result is False

    def test_list_runs(self, storage):
        """Test listing runs."""
        # Create multiple runs
        for i in range(3):
            run_id = uuid4()
            metadata = self.create_sample_metadata(run_id, name=f"run-{i}")
            storage.save_run(run_id, metadata)

        runs = storage.list_runs()
        assert len(runs) == 3

    def test_list_runs_with_filter(self, storage):
        """Test listing runs with filters."""
        # Create runs with different projects
        for project in ["proj-a", "proj-b", "proj-a"]:
            run_id = uuid4()
            metadata = self.create_sample_metadata(run_id, project=project)
            storage.save_run(run_id, metadata)

        # Filter by project
        filter = RunFilter(project="proj-a")
        runs = storage.list_runs(filters=filter)
        assert len(runs) == 2
        assert all(r.project == "proj-a" for r in runs)

    def test_list_runs_with_pagination(self, storage):
        """Test listing runs with pagination."""
        # Create 5 runs
        for i in range(5):
            run_id = uuid4()
            metadata = self.create_sample_metadata(run_id)
            storage.save_run(run_id, metadata)

        # Get first 2
        pagination = Pagination(limit=2, offset=0)
        runs = storage.list_runs(pagination=pagination)
        assert len(runs) == 2

        # Get next 2
        pagination = Pagination(limit=2, offset=2)
        runs = storage.list_runs(pagination=pagination)
        assert len(runs) == 2

    def test_count_runs(self, storage):
        """Test counting runs."""
        assert storage.count_runs() == 0

        for i in range(3):
            run_id = uuid4()
            metadata = self.create_sample_metadata(run_id)
            storage.save_run(run_id, metadata)

        assert storage.count_runs() == 3

    def test_load_steps_with_range(self, storage):
        """Test loading steps with range filter."""
        run_id = uuid4()
        metadata = self.create_sample_metadata(run_id)
        storage.save_run(run_id, metadata)

        for i in range(5):
            step = self.create_sample_step(run_id, i)
            storage.save_step(run_id, step)

        # Load steps 2-4
        steps = list(storage.load_steps(run_id, start=2, end=4))
        assert len(steps) == 2
        assert steps[0].step_number == 2
        assert steps[1].step_number == 3


class TestMemoryStorage(StorageTestBase):
    """Tests for MemoryStorage backend."""

    def create_storage(self):
        return MemoryStorage()

    def test_clear(self, storage):
        """Test clearing all data."""
        run_id = uuid4()
        metadata = self.create_sample_metadata(run_id)
        storage.save_run(run_id, metadata)

        storage.clear()
        assert storage.count_runs() == 0


class TestJSONLStorage(StorageTestBase):
    """Tests for JSONLStorage backend."""

    def create_storage(self):
        tmpdir = tempfile.mkdtemp()
        return JSONLStorage(base_path=tmpdir)

    def test_file_created(self, storage):
        """Test that JSONL file is created."""
        run_id = uuid4()
        metadata = self.create_sample_metadata(run_id)
        storage.save_run(run_id, metadata)

        file_path = storage._get_run_path(run_id)
        assert file_path.exists()

    def test_file_content(self, storage):
        """Test JSONL file content format."""
        run_id = uuid4()
        metadata = self.create_sample_metadata(run_id)
        storage.save_run(run_id, metadata)

        step = self.create_sample_step(run_id, 0)
        storage.save_step(run_id, step)

        file_path = storage._get_run_path(run_id)
        lines = file_path.read_text().strip().split("\n")

        assert len(lines) == 2  # metadata + step


class TestSQLiteStorage(StorageTestBase):
    """Tests for SQLiteStorage backend."""

    def create_storage(self):
        tmpdir = tempfile.mkdtemp()
        return SQLiteStorage(db_path=Path(tmpdir) / "test.db")

    def test_search(self, storage):
        """Test full-text search."""
        # Create runs with searchable content
        run_id1 = uuid4()
        metadata1 = self.create_sample_metadata(run_id1, name="test-search-alpha")
        storage.save_run(run_id1, metadata1)

        run_id2 = uuid4()
        metadata2 = self.create_sample_metadata(run_id2, name="test-search-beta")
        storage.save_run(run_id2, metadata2)

        run_id3 = uuid4()
        metadata3 = self.create_sample_metadata(run_id3, name="different-name")
        storage.save_run(run_id3, metadata3)

        # Search for "alpha"
        results = storage.search("alpha")
        assert len(results) == 1
        assert results[0].name == "test-search-alpha"
