# Pin the manifest so an existing local cache can build even when Docker Hub's
# tag-metadata endpoint is temporarily unreachable.
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293

WORKDIR /app

RUN apk upgrade --no-cache

COPY package*.json ./
# Install app deps, then drop the image-bundled npm tree. Trivy flags dozens of
# HIGH/CRITICAL CVEs under /usr/local/lib/node_modules/npm that are irrelevant
# once dependencies are already installed.
RUN npm ci \
    && rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx

COPY . .

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "node_modules/next/dist/bin/next", "dev", "-H", "0.0.0.0", "-p", "3000"]
