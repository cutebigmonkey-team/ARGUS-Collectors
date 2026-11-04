FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock requirements-postgres.lock ./
RUN pip install --no-cache-dir -r requirements.lock -r requirements-postgres.lock
COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
COPY deploy/hostless/check_database.py ./check_database.py
RUN pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home collector
ENV PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
CMD ["python", "check_database.py"]
