FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# DuckDB's S3 support is an extension. Download it now so runs don't need the internet.
RUN python -c "import duckdb; duckdb.execute('INSTALL httpfs')"

COPY . .