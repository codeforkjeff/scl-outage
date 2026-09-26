
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /opt/scl_outage

COPY pyproject.toml uv.lock .

RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked

COPY . .

RUN mv docker-entrypoint.sh /

VOLUME ["/opt/scl_ourage/maps", "/opt/scl_ourage/tile_cache"]

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
