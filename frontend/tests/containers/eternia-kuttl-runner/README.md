# eternia-kuttl-runner

This container simply stands on the shoulders of https://github.com/virtru/eternia/blob/master/Dockerfile and embeds some Bash scripts that invoke `sdk-cli` with the appropriate arguments.

To do this it assumes `eternia` was cloned alongside `etheria`, `cd`s into that repo, builds the image, then creates a new image using that `eternia` image as the base, using `eternia`'s HEAD gitref as the image tag.

This dependency on `etheria`'s build image is only necessary because these tests rely on a currently unpublished version of `sdk-cli` with OIDC support. Once a version of `sdk-cli` with OIDC support is published to public NPM, we can simply `npm install` it in this container, and drop the dependecy on the `eternia` repo.
