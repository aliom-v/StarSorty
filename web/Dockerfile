FROM node:20-alpine AS builder

WORKDIR /app

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.25-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/out /usr/share/nginx/html

EXPOSE 80
