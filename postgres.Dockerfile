FROM postgres:17

COPY migrations/*_up.sql /docker-entrypoint-initdb.d/
