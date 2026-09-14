# The build helper checks and records the locally tested base image and bundle.
ARG RUNNER_IMAGE=gamedev-runner:1
FROM ${RUNNER_IMAGE}
WORKDIR /opt/opengame
COPY upstream/ ./
COPY npm-cache/ /opt/npm-seed/
RUN --mount=type=cache,id=ludraft-opengame-npm,target=/root/.npm \
    cp -a /opt/npm-seed/. /root/.npm/ \
 && npm ci --omit=dev --ignore-scripts --no-audit --no-fund --prefer-offline --maxsockets 2 --fetch-timeout 120000 --fetch-retries 2 \
 && npm rebuild sharp --foreground-scripts \
 && rm -rf /opt/npm-seed
COPY bridge.mjs /opt/ludraft/bridge.mjs
COPY manifest.json /opt/ludraft/manifest.json
ARG BRIDGE_SHA
LABEL com.ludraft.opengame.bridge-sha256=${BRIDGE_SHA}
LABEL com.ludraft.opengame.commit="c9bea37786af524bf3bbe802f2b67d23816fa5c0"
LABEL com.ludraft.opengame.cli-sha256="10d1201f0b1ad1415360c1d7cd9ca3ac307deef4c9e10d696931abc174e6b0bb"
USER 1000:1000
WORKDIR /tmp
ENV HOME=/tmp/home
ENTRYPOINT ["node", "/opt/ludraft/bridge.mjs"]
