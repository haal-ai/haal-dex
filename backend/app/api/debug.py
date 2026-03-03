from __future__ import annotations

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Query

router = APIRouter(tags=["debug"])


@router.get("/api/debug/aws-identity")
def aws_identity() -> dict:
    profile = os.getenv("AWS_PROFILE")
    region_env = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    sdk_load_config = os.getenv("AWS_SDK_LOAD_CONFIG")

    session = boto3.Session(profile_name=profile or None, region_name=region_env or None)
    resolved_profile = session.profile_name
    resolved_region = session.region_name

    try:
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        caller = {
            "Account": identity.get("Account"),
            "Arn": identity.get("Arn"),
            "UserId": identity.get("UserId"),
        }
        return {
            "env": {
                "AWS_PROFILE": profile,
                "AWS_REGION": os.getenv("AWS_REGION"),
                "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION"),
                "AWS_SDK_LOAD_CONFIG": sdk_load_config,
            },
            "boto3": {
                "profile_name": resolved_profile,
                "region_name": resolved_region,
            },
            "sts": caller,
        }
    except (ClientError, BotoCoreError) as e:
        return {
            "env": {
                "AWS_PROFILE": profile,
                "AWS_REGION": os.getenv("AWS_REGION"),
                "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION"),
                "AWS_SDK_LOAD_CONFIG": sdk_load_config,
            },
            "boto3": {
                "profile_name": resolved_profile,
                "region_name": resolved_region,
            },
            "error": str(e),
        }


@router.get("/api/debug/bedrock/models")
def bedrock_models() -> dict:
    profile = os.getenv("AWS_PROFILE")
    region_env = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    session = boto3.Session(profile_name=profile or None, region_name=region_env or None)

    try:
        bedrock = session.client("bedrock")
        resp = bedrock.list_foundation_models()
        models = resp.get("modelSummaries") or []
        simplified = []
        for m in models:
            simplified.append(
                {
                    "modelId": m.get("modelId"),
                    "modelName": m.get("modelName"),
                    "providerName": m.get("providerName"),
                    "inputModalities": m.get("inputModalities"),
                    "outputModalities": m.get("outputModalities"),
                    "responseStreamingSupported": m.get("responseStreamingSupported"),
                }
            )

        return {
            "boto3": {"profile_name": session.profile_name, "region_name": session.region_name},
            "count": len(simplified),
            "models": simplified,
        }
    except (ClientError, BotoCoreError) as e:
        return {
            "boto3": {"profile_name": session.profile_name, "region_name": session.region_name},
            "error": str(e),
        }


@router.get("/api/debug/bedrock/probe-converse")
def bedrock_probe_converse(
    model_id: str = Query(...),
    text: str = Query("ping"),
) -> dict:
    profile = os.getenv("AWS_PROFILE")
    region_env = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    session = boto3.Session(profile_name=profile or None, region_name=region_env or None)

    try:
        runtime = session.client("bedrock-runtime")
        resp = runtime.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": text}],
                }
            ],
        )

        message = (resp.get("output") or {}).get("message") or {}
        content = message.get("content") or []
        text_out = None
        if content and isinstance(content, list) and isinstance(content[0], dict):
            text_out = content[0].get("text")

        return {
            "boto3": {"profile_name": session.profile_name, "region_name": session.region_name},
            "model_id": model_id,
            "ok": True,
            "output_text": text_out,
        }
    except (ClientError, BotoCoreError) as e:
        return {
            "boto3": {"profile_name": session.profile_name, "region_name": session.region_name},
            "model_id": model_id,
            "ok": False,
            "error": str(e),
        }


@router.get("/api/debug/bedrock/inference-profiles")
def bedrock_inference_profiles() -> dict:
    profile = os.getenv("AWS_PROFILE")
    region_env = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    session = boto3.Session(profile_name=profile or None, region_name=region_env or None)

    try:
        bedrock = session.client("bedrock")

        # API availability varies by boto3/botocore version and account.
        if not hasattr(bedrock, "list_inference_profiles"):
            return {
                "boto3": {"profile_name": session.profile_name, "region_name": session.region_name},
                "error": "boto3 bedrock client does not support list_inference_profiles() in this environment",
            }

        resp = bedrock.list_inference_profiles()
        profiles = resp.get("inferenceProfileSummaries") or resp.get("inferenceProfiles") or []
        simplified = []
        for p in profiles:
            simplified.append(
                {
                    "inferenceProfileId": p.get("inferenceProfileId") or p.get("id"),
                    "inferenceProfileArn": p.get("inferenceProfileArn") or p.get("arn"),
                    "inferenceProfileName": p.get("inferenceProfileName") or p.get("name"),
                    "status": p.get("status"),
                    "modelArn": p.get("modelArn"),
                    "modelId": p.get("modelId"),
                }
            )

        return {
            "boto3": {"profile_name": session.profile_name, "region_name": session.region_name},
            "count": len(simplified),
            "inference_profiles": simplified,
        }
    except (ClientError, BotoCoreError) as e:
        return {
            "boto3": {"profile_name": session.profile_name, "region_name": session.region_name},
            "error": str(e),
        }
