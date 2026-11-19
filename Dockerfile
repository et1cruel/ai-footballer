FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY api /app/api
COPY web /app/web
RUN mkdir -p /app/api/data
ENV PYTHONPATH=/app/api
ENV FOOTBALL_DB_PATH=/app/api/data/football.sqlite
EXPOSE 8000
CMD ["uvicorn", "football_ai.api:app", "--host", "0.0.0.0", "--port", "8000"]
