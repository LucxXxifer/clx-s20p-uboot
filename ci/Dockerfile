# SPDX-License-Identifier: GPL-2.0
FROM ubuntu:22.04@sha256:e0f80c829509ef4df9e76bd8944eb7b8ec25cbb379b112a7f9448b2c77a77c9b
SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
# Dated, signed APT metadata pins the complete compiler/native dependency set.
RUN printf '%s\n' \
    'deb [check-valid-until=no] http://snapshot.ubuntu.com/ubuntu/20261026T000000Z jammy main universe' \
    'deb [check-valid-until=no] http://snapshot.ubuntu.com/ubuntu/20261026T000000Z jammy-updates main universe' \
    'deb [check-valid-until=no] http://snapshot.ubuntu.com/ubuntu/20261026T000000Z jammy-security main universe' \
    > /etc/apt/sources.list \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
       ca-certificates curl xz-utils build-essential gcc-aarch64-linux-gnu \
       flex bison libssl-dev device-tree-compiler python3 python3-dev \
       python3-setuptools swig libgnutls28-dev bc git \
    && rm -rf /var/lib/apt/lists/*
RUN curl --fail --location --retry 3 \
      https://nodejs.org/dist/v22.20.0/node-v22.20.0-linux-x64.tar.xz -o /tmp/node.tar.xz \
    && printf '%s\n' '00bbd05e306ea68b6e13e17360d0e2f680b493ef95f2fea1c4296ff7437530bc  /tmp/node.tar.xz' | sha256sum --check \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.xz
ENV LC_ALL=C TZ=UTC PYTHONDONTWRITEBYTECODE=1
WORKDIR /source
