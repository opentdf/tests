# Container image that runs your code
FROM 833190184321.dkr.ecr.us-west-2.amazonaws.com/virtru-builder:1.0.16

# Copies your code file from your action repository to the filesystem path `/` of the container
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Install Argo
# RUN curl -sSL -o /usr/local/bin/argo https://github.com/argoproj/argo/releases/download/v2.2.1/argo-linux-amd64
# RUN chmod +x /usr/local/bin/argo

# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT ["/entrypoint.sh"]
