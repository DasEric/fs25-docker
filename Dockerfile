FROM docker.io/cubecoders/ampbase:debian@sha256:f02eb4e2cdd242b61f9e0b8c99c004842796e8c6fd7eaae6e92701c621d4f40b AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends xdotool libgl1 libvulkan1 mesa-vulkan-drivers \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --user-group --uid 1000 --home-dir /home/container container

COPY fs25/ /opt/fs25/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

FROM base AS installer
WORKDIR /mnt/server
ENTRYPOINT []
CMD ["/usr/bin/python3", "/opt/fs25/server.py", "install"]

FROM base AS runtime
RUN mkdir -p /mnt && ln -s /home/container /mnt/server
ENV USER=container HOME=/home/container
WORKDIR /home/container
USER container
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/bin/python3", "/opt/fs25/server.py", "start"]
