ARG NODE_VERSION=lts
# multi-stage build

# depender - get production dependencies
FROM node:${NODE_VERSION} as depender
WORKDIR /build/
COPY web/package-lock.json web/package.json ./
RUN npm ci --production

# builder - next build
FROM node:${NODE_VERSION} as builder
# In your Dockerfile, if you specify ARG before the FROM instruction, ARG is not available in the
# build instructions under FROM. (Ref https://docs.docker.com/compose/compose-file/#args)
ARG abacusBaseUrl
ARG abacusAssetPrefix
ARG easApiUrl
WORKDIR /build/
# We need EAS's `openapi.yaml` file - this file should be something
# npm can pull in as a published dependency, but in the interim
# we must engage in the awkward strech of assuming a script has
# copied it into our context.
COPY eas-openapi.yaml eas/openapi.yaml
WORKDIR /build/abacus/web/
COPY web/package-lock.json web/package.json ./
RUN npm ci
COPY web/ ./
ENV NEXT_BASE_PATH=${abacusBaseUrl}
ENV NEXT_ASSET_PREFIX=${abacusAssetPrefix}
ENV NEXT_PUBLIC_EAS_API_URL=${easApiUrl}
RUN npm run build

# server - next start
FROM node:${NODE_VERSION} as server
WORKDIR /app/
EXPOSE 80
# production application code
COPY --from=builder /build/abacus/web/.next/ .next/
# production dependencies
COPY --from=depender /build/node_modules/ node_modules/
CMD node_modules/.bin/next start --port 80

# dever - runs a development server
FROM node:${NODE_VERSION} as dever
WORKDIR /app/
COPY eas/openapi.yaml eas/
WORKDIR /app/abacus/web/
COPY web/package-lock.json web/package.json ./
RUN npm ci
COPY web/ ./
CMD node_modules/.bin/next dev --port 80
