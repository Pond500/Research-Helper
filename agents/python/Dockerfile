FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install dependencies from pyproject.toml (source of truth)
COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache .

# Copy source after deps to leverage layer cache
COPY . .

EXPOSE 10236

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10236"]
