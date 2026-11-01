FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Set INSTALL_DEV=1 to include pytest/ruff (used by scripts/docker-test.sh).
ARG INSTALL_DEV=0
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . \
 && if [ "$INSTALL_DEV" = "1" ]; then pip install --no-cache-dir ".[dev]"; fi
COPY tests ./tests

ENTRYPOINT ["python", "-m", "app"]
CMD ["ping"]
