import boto3
import base64
import json
import logging
import os
from pymediainfo import MediaInfo
from typing import cast
from botocore.config import Config
from PIL import Image
import io

log = logging.getLogger()
log.setLevel(logging.INFO)

aws_region = os.environ["AWS_REGION"]


def get_signed_url(expires_in, bucket, key):
    """
    Generate a signed URL
    * param expires_in:  URL Expiration time in seconds
    * param bucket:      S3 Bucket name
    * param key:         S3 Key name
    * return:            Signed URL
    """
    s3_cli = boto3.client("s3", region_name=aws_region, config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    presigned_url = s3_cli.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in)
    return presigned_url


def lambda_handler(event, context):
    """Process S3 events for MediaInfo analysis

    Returns:

    """
    # MediaInfo library location in AWS Lambda layer
    pymediainfo_library_file = "/opt/libmediainfo.so"

    s3_bucket_name = os.environ["BUCKET_NAME"]
    s3_bucket_prefix = os.environ["BUCKET_PREFIX"]
    log.info(f"\nBucket name: {s3_bucket_name}\nBucket prefix: {s3_bucket_prefix}")

    # Process S3 events
    for record in event["Records"]:
        s3_event = record["s3"]
        bucket_name = s3_event["bucket"]["name"]
        key = s3_event["object"]["key"]
        log.info(f"Media file to analyze: {bucket_name}/{key}")

        # Get presigned S3 URL
        signed_url = get_signed_url(300, bucket_name, key)

        # Get MediaInfo report directly from S3
        mediainfo_result = cast(dict, MediaInfo.parse(signed_url, library_file=pymediainfo_library_file))
        mediainfo_data = mediainfo_result.to_data()
        analyzed_file_type = mediainfo_data["tracks"][0].get("internet_media_type")
        log.info(f"Saved MediaInfo result for {key} ({analyzed_file_type})")

        # Extract desired metadata
        duration = mediainfo_data["tracks"][0].get("other_duration")[0]
        artist = mediainfo_data["tracks"][0].get("album_performer")
        album = mediainfo_data["tracks"][0].get("album")
        cover_art_data = mediainfo_data["tracks"][0].get("cover")

        # Add metadata tags to the original S3 object
        try:
            s3_client = boto3.client("s3")
            s3_client.put_object_tagging(
                Bucket=bucket_name,
                Key=key,
                Tagging={
                    "TagSet": [
                        {
                            "Key": "Duration",
                            "Value": duration
                        },
                        {
                            "Key": "Artist",
                            "Value": artist
                        },
                        {
                            "Key": "Album",
                            "Value": album
                        }
                    ]
                }
            )
        except Exception as ex:
            log.error(f"Failed to add tags to S3 object: {ex}")

        # Upload cover art to the output S3 bucket
        if cover_art_data and "," in cover_art_data:
            try:
                cover_art_bytes = base64.b64decode(cover_art_data.split(",", 1)[1])
                cover_art_image = Image.open(io.BytesIO(cover_art_bytes))
                cover_art_key = f"{s3_bucket_prefix}/{key.split('/')[-1]}.jpg"
                
                # Save cover art as JPEG
                jpeg_buffer = io.BytesIO()
                cover_art_image.save(jpeg_buffer, format="JPEG")
                jpeg_buffer.seek(0)

                s3_client.put_object(
                    Body=jpeg_buffer,
                    Bucket=s3_bucket_name,
                    Key=cover_art_key,
                    ContentType="image/jpeg"
                )
                s3_client.put_object_tagging(
                    Bucket=s3_bucket_name,
                    Key=key,
                    Tagging={
                        "TagSet": [
                            {
                                "Key": "CoverArt",
                                "Value": f"s3://{s3_bucket_name}/{cover_art_key}"
                            }
                        ]
                    }
                )
            except Exception as ex:
                log.error(f"Failed to upload cover art to S3: {ex}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": (f"MediaInfo ran successfully with results saved to s3://{s3_bucket_name}/{s3_bucket_prefix}")
        })
    }