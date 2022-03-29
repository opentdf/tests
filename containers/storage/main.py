import json
import logging
import os
import sys
import uuid as uuid
from enum import Enum
from http import HTTPStatus
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic.main import BaseModel

logging.basicConfig(
    stream=sys.stdout, level=os.getenv("SERVER_LOG_LEVEL", "CRITICAL").upper()
)
logger = logging.getLogger(__package__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=(os.environ.get("CORS_ORIGINS", "").split(",")),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


class StorageMultipartFields(BaseModel):
    key: Optional[str] = ""
    AWSAccessKeyId: Optional[str] = ""
    AWSSecretAccessKey: Optional[str] = ""
    AWSSessionToken: Optional[str] = ""
    policy: Optional[str] = ""
    signature: Optional[str] = ""


class StorageMultipart(BaseModel):
    url: Optional[str] = ""
    bucket: Optional[str] = ""
    fields: StorageMultipartFields = StorageMultipartFields()

    class Config:
        schema_extra = {
            "example": {
                "url": "https://s3.amazonaws.com/datalake",
                "fields": {
                    "key": "tdf/987a663b-1c72-44a0-8b86-320e4bd49bd3",
                    "AWSAccessKeyId": "AKIAZJJC2YYD",
                    "AWSSecretAccessKey": "p7TAy1E9nKt",
                    "AWSSessionToken": "FwoGZXIvYXdzEFUaDLgAkQsFe8UsYIM8QyLBArxychGzO2hI",
                    "policy": "eyJleHBpcmF0aW9uIjogIjIwMjEtMDUtMTlUMTY6MzI6MTJaIiwgImNvbmRpdGlvbnMiOiBbeyJidWNrZXQiO",
                    "signature": "WmazvDuLzr96mPf6M6zVI8=",
                },
            }
        }


@app.on_event("startup")
async def startup():
    s3 = boto3.resource("s3")
    s3.meta.client.head_bucket(Bucket=os.getenv("BUCKET"))


@app.get("/v2/storage", response_model=StorageMultipart)
async def create_storage():
    payload_key = str(uuid.uuid4())
    name = os.getenv("BUCKET")
    sts_client = boto3.client("sts")
    # https://docs.aws.amazon.com/STS/latest/APIReference/API_GetFederationToken.html
    token = sts_client.get_federation_token(
        Name="uploader",
        Policy='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"s3:ListAllMyBuckets","Resource":"arn:aws:s3:::*"},{"Effect":"Allow","Action":["s3:ListBucket","s3:GetBucketLocation"],"Resource":"arn:aws:s3:::'
        + name
        + '"},{"Effect":"Allow","Action":["s3:PutObject","s3:PutObjectAcl","s3:GetObject","s3:GetObjectAcl","s3:DeleteObject"],"Resource":"arn:aws:s3:::'
        + name
        + '/*"}]}',
        DurationSeconds=900,
    )
    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=token["Credentials"]["AccessKeyId"],
            aws_secret_access_key=token["Credentials"]["SecretAccessKey"],
            aws_session_token=token["Credentials"]["SessionToken"],
        )
        presigned = s3_client.generate_presigned_post(
            Bucket=name,
            Key=f"tdf/{payload_key}",
            Fields=dict(acl="public-read"),
            Conditions=[{"acl": "public-read"}],
            ExpiresIn=3600,
        )
        return StorageMultipart(
            url=presigned["url"],
            bucket=name,
            fields=StorageMultipartFields(
                key=presigned["fields"]["key"],
                AWSAccessKeyId=presigned["fields"]["AWSAccessKeyId"],
                AWSSecretAccessKey=token["Credentials"]["SecretAccessKey"],
                AWSSessionToken=token["Credentials"]["SessionToken"],
                policy=presigned["fields"]["policy"],
                signature=presigned["fields"]["signature"],
            ),
        )
    except ClientError as e:
        logger.error(e)
        raise HTTPException(status_code=400, detail=f"{str(e)}") from e


class ProbeType(str, Enum):
    liveness = "liveness"
    readiness = "readiness"


@app.get("/healthz", status_code=HTTPStatus.NO_CONTENT, include_in_schema=False)
async def read_liveness(probe: ProbeType = ProbeType.liveness):
    if probe == ProbeType.readiness:
        s3 = boto3.resource("s3")
        try:
            s3.Bucket(os.getenv("BUCKET"))
        except ClientError as e:
            logger.error(e)
            raise HTTPException(status_code=500, detail=f"{str(e)}") from e
    return Response()  # empty response


if __name__ == "__main__":
    print(json.dumps(app.openapi()), file=sys.stdout)
