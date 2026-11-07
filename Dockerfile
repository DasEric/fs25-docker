FROM docker.io/cubecoders/ampbase:debian@sha256:f02eb4e2cdd242b61f9e0b8c99c004842796e8c6fd7eaae6e92701c621d4f40b

RUN apt-get update \
    && apt-get install -y --no-install-recommends xdotool p7zip-full libgl1 libvulkan1 mesa-vulkan-drivers \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --user-group --uid 1000 --home-dir /home/container container \
    && mkdir -p /mnt && ln -s /home/container /mnt/server

COPY fs25/ /opt/fs25/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 USER=container HOME=/home/container
WORKDIR /home/container
# Wings overrides the runtime UID. The installer drops root to the data volume owner.
USER 0
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/bin/python3", "/opt/fs25/server.py", "start"]
