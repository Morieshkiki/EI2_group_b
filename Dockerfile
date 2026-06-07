# generated using AI: builds the web app's Docker image — installs the Python
# dependencies and starts the FastAPI server inside the container.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install build tools and Node.js (Node runs app/convert/convert.js to convert IFC -> XKT)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Install Node dependencies (@xeokit/xeokit-convert) used by the IFC -> XKT converter
COPY package.json package-lock.json ./
RUN npm install

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
