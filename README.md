# graph-claude

GraphQL API + SQLite storage for a shared headless-Claude-Code prompt
queue. Other homelab services submit prompts here via GraphQL instead of
each building their own LLM integration; a separate CronJob (`k8s-claude`,
not part of this repo) polls for pending prompts, runs them through
`claude` headlessly, and reports results back. A `uv`-managed Python
project serving a `strawberry.federation.Schema` subgraph over plain WSGI
(`gunicorn`), same structural pattern as `graph-ad-reporter`. Deploys to
`k8s-claude`.

## Schema

This homelab namespaces each new subgraph under a single root field
(its domain name) that returns a namespace object holding the real
fields, rather than flat root `Query`/`Mutation` fields — Apollo
Federation's "nested namespace types" pattern. `graph-claude` owns the
root field `claude`:

```graphql
enum PromptStatus {
  PENDING
  COMPLETED
  FAILED
}

type PromptJob {
  id: ID!
  prompt: String!
  status: PromptStatus!
  response: String
  error: String
  createdAt: DateTime!
}

type ClaudeQuery {
  promptJob(id: ID!): PromptJob
  pendingPrompts: [PromptJob!]!
}

type ClaudeMutation {
  submitPrompt(prompt: String!): PromptJob!
  completePrompt(id: ID!, response: String!): PromptJob!
  failPrompt(id: ID!, error: String!): PromptJob!
}

type Query {
  claude: ClaudeQuery!
}

type Mutation {
  claude: ClaudeMutation!
}
```

A caller submits a prompt like:

```graphql
mutation { claude { submitPrompt(prompt: "...") { id status } } }
```

The runner CronJob discovers work via `pendingPrompts`, and a consumer
polls for the result:

```graphql
query { claude { promptJob(id: "1") { status response } } }
```

- `submitPrompt` creates a `PENDING` job.
- `pendingPrompts` returns `PENDING` jobs, oldest first, for the runner
  CronJob to pick up.
- `completePrompt` / `failPrompt` are called by the runner CronJob once a
  prompt has been run, setting status to `COMPLETED` (with `response`) or
  `FAILED` (with `error`).
- No auth on any of this, matching every other GraphQL service in this
  homelab.

## Storage

One SQLite file, path set by `CLAUDE_SERVICE_DB_PATH` (default
`/data/claude-service.db`, matching where `k8s-claude`'s PVC is
mounted):

```sql
CREATE TABLE prompt_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    response TEXT,
    error TEXT,
    created_at TEXT NOT NULL      -- ISO 8601 UTC
);
```

## Files

- `src/claude_service/db.py` — SQLite access (schema creation, CRUD).
- `src/claude_service/schema.py` — the federation schema (`PromptJob`,
  `ClaudeQuery`, `ClaudeMutation`) under the namespaced `claude` root
  field.
- `src/claude_service/wsgi.py` — the WSGI app: `/graphql` (POST), `/version`.
- `scripts/verify-deploy.sh` — polls `/version` post-publish until it
  matches the just-built commit SHA.

## Local setup

```sh
nix-shell -p uv python312
uv sync
uv run pytest
```

## `/version`

Returns `{"commit_sha": ...}`, baked in at image build time via the
`COMMIT_SHA` build arg (see `Dockerfile`). `k8s-claude`'s `PostSync`
verify Job polls this to confirm the live pod is running the
just-deployed commit.
