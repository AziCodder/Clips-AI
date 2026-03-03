# Stage 1: build frontend
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
# Фронт ходит на /api/v1 (прокси nginx → api:8000)
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build

# Stage 2: serve with nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
# Конфиг монтируется из compose (infra/nginx/frontend.conf)
# Дефолтный конфиг nginx — только статика (для fallback если volume не смонтирован)
RUN echo 'server { listen 80; root /usr/share/nginx/html; index index.html; location / { try_files $uri $uri/ /index.html; } }' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
