FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    hping3 \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY attacker.py .

CMD ["python", "attacker.py"]