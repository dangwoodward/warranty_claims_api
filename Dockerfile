FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY warranty_module.py warranty_server.py models.py main.py ./

EXPOSE 8000

# The API process spawns the MCP warranty server as a subprocess over stdio,
# so only uvicorn needs to be started here.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
