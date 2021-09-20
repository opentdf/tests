# kaitai-struct-compile via docker
# Reference: 'install on ubuntu' instructions on https://kaitai.io
#
# Compile nanotdf.ksy:
#     docker build --tag ksc:0.8 --target compiler .
#     docker run -it --volume "$PWD":/workdir ksc:0.8 \
#       --target python \
#       --outdir build/gencode \
#       nanotdf.ksy
FROM ubuntu:focal as compiler
RUN buildDeps='ca-certificates curl' \
    && apt-get update \
    && apt-get install -y $buildDeps python --no-install-recommends
RUN curl -LO https://github.com/kaitai-io/kaitai_struct_compiler/releases/download/0.9/kaitai-struct-compiler_0.9_all.deb \
    && apt-get install -y ./kaitai-struct-compiler_0.9_all.deb
WORKDIR /workdir
ENTRYPOINT ["/usr/bin/kaitai-struct-compiler"]
