#!/bin/sh
# Grafana's database account: may connect and SELECT from the analytics schema,
# nothing else. It cannot write, and it cannot see any other schema.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v reader_password="$GRAFANA_READER_PASSWORD" <<'SQL'
CREATE ROLE grafana_reader LOGIN PASSWORD :'reader_password';
REVOKE ALL ON SCHEMA public FROM grafana_reader;
GRANT CONNECT ON DATABASE argus_analytics TO grafana_reader;
GRANT USAGE ON SCHEMA analytics TO grafana_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO grafana_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO grafana_reader;
ALTER ROLE grafana_reader SET default_transaction_read_only = on;
SQL
