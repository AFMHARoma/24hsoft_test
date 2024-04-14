FROM --platform=linux/amd64 python:3.11-slim-buster

WORKDIR .
COPY . .

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install libpq-dev -y && pip3 install --upgrade pip && pip3 install -r requirements.txt --use-pep517

ENTRYPOINT ["python", "main.py"]