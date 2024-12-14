FROM python:3.11-slim-bookworm AS base

## Basis ##
ENV ENV=prod \
    PORT=9099 \
# Install GCC and build tools. 
# These are kept in the final image to enable installing packages on the fly.
RUN apt-get update && \
    apt-get install -y gcc build-essential curl git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY ./requirements.txt .
RUN pip3 install uv
RUN uv pip install --system -r requirements.txt --no-cache-dir

# Copy the application code
COPY . .

# Expose the port
ENV HOST="0.0.0.0"
ENV PORT="9099"

ENTRYPOINT [ "bash", "start.sh" ]
