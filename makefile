ENV ?= dev
SAM_ROOT = deploy

build:
	cd AppLambda; \
	uvicorn src.app:app --reload --port 9000

deployment:
	poetry export -f requirements.txt --output AppLambda/requirements.txt
	sam build \
		--template-file $(SAM_ROOT)/template.yaml \
		--config-file samconfig-$(ENV).toml \

	sam deploy \
		--config-file $(SAM_ROOT)/samconfig-$(ENV).toml \