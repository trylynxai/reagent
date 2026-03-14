"""Remote storage backend — read-only HTTP client for CLI in remote mode."""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Iterator
from uuid import UUID

from reagent.core.exceptions import TraceNotFoundError, StorageError
from reagent.schema.run import Run, RunMetadata, RunSummary
from reagent.schema.steps import AnyStep
from reagent.storage.base import StorageBackend, RunFilter, Pagination


class RemoteStorage(StorageBackend):
    """Read-only storage backend that fetches data from a remote ReAgent server.

    Used by the CLI when mode=remote. All write methods raise NotImplementedError.
    """

    def __init__(
        self,
        server_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make an HTTP request to the server and return parsed JSON."""
        url = f"{self._server_url}{path}"

        if params:
            query_parts = []
            for k, v in params.items():
                if v is not None:
                    query_parts.append(f"{urllib.request.quote(str(k))}={urllib.request.quote(str(v))}")
            if query_parts:
                url += "?" + "&".join(query_parts)

        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = urllib.request.Request(url, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise TraceNotFoundError(path) from e
            raise StorageError(f"Server returned {e.code}: {e.reason}") from e
        except Exception as e:
            raise StorageError(f"Failed to connect to server: {e}") from e

    def save_run(self, run_id: UUID, metadata: RunMetadata) -> None:
        raise NotImplementedError("RemoteStorage is read-only. Writes go through RemoteTransport.")

    def save_step(self, run_id: UUID, step: AnyStep) -> None:
        raise NotImplementedError("RemoteStorage is read-only. Writes go through RemoteTransport.")

    def load_run(self, run_id: UUID) -> Run:
        data = self._request("GET", f"/api/v1/runs/{run_id}")
        return Run.model_validate(data)

    def load_metadata(self, run_id: UUID) -> RunMetadata:
        data = self._request("GET", f"/api/v1/runs/{run_id}/metadata")
        return RunMetadata.model_validate(data)

    def load_steps(
        self,
        run_id: UUID,
        start: int | None = None,
        end: int | None = None,
        step_type: str | None = None,
    ) -> Iterator[AnyStep]:
        from reagent.storage.sqlite import STEP_TYPE_MAP, CustomStep

        params: dict[str, Any] = {}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        if step_type is not None:
            params["step_type"] = step_type

        data = self._request("GET", f"/api/v1/runs/{run_id}/steps", params=params)
        for step_data in data:
            step_cls = STEP_TYPE_MAP.get(step_data.get("step_type", "custom"), CustomStep)
            yield step_cls.model_validate(step_data)

    def list_runs(
        self,
        filters: RunFilter | None = None,
        pagination: Pagination | None = None,
    ) -> list[RunSummary]:
        filters = filters or RunFilter()
        pagination = pagination or Pagination()

        params: dict[str, Any] = {
            "limit": pagination.limit,
            "offset": pagination.offset,
            "sort_by": pagination.sort_by,
            "sort_order": pagination.sort_order,
        }

        if filters.project:
            params["project"] = filters.project
        if filters.status:
            if isinstance(filters.status, list):
                params["status"] = ",".join(s.value for s in filters.status)
            else:
                params["status"] = filters.status.value
        if filters.model:
            params["model"] = filters.model
        if filters.has_error is not None:
            params["has_error"] = str(filters.has_error).lower()
        if filters.failure_category:
            params["failure_category"] = filters.failure_category
        if filters.name:
            params["name"] = filters.name

        data = self._request("GET", "/api/v1/runs", params=params)
        return [RunSummary.model_validate(r) for r in data]

    def search(
        self,
        query: str,
        filters: RunFilter | None = None,
        pagination: Pagination | None = None,
    ) -> list[RunSummary]:
        filters = filters or RunFilter()
        pagination = pagination or Pagination()

        params: dict[str, Any] = {
            "q": query,
            "limit": pagination.limit,
            "offset": pagination.offset,
        }
        if filters.project:
            params["project"] = filters.project

        data = self._request("GET", "/api/v1/search", params=params)
        return [RunSummary.model_validate(r) for r in data]

    def delete_run(self, run_id: UUID) -> bool:
        data = self._request("DELETE", f"/api/v1/runs/{run_id}")
        return data.get("deleted", False)

    def exists(self, run_id: UUID) -> bool:
        try:
            self._request("GET", f"/api/v1/runs/{run_id}/metadata")
            return True
        except TraceNotFoundError:
            return False

    def count_runs(self, filters: RunFilter | None = None) -> int:
        params: dict[str, Any] = {}
        if filters and filters.project:
            params["project"] = filters.project
        if filters and filters.status:
            if isinstance(filters.status, list):
                params["status"] = ",".join(s.value for s in filters.status)
            else:
                params["status"] = filters.status.value

        data = self._request("GET", "/api/v1/runs/count", params=params)
        return data.get("count", 0)

    def close(self) -> None:
        pass
