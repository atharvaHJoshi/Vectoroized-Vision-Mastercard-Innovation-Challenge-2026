# SentinelGraph backend image.
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY cli.py ./
COPY GRAPH_MODEL.md README.md ./

ENV PYTHONUNBUFFERED=1
ENV SG_GRAPH_FALLBACK=1

EXPOSE 8000
CMD ["python", "cli.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
