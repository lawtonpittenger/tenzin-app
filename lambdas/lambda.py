import boto3
import os
from PIL import Image
import random
import string

s3 = boto3.client('s3')
s3_resource = boto3.resource('s3')

def lambda_handler(event, context):
    # Get the bucket name and key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    cover_art_bucket = 'cover-art-bucket-777'
    key = event['Records'][0]['s3']['object']['key']

    print(f"Processing file: {key}")

    # Get metadata from the S3 object
    response = s3.head_object(Bucket=bucket, Key=key)
    metadata = response.get('Metadata', {})

    print(f"Metadata received from S3: {metadata}")

    artist = metadata.get('artist', 'Unknown')
    duration = metadata.get('duration', 'Unknown')
    cover_art_url = metadata.get('cover_art', None)

    print(f"Artist: {artist}")
    print(f"Duration: {duration}")

    if cover_art_url:
        print(f"Cover art URL: {cover_art_url}")
    else:
        print("No cover art found")
        cover_art_url = None

    # Add metadata and cover art URL as tags to the S3 object
    tags = [
        {'Key': 'Artist', 'Value': artist},
        {'Key': 'Duration', 'Value': duration},
    ]
    if cover_art_url:
        tags.append({'Key': 'CoverArt', 'Value': cover_art_url})
        print(f"Adding CoverArt tag: {cover_art_url}")

    print(f"Adding tags to {key}: {tags}")

    s3.put_object_tagging(
        Bucket=bucket,
        Key=key,
        Tagging={'TagSet': tags}
    )

    return {
        'statusCode': 200,
        'body': f'Metadata and cover art added to {key}: Artist={artist}, Duration={duration}, CoverArt={cover_art_url}'
    }