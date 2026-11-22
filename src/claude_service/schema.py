# Apollo Federation subgraph schema for the claude service.
# Uses strawberry.federation.Schema to enable the _service { sdl } introspection
# field that Apollo Gateway/Router needs for subgraph composition.
#
# Namespaced under a single root field (claude) per this homelab's
# nested-namespace-type convention for new subgraphs: composition merges each
# subgraph's one root field into the supergraph without needing @shareable,
# since the field name and its namespace types are unique to this subgraph.
import datetime
import enum

import strawberry

from claude_service import db


@strawberry.enum
class PromptStatus(enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@strawberry.federation.type
class PromptJob:
    id: strawberry.ID
    prompt: str
    status: PromptStatus
    response: str | None
    error: str | None
    created_at: datetime.datetime


def _job_from_row(row: db.PromptJobRow) -> PromptJob:
    return PromptJob(
        id=strawberry.ID(str(row.id)),
        prompt=row.prompt,
        status=PromptStatus(row.status),
        response=row.response,
        error=row.error,
        created_at=datetime.datetime.fromisoformat(row.created_at),
    )


@strawberry.type
class ClaudeQuery:
    @strawberry.field
    def prompt_job(self, id: strawberry.ID) -> PromptJob | None:
        row = db.get_prompt_job(int(id))
        return None if row is None else _job_from_row(row)

    @strawberry.field
    def pending_prompts(self) -> list[PromptJob]:
        return [_job_from_row(row) for row in db.pending_prompts()]


@strawberry.type
class ClaudeMutation:
    @strawberry.field
    def submit_prompt(self, prompt: str) -> PromptJob:
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        row = db.insert_prompt_job(prompt=prompt, created_at=timestamp)
        return _job_from_row(row)

    @strawberry.field
    def complete_prompt(self, id: strawberry.ID, response: str) -> PromptJob:
        row = db.complete_prompt_job(int(id), response)
        if row is None:
            raise ValueError(f"prompt job {id} not found")
        return _job_from_row(row)

    @strawberry.field
    def fail_prompt(self, id: strawberry.ID, error: str) -> PromptJob:
        row = db.fail_prompt_job(int(id), error)
        if row is None:
            raise ValueError(f"prompt job {id} not found")
        return _job_from_row(row)


@strawberry.type
class Query:
    @strawberry.field
    def claude(self) -> ClaudeQuery:
        return ClaudeQuery()


@strawberry.type
class Mutation:
    @strawberry.field
    def claude(self) -> ClaudeMutation:
        return ClaudeMutation()


schema = strawberry.federation.Schema(query=Query, mutation=Mutation)
