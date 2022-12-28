build:
	AWS_ACCESS_KEY_ID=$(AWS_ACCESS_KEY_ID)
	AWS_SECRET_ACCESS_KEY=$(AWS_SECRET_ACCESS_KEY)

	cd AppLambda; \
	uvicorn src.app:app --reload --port 9000


deployment:
	AWS_ACCESS_KEY_ID=$(AWS_ACCESS_KEY_ID)
	AWS_SECRET_ACCESS_KEY=$(AWS_SECRET_ACCESS_KEY)

	poetry export -f requirements.txt --output AppLambda/requirements.txt
	sam build
	sam deploy \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--s3-bucket $(S3_BUCKET) \
		--capabilities CAPABILITY_IAM \
		--tags "Project=unifiedShoppingList" \