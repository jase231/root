FROM quay.io/pypa/manylinux_2_28_x86_64

# Recent ccache (static binary, no repo dependency)
ARG CCACHE_VERSION=4.13.6
RUN curl -fsSL -o /tmp/cc.tar.xz \
      https://github.com/ccache/ccache/releases/download/v${CCACHE_VERSION}/ccache-${CCACHE_VERSION}-linux-x86_64-glibc.tar.gz \
 && tar -xf /tmp/cc.tar.xz -C /tmp \
 && install /tmp/ccache-${CCACHE_VERSION}-linux-x86_64-glibc/ccache /usr/local/bin/ccache \
 && rm -rf /tmp/cc*

# Install system dependencies
RUN dnf install -y epel-release && /usr/bin/crb enable && dnf install -y openssl-devel libX11-devel libXpm-devel libXft-devel libXext-devel libuuid-devel libjpeg-devel giflib-devel libtiff-devel

# Cache content lives in a mounted volume (/ccache); the rest are stability knobs.
ENV CCACHE_DIR=/ccache \
    CCACHE_BASEDIR=/project \
    CCACHE_NOHASHDIR=1 \
    CCACHE_COMPILERCHECK=content \
    CCACHE_SLOPPINESS=time_macros,include_file_mtime,include_file_ctime,locale \
    CCACHE_MAXSIZE=5G

# CMake reads these env vars to route every compile through ccache.
ENV CMAKE_C_COMPILER_LAUNCHER=ccache \
    CMAKE_CXX_COMPILER_LAUNCHER=ccache

# This image is consumed as cibuildwheel's manylinux base image
# (CIBW_MANYLINUX_X86_64_IMAGE) by build-wheels.sh. It must NOT set an ENTRYPOINT:
# cibuildwheel runs its own build/repair commands inside the image. cibuildwheel
# mounts the project at /project, which matches CCACHE_BASEDIR above.
WORKDIR /project
