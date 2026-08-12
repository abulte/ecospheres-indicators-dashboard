.PHONY: restore

restore:
	@echo "Dropping database..."
	docker compose exec -T -u postgres db dropdb --if-exists ecospheres_dashboard
	@echo "Creating fresh database..."
	docker compose exec -T -u postgres db createdb ecospheres_dashboard
	@echo "Restoring from Dokku..."
	dokku postgres:export indicators-dashboard | docker compose exec -T -u postgres db pg_restore -v -d ecospheres_dashboard
