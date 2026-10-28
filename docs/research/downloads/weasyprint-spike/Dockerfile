# Throwaway spike build. Mirrors the shape of the final stage in deploy/Dockerfile
# (python:3.12-slim-bookworm + useradd), without the app.
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS base
RUN useradd --system --uid 10001 --create-home trainer

FROM base AS weasy
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir weasyprint
RUN pip install --no-cache-dir pypdf

FROM weasy AS weasy-dejavu
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# Not a real-world state: Debian fontconfig depends on some font package
# (default fonts-dejavu-core). This variant force-removes it to observe
# WeasyPrint behaviour with zero system fonts, @font-face only.
FROM weasy AS weasy-zero-fonts
RUN dpkg --remove --force-depends fonts-dejavu-core \
 && rm -rf /usr/share/fonts /var/cache/fontconfig
