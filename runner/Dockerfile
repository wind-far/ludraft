ARG NODE_IMAGE=public.ecr.aws/docker/library/node:22-bookworm-slim
FROM ${NODE_IMAGE}
WORKDIR /opt/runner
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
# Bootstrap HTTPS using Node's bundled public Mozilla CA roots; verification remains enabled.
RUN mkdir -p /etc/ssl/certs && node -e "require('fs').writeFileSync('/etc/ssl/certs/ca-certificates.crt',require('tls').rootCertificates.join('\n'))" \
 && sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
 && echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries \
 && apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates fonts-wqy-zenhei libasound2 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 \
 && rm -rf /var/lib/apt/lists/*
RUN npx playwright install --only-shell chromium && rm -rf /root/.npm
COPY verify.mjs match3-verify.mjs mobile-verify.mjs ./
ENV NODE_ENV=production
ENTRYPOINT ["node", "/opt/runner/verify.mjs"]
