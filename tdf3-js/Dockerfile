ARG NODE_VERSION=latest
# multi-stage build

# stage intermediate only
FROM node:${NODE_VERSION} as builder
WORKDIR /build/
COPY . .
RUN npm ci
RUN npm run build
# runner - node environment
FROM node:${NODE_VERSION} as runner
ARG CODE_VERSION=0.0.0
WORKDIR /app/
COPY --from=builder /build/build/ /app/
COPY --from=builder /build/node_modules/ /app/node_modules/
# server - browser environemnt
FROM nginx:stable as server
ARG CODE_VERSION=0.0.0
COPY --from=builder /build/build/ /usr/share/nginx/html/
