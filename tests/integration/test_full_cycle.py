"""Integration tests for full recording/replay cycle."""

import pytest
import tempfile
from pathlib import Path
from uuid import uuid4

from reagent.client.reagent import ReAgent
from reagent.core.config import Config
from reagent.core.constants import Status, ReplayMode
from reagent.schema.run import RunConfig
from reagent.replay.engine import ReplayEngine
from reagent.storage.jsonl import JSONLStorage


class TestFullCycle:
    """Integration tests for complete recording/replay workflow."""

    @pytest.fixture
    def temp_storage_path(self):
        """Create a temporary storage directory."""
        return tempfile.mkdtemp()

    @pytest.fixture
    def client(self, temp_storage_path):
        """Create a ReAgent client with JSONL storage."""
        config = Config(
            storage={"type": "jsonl", "path": temp_storage_path},
            redaction={"enabled": False},
        )
        return ReAgent(config=config)

    def test_record_and_list(self, client):
        """Test recording a run and listing it."""
        # Record a run
        with client.trace(RunConfig(name="integration-test")) as ctx:
            ctx.record_llm_call(
                model="gpt-4",
                prompt="What is 2+2?",
                response="4",
                prompt_tokens=10,
                completion_tokens=1,
            )
            ctx.record_tool_call(
                tool_name="calculator",
                kwargs={"expression": "2+2"},
                result=4,
            )
            ctx.set_output({"answer": 4})

        # Flush and verify
        client.flush()

        # List and verify
        runs = client.list_runs()
        assert len(runs) == 1
        assert runs[0].name == "integration-test"
        assert runs[0].status == Status.COMPLETED
        assert runs[0].step_count == 2

    def test_record_and_load(self, client):
        """Test recording a run and loading full details."""
        # Record
        with client.trace(RunConfig(name="load-test", project="test")) as ctx:
            run_id = ctx.run_id
            ctx.record_llm_call(
                model="gpt-4",
                prompt="Hello",
                response="Hi!",
            )

        client.flush()

        # Load
        run = client.load_run(run_id)

        assert run.metadata.name == "load-test"
        assert run.metadata.project == "test"
        assert len(run.steps) == 1
        assert run.steps[0].step_type == "llm_call"

    def test_record_and_replay(self, client):
        """Test recording a run and replaying it."""
        # Record
        with client.trace(RunConfig(name="replay-test")) as ctx:
            run_id = ctx.run_id
            ctx.record_llm_call(
                model="gpt-4",
                prompt="What is the capital of France?",
                response="Paris",
                prompt_tokens=15,
                completion_tokens=1,
            )
            ctx.record_tool_call(
                tool_name="web_search",
                kwargs={"query": "Paris facts"},
                result=["Paris is beautiful"],
            )
            ctx.record_llm_call(
                model="gpt-4",
                prompt="Summarize",
                response="Paris is the capital of France and is beautiful.",
                prompt_tokens=20,
                completion_tokens=10,
            )

        client.flush()

        # Replay
        engine = ReplayEngine(
            storage=client.storage,
            mode=ReplayMode.STRICT,
        )

        session = engine.replay(run_id)

        assert session.status == Status.COMPLETED
        assert session.current_step == 3
        assert len(session.results) == 3
        assert all(not r.diverged for r in session.results)

    def test_multiple_runs_and_filter(self, client):
        """Test recording multiple runs and filtering."""
        # Record runs with different projects
        for project in ["project-a", "project-a", "project-b"]:
            with client.trace(RunConfig(project=project)):
                pass

        client.flush()

        # Filter by project
        runs_a = client.list_runs(project="project-a")
        assert len(runs_a) == 2

        runs_b = client.list_runs(project="project-b")
        assert len(runs_b) == 1

    def test_error_handling(self, client):
        """Test error handling during recording."""
        with pytest.raises(ValueError):
            with client.trace(RunConfig(name="error-test")) as ctx:
                ctx.record_llm_call(model="gpt-4", prompt="Before error")
                raise ValueError("Test error")

        client.flush()

        # Verify run was saved as failed
        runs = client.list_runs()
        assert len(runs) == 1
        assert runs[0].status == Status.FAILED
        assert "Test error" in runs[0].error


class TestFileBasedWorkflow:
    """Integration tests for file-based workflow."""

    def test_jsonl_persistence(self):
        """Test that JSONL files persist correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = Path(tmpdir) / "traces"

            # Create and record
            config = Config(
                storage={"type": "jsonl", "path": str(storage_path)},
                redaction={"enabled": False},
            )
            client = ReAgent(config=config)

            with client.trace(RunConfig(name="persistence-test")) as ctx:
                run_id = ctx.run_id
                ctx.record_llm_call(model="gpt-4", prompt="test")

            client.flush()
            client.close()

            # Verify file exists
            trace_file = storage_path / f"{run_id}.jsonl"
            assert trace_file.exists()

            # Load with new client
            new_client = ReAgent(config=config)
            run = new_client.load_run(run_id)

            assert run.metadata.name == "persistence-test"
            assert len(run.steps) == 1
            new_client.close()
