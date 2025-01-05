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
import random
import string

log = logging.getLogger()
log.setLevel(logging.INFO)

aws_region = os.environ["AWS_REGION"]
s3_client = boto3.client("s3", region_name=aws_region)


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
        mediainfo_result = cast(dict, MediaInfo.parse(signed_url, library_file=pymediainfo_library_file, cover_data=True))
        mediainfo_data = mediainfo_result.to_data()
        analyzed_file_type = mediainfo_data["tracks"][0].get("internet_media_type")
        analyzed_file_name_extension = mediainfo_data["tracks"][0].get("file_name_extension")
        log.info(f"Saved MediaInfo result for {key} ({analyzed_file_type})")

        # Save MediaInfo to an S3 object
        try:
            s3_client.put_object(
                Body=str(mediainfo_result.to_json()),
                Bucket=s3_bucket_name,
                Key=f"{s3_bucket_prefix}/{analyzed_file_name_extension}.mediainfo.json"
            )
        except Exception as ex:
            log.error(f"Failed to write MediaInfo result to S3: {ex}")

        # Extract desired metadata
        duration = mediainfo_data["tracks"][0].get("other_duration")[0]
        artist = mediainfo_data["tracks"][0].get("album_performer") or "Unknown Artist"
        album = mediainfo_data["tracks"][0].get("album") or "Unknown Album"
        track = mediainfo_data["tracks"][0]

        # Extract cover art data
        cover_art_data = None
        if 'cover_data' in track:
            cover_art_data = track['cover_data']

        # Prepare the tag set
        tag_set = [
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

        # Upload cover art to the same S3 bucket
        if cover_art_data:
            try:
                log.info(f"Cover art data found")
                cover_art_bytes = base64.b64decode(cover_art_data)
                log.info(f"Cover art bytes decoded successfully")
                cover_art_image = Image.open(io.BytesIO(cover_art_bytes))
                log.info(f"Cover art image opened successfully")

                # Convert cover art image to JPEG format
                cover_art_bytes_jpeg = io.BytesIO()
                cover_art_image.save(cover_art_bytes_jpeg, format='JPEG')
                cover_art_bytes_jpeg.seek(0)
                log.info(f"Cover art image converted to JPEG format successfully")

                # Generate a random string for the cover art file name
                random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
                cover_art_key = f"{s3_bucket_prefix}/{random_string}_cover_art.jpg"
                log.info(f"Cover art key: {cover_art_key}")

                s3_client.put_object(
                    Bucket=s3_bucket_name,
                    Key=cover_art_key,
                    Body=cover_art_bytes_jpeg.getvalue(),
                    ContentType="image/jpeg"
                )
                log.info(f"Cover art uploaded to S3 successfully")

                # Construct the Object URL for the cover art
                cover_art_url = f"https://{s3_bucket_name}.s3.amazonaws.com/{cover_art_key}"
                log.info(f"Cover art URL: {cover_art_url}")

                # Add the cover art URL to the tag set
                tag_set.append({
                    "Key": "CoverArt",
                    "Value": cover_art_url
                })
            except Exception as ex:
                log.error(f"Failed to upload cover art to S3: {ex}")
        else:
            log.info("No cover art data found")

        # Add metadata tags to the original S3 object
        try:
            s3_client.put_object_tagging(
                Bucket=bucket_name,
                Key=key,
                Tagging={
                    "TagSet": tag_set
                }
            )
            log.info(f"Metadata tags added to the original S3 object")
        except Exception as ex:
            log.error(f"Failed to add tags to S3 object: {ex}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": (f"MediaInfo ran successfully with results saved to s3://{s3_bucket_name}/{s3_bucket_prefix}")
        })
    }