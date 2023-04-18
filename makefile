SHELL := /bin/bash

ENV ?= dev
SAM_ROOT = deploy

export AWS_PROFILE := ${ENV}

local-build:
	source env/secrets/${ENV}.sh && \
	cd AppLambda && \
	uvicorn src.app:app --reload --port 9000

deployment:
	poetry export -f requirements.txt --output AppLambda/requirements.txt
	sam build \
		--template-file $(SAM_ROOT)/template.yaml \
		--config-file samconfig-$(ENV).toml \

	sam deploy \
		--config-file $(SAM_ROOT)/samconfig-$(ENV).toml \
