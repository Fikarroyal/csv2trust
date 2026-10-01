web:
	cd apps/web && npm install && npm run dev

api:
	cd apps/api && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload

test:
	cd apps/api && python3 -m pytest -q

docker:
	docker compose up --build
