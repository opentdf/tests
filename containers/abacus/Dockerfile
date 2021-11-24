ARG NODE_VERSION=16-slim
# multi-stage build

# depender - get production dependencies
FROM node:${NODE_VERSION} as depender
WORKDIR /build/
COPY abacus/web/package-lock.json .
COPY abacus/web/package.json .
RUN npm ci --production --no-audit

# builder - next build
FROM node:${NODE_VERSION} as builder
# In your Dockerfile, if you specify ARG before the FROM instruction, ARG is not available in the
# build instructions under FROM. (Ref https://docs.docker.com/compose/compose-file/#args)
ARG abacusBaseUrl=""
ARG abacusAssetPrefix=""
ARG easApiUrl=http://localhost:65432
WORKDIR /build/
# we must engage in the awkward strech of assuming a script has
# copied it into our context.
COPY service_entity_object/openapi.json service_entity_object/openapi.json
COPY service_attribute_authority/openapi.json service_attribute_authority/openapi.json
COPY service_entitlement/openapi.json service_entitlement/openapi.json
WORKDIR /build/abacus/web/
COPY abacus/web/package-lock.json .
COPY abacus/web/package.json .
RUN npm ci --no-audit
COPY abacus/web/ ./
ENV NEXT_BASE_PATH=${abacusBaseUrl}
ENV NEXT_ASSET_PREFIX=${abacusAssetPrefix}
ENV NEXT_PUBLIC_EAS_API_URL=${easApiUrl}
ENV NEXT_TELEMETRY_DISABLED=1
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
# COPY eas/openapi.yaml eas/
WORKDIR /app/abacus/web/
COPY web/package-lock.json web/package.json ./
RUN npm ci --no-audit
COPY web/ ./
CMD node_modules/.bin/next dev --port 80
