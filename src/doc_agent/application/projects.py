"""Project use cases."""

from __future__ import annotations

from doc_agent.domain.models import Project
from doc_agent.ports.repositories import DocumentRepository


class ProjectService:
    def __init__(self, repository: DocumentRepository) -> None:
        self.repository = repository

    def create(self, name: str) -> Project:
        return self.repository.create_project(name.strip())

    def list(self) -> list[Project]:
        return self.repository.list_projects()

    def get(self, project_id: str) -> Project:
        return self.repository.get_project(project_id)
