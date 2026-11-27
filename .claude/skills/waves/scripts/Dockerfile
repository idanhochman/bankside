# The waves tool's image: GTKWave on a virtual display, to grab waveform
# images, and fst2vcd for text tables. Built locally by ./waves on first use
# and tagged with a hash of this file. Pinned (base image by digest, GTKWave by
# version) so every machine draws the same pixels: `waves png --check` compares
# images byte for byte.
FROM ubuntu:24.04@sha256:562111b88caa79c71391c0c4d3c2114a7d5c35915c20561fd893cb1e07929e6b
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      gtkwave=3.3.116-1build2 xvfb xauth fonts-dejavu-core \
      python3 python3-yaml python3-pil \
 && rm -rf /var/lib/apt/lists/*
