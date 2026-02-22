PYTHONPATH=apps/api/src:packages/schemas/python:packages/checklist/python:packages/eval/python:packages/registry/python
ALEMBIC_CONFIG=apps/api/alembic.ini

.PHONY: test db-upgrade db-downgrade registry-seed registry-fetch registry-diff registry-draft registry-status

test:
	PYTHONPATH="$(PYTHONPATH)" pytest -q apps/api/tests

db-upgrade:
	PYTHONPATH="$(PYTHONPATH)" alembic -c $(ALEMBIC_CONFIG) upgrade head

db-downgrade:
	PYTHONPATH="$(PYTHONPATH)" alembic -c $(ALEMBIC_CONFIG) downgrade base

registry-seed:
	PYTHONPATH="$(PYTHONPATH)" python -m dpa_registry.cli seed

registry-fetch:
	PYTHONPATH="$(PYTHONPATH)" python -m dpa_registry.cli fetch

registry-diff:
	PYTHONPATH="$(PYTHONPATH)" python -m dpa_registry.cli diff

registry-draft:
	PYTHONPATH="$(PYTHONPATH)" python -m dpa_registry.cli draft --policy-version "$${POLICY_VERSION:?set POLICY_VERSION}"

registry-status:
	PYTHONPATH="$(PYTHONPATH)" python -m dpa_registry.cli status
