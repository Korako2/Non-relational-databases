#!/bin/bash
set -euo pipefail

for password in "$CH_WRITER_PASSWORD" "$CH_READER_PASSWORD"; do
    [[ "$password" =~ ^[a-zA-Z0-9]+$ ]] || exit 1
done

client=(
    clickhouse-client
    --host clickhouse
    --user lab_admin
    --password "$CH_ADMIN_PASSWORD"
    --multiquery
)

"${client[@]}" < /setup/init.sql

"${client[@]}" <<SQL
CREATE USER IF NOT EXISTS lab_writer
    IDENTIFIED WITH sha256_password BY '$CH_WRITER_PASSWORD';

GRANT INSERT ON lab4.requests TO lab_writer;

CREATE USER IF NOT EXISTS lab_grafana
    IDENTIFIED WITH sha256_password BY '$CH_READER_PASSWORD';

GRANT SELECT ON lab4.requests TO lab_grafana;
SQL

echo "Schema and users ready"