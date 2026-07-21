FROM node:22-slim

# Install Python 3, pip, and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy codebase
COPY . /app

# Install Node dependencies and build Showdown TypeScript files
RUN cd pokemon-showdown && mkdir -p dist/config && npm install && node build

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt || pip3 install --no-cache-dir -r requirements.txt

# Make start script executable
RUN chmod +x /app/start.sh

ENV PORT=8000
EXPOSE 8000

CMD ["./start.sh"]
