FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN npm install --global @openai/codex

WORKDIR /service
COPY requirements.txt .
RUN python3 -m pip install --break-system-packages --no-cache-dir -r requirements.txt
COPY app.py .
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8001
CMD ["./start.sh"]
