ARG NODE_VERSION=lts
# multi-stage build

# depender - get production dependencies
FROM node:${NODE_VERSION} as depender
WORKDIR /build/
COPY package-lock.json package.json ./
RUN npm ci

# builder - create-react-app build
FROM depender as builder
WORKDIR /build/
COPY public/ public/
COPY src/ src/
COPY tsconfig.json/ .
RUN npm run build

# server - nginx alpine
FROM nginx:stable-alpine as server
COPY --from=builder /build/build /usr/share/nginx/html
COPY nginx-default.conf /etc/nginx/templates/default.conf.template
ENV KEYCLOAK_HOST "http://localhost/keycloak/auth"
ENV KEYCLOAK_CLIENT_ID ""
ENV KEYCLOAK_REALM ""
ENV ATTRIBUTES_HOST "http://localhost/attributes"

EXPOSE 80
