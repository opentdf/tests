#!/bin/bash -l

aws eks update-kubeconfig --region us-west-2 --name k8s-mgmt

# Submits an Argo workflow off of a Github PR event
#
#
# NOTE: In a PR context, we have to use $GITHUB_HEAD_REF to get the PR branch
# and then strip the `refs/heads/XXX` prefix off
# Note that in NON-PR contexts, $GITHUB_HEAD_REF is not defined, and you must use $GITHUB_REF instead
# For more info see: https://docs.github.com/en/actions/reference/environment-variables
    argo submit -n argo-events ./.argo/publish/pr-workflow.yaml \
        -p ciCommitSha="$GITHUB_SHA" \
        -p gitRepoName=opentdf-backend \
        -p branch="${GITHUB_HEAD_REF#refs/*/}" \
        -p gitRepoUrl="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY" \
        --wait \
        --log
# done
