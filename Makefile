PYTHONPATH=apps/api/src:apps/worker/src:packages/schemas/python:packages/checklist/python:packages/eval/python
ALEMBIC_CONFIG=apps/api/alembic.ini

.PHONY: test db-upgrade db-downgrade kb-plan kb-run kb-resume kb-status kb-retry-failed

test:
	PYTHONPATH="$(PYTHONPATH)" pytest -q apps/api/tests apps/worker/tests

db-upgrade:
	PYTHONPATH="$(PYTHONPATH)" alembic -c $(ALEMBIC_CONFIG) upgrade head

db-downgrade:
	PYTHONPATH="$(PYTHONPATH)" alembic -c $(ALEMBIC_CONFIG) downgrade base

kb-plan:
	PYTHONPATH="$(PYTHONPATH)" python -m kb_pipeline.cli plan $(if $(SOURCE_ID),--source-id "$(SOURCE_ID)",) $(if $(MAX_CHUNKS),--max-chunks "$(MAX_CHUNKS)",)

kb-run:
	PYTHONPATH="$(PYTHONPATH)" python -m kb_pipeline.cli run $(if $(SOURCE_ID),--source-id "$(SOURCE_ID)",) $(if $(MAX_CHUNKS),--max-chunks "$(MAX_CHUNKS)",) $(if $(LLM_CONCURRENCY),--llm-concurrency "$(LLM_CONCURRENCY)",) $(if $(EMBED_CONCURRENCY),--embed-concurrency "$(EMBED_CONCURRENCY)",) $(if $(UPSERT_CONCURRENCY),--upsert-concurrency "$(UPSERT_CONCURRENCY)",) $(if $(REQUEST_RETRIES),--request-retries "$(REQUEST_RETRIES)",) $(if $(TIMEOUT_SECONDS),--timeout-seconds "$(TIMEOUT_SECONDS)",)

kb-resume:
	PYTHONPATH="$(PYTHONPATH)" python -m kb_pipeline.cli resume --run-id "$${RUN_ID:?set RUN_ID}" $(if $(LLM_CONCURRENCY),--llm-concurrency "$(LLM_CONCURRENCY)",) $(if $(EMBED_CONCURRENCY),--embed-concurrency "$(EMBED_CONCURRENCY)",) $(if $(UPSERT_CONCURRENCY),--upsert-concurrency "$(UPSERT_CONCURRENCY)",)

kb-status:
	PYTHONPATH="$(PYTHONPATH)" python -m kb_pipeline.cli status --run-id "$${RUN_ID:?set RUN_ID}"

kb-retry-failed:
	PYTHONPATH="$(PYTHONPATH)" python -m kb_pipeline.cli retry-failed --run-id "$${RUN_ID:?set RUN_ID}" $(if $(LLM_CONCURRENCY),--llm-concurrency "$(LLM_CONCURRENCY)",) $(if $(EMBED_CONCURRENCY),--embed-concurrency "$(EMBED_CONCURRENCY)",) $(if $(UPSERT_CONCURRENCY),--upsert-concurrency "$(UPSERT_CONCURRENCY)",)
