# Dependency-only image; supply this file on stdin with no repository context.
FROM ubuntu:24.04 AS build
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 dpkg xz-utils \
    && mkdir -p /opt/evidence \
    && dpkg-query -W > /opt/evidence/dependencies.txt \
    && rm -rf /var/lib/apt/lists/*

FROM ubuntu:24.04 AS runtime
ARG RUNTIME_UID
ARG RUNTIME_GID
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-gi gir1.2-gtk-4.0 gir1.2-secret-1 gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    iproute2 adwaita-icon-theme xvfb xauth dbus-x11 fonts-dejavu-core \
    && mkdir -p /opt/evidence /home/runtime \
    && test "$RUNTIME_UID" -gt 0 && test "$RUNTIME_GID" -gt 0 \
    && if getent passwd "$RUNTIME_UID"; then userdel "$(getent passwd "$RUNTIME_UID" | cut -d: -f1)"; fi \
    && (getent group "$RUNTIME_GID" || groupadd --gid "$RUNTIME_GID" runtime) \
    && useradd --uid "$RUNTIME_UID" --gid "$RUNTIME_GID" --home-dir /home/runtime --no-create-home --shell /usr/sbin/nologin runtime \
    && chown "$RUNTIME_UID:$RUNTIME_GID" /home/runtime \
    && dpkg-query -W > /opt/evidence/dependencies.txt \
    && rm -rf /var/lib/apt/lists/*
# GstPbutils must be provided by the runtime dependency closure above. Preflight
# deliberately does not mask a missing typelib with extra build/test packages.
