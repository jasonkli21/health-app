FROM python:3.12.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/services/api/src \
    PORT=8080

WORKDIR /app

COPY services/api/requirements-runtime.lock /tmp/requirements-runtime.lock
RUN python -m pip install --no-cache-dir --require-hashes --no-deps \
      -r /tmp/requirements-runtime.lock \
    && groupadd --system --gid 10001 health \
    && useradd --system --uid 10001 --gid health --home-dir /nonexistent \
      --shell /usr/sbin/nologin health \
    && install -d -o 10001 -g 10001 -m 0700 /app/.data/objects

COPY --chown=10001:10001 services/api/src /app/services/api/src
COPY --chown=10001:10001 migrations /app/migrations
COPY --chown=10001:10001 alembic.ini /app/alembic.ini

USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM

# Cloud Run injects PORT. The same image can run Alembic as a separate Job by
# overriding the command; migrations never execute in the serving process.
CMD ["sh", "-c", "exec uvicorn health_api.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --workers 1 --timeout-graceful-shutdown 8"]
