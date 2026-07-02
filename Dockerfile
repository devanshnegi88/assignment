# =====================================================
# Stage 1 - Build React Frontend
# =====================================================

FROM node:20-alpine AS frontend-builder
# =====================================================
# Stage 1 - Build React Frontend
# =====================================================

FROM node:20-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build


# =====================================================
# Stage 2 - Python Backend
# =====================================================

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY data ./data

# Copy the React build into the location expected by FastAPI
COPY --from=frontend-builder /frontend/dist ./backend/frontend/dist

WORKDIR /app/backend

EXPOSE 10000

CMD ["sh","-c","uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build


# =====================================================
# Stage 2 - Python Backend
# =====================================================

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY data ./data

# Copy built React app
COPY --from=frontend-builder /frontend/dist ./backend/frontend/dist

WORKDIR /app/backend

EXPOSE 10000

CMD ["sh","-c","uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]