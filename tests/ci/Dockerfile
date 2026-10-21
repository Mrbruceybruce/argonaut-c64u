# Build with stdin and an empty context: no application source enters the image.
FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 python3-gi gir1.2-gtk-4.0 gir1.2-secret-1 \
    gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-tools iproute2 util-linux \
    xvfb xauth dbus-x11 libxtst6 fonts-dejavu-core \
    && mkdir -p /usr/local/share/argonaut-ci \
    && dpkg-query -W > /usr/local/share/argonaut-ci/dependencies.txt \
    && rm -rf /var/lib/apt/lists/*
