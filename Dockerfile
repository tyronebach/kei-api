FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data
RUN chmod +x docker-entrypoint.sh

EXPOSE 8081

CMD ["./docker-entrypoint.sh"]
