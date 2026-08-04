FROM node:22.14.0-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13.7-slim
WORKDIR /app
COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend[dev]
COPY --from=frontend-build /build/frontend/dist ./static
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
