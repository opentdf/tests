#!/usr/bin/env sh
export NGINX_HOST
export ENV_URL
export KAS_URL
export EAS_ENTITY_ID_HEADER

echo "Reverse proxy starting..."

###
# SET_PKI_MODE determines if PKI should be enabled or disabled
IS_PKI_ON="#" # PKI config lines will be commented out
if [ "$SET_PKI_MODE" = "on" ]; then
  IS_PKI_ON="" # PKI config lines will be enabled
  echo "PKI mode is on"
else
  echo "PKI mode is off"
fi
export IS_PKI_ON
###

# Nginx configuration cannot use engironment variables. This allows us to control the variables from docker-compose.yml
# https://github.com/docker-library/docs/tree/master/nginx#using-environment-variables-in-nginx-configuration
# In this case we are making sure we can set the NGINX_HOST, EAS_URL, and KAS_URL from compose
envsubst "\$EAS_ENTITY_ID_HEADER \$IS_PKI_ON \$NGINX_HOST \$ABACUS_URL \$EAS_URL \$KAS_URL" </etc/nginx/nginx.template >/etc/nginx/nginx.conf

nginx -g 'daemon off;'
