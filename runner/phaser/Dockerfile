# Reuse the existing tested Chromium/runtime image; Phaser has independent deps.
FROM gamedev-runner:1
WORKDIR /opt/runner/phaser
COPY phaser/package.json phaser/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund --maxsockets 3
COPY phaser/build.mjs phaser/verify.mjs ./
ENTRYPOINT ["node", "/opt/runner/phaser/verify.mjs"]
