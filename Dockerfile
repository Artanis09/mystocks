# Multi-stage build for mystocks application

# ==========================================
# Stage 1: Build Frontend
# ==========================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# Copy frontend source files
COPY *.tsx *.ts *.css *.html ./
COPY components/ ./components/
COPY services/ ./services/
COPY public/ ./public/
COPY vite.config.ts tsconfig.json ./

# Build frontend
RUN npm run build

# ==========================================
# Stage 2: Production Image
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements and install
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python application files
COPY update_stock_prices.py crawl.py debug_kis.py ./
COPY config.ini ./
COPY ml/ ./ml/
COPY scripts/ ./scripts/
COPY data/ ./data/

# Copy built frontend from builder stage
COPY --from=frontend-builder /app/dist ./static

# Create .env file placeholder
RUN touch .env

# Expose ports
# 5000: Flask Backend API
# 3000: Frontend (for development)
EXPOSE 5000

# Environment variables
ENV FLASK_APP=update_stock_prices.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Start Flask server
CMD ["python", "update_stock_prices.py"]
