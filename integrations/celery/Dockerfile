FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY app /app/app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
