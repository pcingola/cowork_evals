# The container that reproduces the CoWork image. See docs/docker.md for the design and
# docs/runtime.md for the inventory every version below is a row of.
#
# The build context is this directory's sibling `data/`, the two requirements files and
# nothing else. No source tree is copied and no credential is installed.

FROM ubuntu:22.04

# The Claude Code CLI version. An npm global the CoWork image does not carry, and the one
# npm delta against docs/runtime.md.
ARG CLAUDE_CODE_VERSION
# Set by buildx from --platform. The LibreOffice tarball is named by the kernel
# architecture, so it is mapped below.
ARG TARGETARCH

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

# One apt layer: the document, image, media and CLI tooling jammy already carries at the
# recorded versions, TeX Live and Graphviz, the Java 11 the tabula-py pin needs, the nine
# suppliers of /usr/lib/python3/dist-packages, the Ubuntu font stack, bubblewrap and socat,
# and the headers the sdist-only pins compile against.
#
# A package the CoWork image carries is installed here when a skill can call it: it supplies
# an executable or a library a session command uses. The VM's own plumbing, the kernel, the
# boot chain, cloud-init, udev, firmware and the ssh server, is not. docs/docker.md.
#
# bubblewrap and socat are on the CoWork image, and the harness also needs both: it refuses
# to start a granted Bash tool without them, and every case here is pinned --allow-tools
# Bash.
#
# The font list carries the Noto fallback faces and not fonts-noto-core, which alone adds
# 192 families over what docs/runtime.md records.
RUN apt-get update \
  && apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    wget \
    jq \
    git \
    bc \
    file \
    lsof \
    netcat-openbsd \
    ripgrep \
    rsync \
    unzip \
    zip \
    libxml2-utils \
    xvfb \
    graphviz \
    latexmk \
    texlive-fonts-recommended \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-xetex \
    openssh-client \
    build-essential \
    pkg-config \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    libcairo2-dev \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    libfreetype6-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    pandoc \
    poppler-utils \
    ghostscript \
    qpdf \
    tesseract-ocr \
    imagemagick \
    ffmpeg \
    default-jre-headless \
    bubblewrap \
    socat \
    command-not-found \
    pipx \
    python3-apt \
    python3-dbus \
    python3-distro-info \
    python3-gi \
    python3-pyinotify \
    ufw \
    unattended-upgrades \
    fontconfig \
    fonts-crosextra-caladea \
    fonts-crosextra-carlito \
    fonts-dejavu \
    fonts-droid-fallback \
    fonts-font-awesome \
    fonts-liberation \
    fonts-liberation2 \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-noto-mono \
    fonts-texgyre \
    fonts-urw-base35 \
    lmodern \
    libcups2 \
    libdbus-glib-1-2 \
    libgl1 \
    libice6 \
    libsm6 \
    libxinerama1 \
    libxrandr2 \
    libxrender1 \
  && rm -rf /var/lib/apt/lists/*

# An optional extra root CA, for a host whose network inspects TLS. It arrives as a build
# secret named by docker.extra_ca_file, never through the build context, and is absent on a
# network that does not intercept. docs/docker.md.
#
# The secret id below is the one container-side string this file still holds. Every other
# one is a build argument off docker/__init__.py, and a unit test asserts this id against
# EXTRA_CA_SECRET there.
ARG CONTAINER_EXTRA_CA
ENV EXTRA_CA_FILE=${CONTAINER_EXTRA_CA}
RUN --mount=type=secret,id=extra_ca \
  set -eux; \
  if [ -s /run/secrets/extra_ca ]; then \
    cp /run/secrets/extra_ca "${EXTRA_CA_FILE}"; \
    # cp preserves the secret mount's root-only mode, and the container runs as a
    # different uid. Node reads this file by path and warns and continues without it.
    chmod 0644 "${EXTRA_CA_FILE}"; \
    update-ca-certificates; \
  fi

# LibreOffice from the upstream deb set. Jammy ships 7.3, and the 26.2 pyuno is what
# unoserver==3.7 needs. It comes from the Document Foundation's archive, which keeps every
# release: the stable tree keeps only the current ones and dropped 26.2.5, so a build there
# fails with curl exit 22. The archive names the release by its full number, which is also
# what soffice reports. TARGETARCH is Docker's name for the architecture; the archive uses
# two others, one for the directory and one for the file name.
ARG LIBREOFFICE_RELEASE=26.2.5.2
RUN set -eux; \
  case "${TARGETARCH:-arm64}" in \
    arm64) lo_dir=aarch64; lo_file=aarch64 ;; \
    amd64) lo_dir=x86_64; lo_file=x86-64 ;; \
    *) echo "unsupported TARGETARCH ${TARGETARCH}" >&2; exit 1 ;; \
  esac; \
  tarball="LibreOffice_${LIBREOFFICE_RELEASE}_Linux_${lo_file}_deb.tar.gz"; \
  cd /tmp; \
  curl -fsSLO "https://downloadarchive.documentfoundation.org/libreoffice/old/${LIBREOFFICE_RELEASE}/deb/${lo_dir}/${tarball}"; \
  tar -xzf "${tarball}"; \
  dpkg -i LibreOffice_"${LIBREOFFICE_RELEASE}"*_Linux_*_deb/DEBS/*.deb; \
  rm -rf /tmp/"${tarball}" /tmp/LibreOffice_"${LIBREOFFICE_RELEASE}"*_Linux_*_deb; \
  ln -s "$(ls -d /opt/libreoffice*)" /opt/libreoffice; \
  ln -s /opt/libreoffice/program/soffice /usr/local/bin/soffice

# pyuno lives under the deb set's own program directory, so `import uno` resolves from the
# system interpreter. docs/docker.md.
ENV PYTHONPATH=/opt/libreoffice/program

# Node.js from NodeSource. Jammy ships 12.
ARG NODE_VERSION=22.23.2-1nodesource1
RUN set -eux; \
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
    | gpg --dearmor -o /usr/share/keyrings/nodesource.gpg; \
  echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list; \
  apt-get update; \
  apt-get install -y "nodejs=${NODE_VERSION}"; \
  rm -rf /var/lib/apt/lists/*

# The second global npm tree docs/runtime.md records, at its prefix and versions, and the
# two variables a session sets to expose it.
RUN npm install -g --no-fund --no-audit --prefix /usr/local/lib/node_modules_global \
  @anthropic-ai/sandbox-runtime@0.0.76 \
  docx@9.7.1 \
  graphviz@0.0.9 \
  markdown-toc@1.2.0 \
  marked@18.0.12 \
  pdf-lib@1.17.1 \
  pdfjs-dist@6.3.289 \
  pptxgenjs@4.0.1 \
  sharp@0.35.4 \
  ts-node@10.9.2 \
  tsx@4.23.13 \
  typescript@7.0.2
ENV NODE_PATH=/usr/local/lib/node_modules_global/lib/node_modules
ENV PATH=/usr/local/lib/node_modules_global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# uv, from the Astral installer. Absent from jammy.
ARG UV_VERSION=0.12.3
RUN set -eux; \
  export UV_UNMANAGED_INSTALL=/usr/local/bin; \
  curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh

# The 127 pins that install off the VM. The other 9 came from apt above, into
# /usr/lib/python3/dist-packages, where pip freeze still sees them. docs/docker.md.
ARG PIP_VERSION=25.3
COPY requirements_installable.txt /tmp/requirements_installable.txt
RUN set -eux; \
  python3 -m pip install --upgrade "pip==${PIP_VERSION}"; \
  python3 -m pip install --no-cache-dir -r /tmp/requirements_installable.txt; \
  rm /tmp/requirements_installable.txt

# The harness. Not part of the CoWork image, and the one added npm global.
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"

# The container runs with the host user's numeric uid and gid, which has no passwd entry.
# HOME is set to CONTAINER_HOME at run time, and the two mounts land under CONTAINER_WORK.
# All four are build arguments rather than literals: docker/__init__.py holds them, passes
# them here from Docker.build_args and hashes the same mapping into the image digest, so a
# path cannot be changed there and left uncreated here.
ARG CONTAINER_HOME
ARG CONTAINER_WORK
ARG CONTAINER_PLUGIN
ARG CONTAINER_LOGS
RUN mkdir -p "${CONTAINER_HOME}" "${CONTAINER_PLUGIN}" "${CONTAINER_LOGS}" \
  && chmod 0777 "${CONTAINER_HOME}" "${CONTAINER_WORK}" "${CONTAINER_PLUGIN}" "${CONTAINER_LOGS}"

# /run/shm as a real directory. jammy ships it as a symlink to /dev/shm, and bubblewrap
# mounts a tmpfs there: the symlink resolves against a new root whose /dev is not staged
# yet, so the mount fails with ENOENT. Every sandboxed command then exits 1 with `bwrap:
# Can't mount tmpfs on /newroot/run/shm`, and the model reports a broken sandbox rather
# than the command's output. `mkdir -p` alone is a no-op on the symlink, and running
# bwrap without that mount does not reach the failure.
RUN rm -f /run/shm && mkdir -p /run/shm && chmod 1777 /run/shm

# Every Bash call and hook command Claude Code runs goes through cowork-env, which gives it the
# CoWork session environment and nothing else. Managed settings rather than `docker run --env`,
# because the harness strips variables it does not know from the CLI it starts, and managed
# settings still apply inside a run. The names it keeps arrive per run in a file mounted
# read-only. docs/docker.md, "The session environment".
COPY cowork_env.sh /usr/local/bin/cowork-env
RUN chmod 0755 /usr/local/bin/cowork-env \
  && mkdir -p /etc/claude-code \
  && printf '%s\n' '{"env": {"CLAUDE_CODE_SHELL_PREFIX": "/usr/local/bin/cowork-env"}}' \
    > /etc/claude-code/managed-settings.json

WORKDIR ${CONTAINER_WORK}
