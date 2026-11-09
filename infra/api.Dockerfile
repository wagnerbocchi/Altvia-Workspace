FROM ghcr.io/astral-sh/uv@sha256:c7db1d63057f268a8b6da8af9077850a60461f98d23db23c676a82089a050c91 AS uv
FROM python@sha256:a61cbd76a882645de7f91423329fe43a67eed60d7da24f9e5331414bb3618b20 AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /opt/altvia
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-build

FROM python@sha256:a61cbd76a882645de7f91423329fe43a67eed60d7da24f9e5331414bb3618b20 AS runtime
ENV PATH="/opt/altvia/.venv/bin:$PATH" PYTHONPATH=/opt/altvia/apps/api \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/altvia
RUN addgroup -g 10001 altvia && adduser -D -H -u 10001 -G altvia altvia
# PostgreSQL is the only supported API database. Drop unused SQLite capability
# from the runtime, retaining the general-purpose builder and other stdlib modules.
RUN python -c "import pathlib,shutil,sysconfig; p=pathlib.Path(sysconfig.get_path('stdlib')); shutil.rmtree(p/'sqlite3'); [f.unlink() for f in (p/'lib-dynload').glob('_sqlite3*.so')]" \
    && rundeps="$(apk info --depends .python-rundeps | sed -n '/^so:/p' | grep -v '^so:libsqlite3.so.0$')" \
    && test -n "$rundeps" \
    && apk add --no-network --virtual .altvia-python-rundeps $rundeps \
    && apk del --no-network .python-rundeps sqlite-libs
COPY --from=dependencies /opt/altvia/.venv /opt/altvia/.venv
COPY apps/api/altvia apps/api/altvia
COPY apps/api/migrations apps/api/migrations
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY scripts/check_api_runtime.py check_api_runtime.py
USER 10001:10001
RUN python check_api_runtime.py
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health/ready',timeout=3)"]
CMD ["python", "-m", "uvicorn", "altvia.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers", "--no-access-log", "--timeout-graceful-shutdown", "20"]
