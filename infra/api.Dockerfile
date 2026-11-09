FROM ghcr.io/astral-sh/uv@sha256:c7db1d63057f268a8b6da8af9077850a60461f98d23db23c676a82089a050c91 AS uv
FROM python@sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4 AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /opt/altvia
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python@sha256:0f086103b026048cc50cb5da25ec435c023c5241a83fc44daea593377abc61c4 AS runtime
ENV PATH="/opt/altvia/.venv/bin:$PATH" PYTHONPATH=/opt/altvia/apps/api \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/altvia
RUN groupadd --gid 10001 altvia && useradd --uid 10001 --gid 10001 --no-create-home altvia
COPY --from=dependencies /opt/altvia/.venv /opt/altvia/.venv
COPY apps/api/altvia apps/api/altvia
COPY apps/api/migrations apps/api/migrations
COPY apps/api/alembic.ini apps/api/alembic.ini
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health/ready',timeout=3)"]
CMD ["python", "-m", "uvicorn", "altvia.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers", "--no-access-log", "--timeout-graceful-shutdown", "20"]
