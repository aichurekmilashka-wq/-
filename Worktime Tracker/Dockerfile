FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json ./
RUN npm install
COPY components ./components
COPY lib ./lib
COPY src ./src
COPY tsconfig.json vite.config.mts ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements-hosted.txt ./
RUN pip install --no-cache-dir -r requirements-hosted.txt
COPY . .
COPY --from=frontend /build/static/widgets.js /build/static/widgets.css ./static/
ENV PORT=10000
ENV WORKTIME_DB_PATH=/tmp/worktime-demo.sqlite3
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 60 'hosted:create_app()'"]
