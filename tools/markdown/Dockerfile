# Official node:22.14.0-bookworm-slim multi-platform manifest, resolved from Docker Hub.
FROM node:22.14.0-bookworm-slim@sha256:1c18d9ab3af4585870b92e4dbc5cac5a0dc77dd13df1a5905cea89fc720eb05b
WORKDIR /opt/markdown
# Dependency acquisition only: no repository source or lifecycle scripts run here.
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund && npm cache clean --force
USER 1000:1000
ENV HOME=/tmp
