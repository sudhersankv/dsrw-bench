APP ?= dsrw-bench
STORE ?= jsonl:out/results.jsonl
CONFIGS = configs/pilot.yaml configs/r1_steady.yaml configs/r2_reversal.yaml configs/r3_ladder.yaml

.PHONY: test gates demo analyze web dry-run fly-secrets fly-deploy

test:
	uv run pytest -q

gates:
	uv run swb gates

demo:
	uv run swb demo

analyze:
	uv run swb analyze --store $(STORE) --out web/public/data

web:
	cd web && npm ci && npm run build

dry-run:
	uv run swb dry-run $(CONFIGS)

# Only NAME=value lines go to Fly, through stdin, so no value reaches the terminal or argv.
fly-secrets:
	@test -f .env || { echo ".env not found; copy .env.example first"; exit 1; }
	@grep -E '^[A-Za-z_][A-Za-z0-9_]*=.+' .env | fly secrets import --stage --app $(APP)
	@echo "Secrets staged for $(APP); they apply on the next make fly-deploy."

fly-deploy:
	fly deploy --app $(APP)
