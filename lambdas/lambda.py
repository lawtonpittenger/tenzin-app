import boto3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
import io
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
    tmp_file_path = f"/tmp/{os.path.basename(key)}"

    print(f"Processing file: {key}")

    # Download the MP3 file from S3
    s3.download_file(bucket, key, tmp_file_path)

    # Open the downloaded file and read its contents
    with open(tmp_file_path, 'rb') as f:
        mp3_data = f.read()

    # Extract metadata from the MP3 file
    mp3 = MP3(io.BytesIO(mp3_data))
    duration_seconds = mp3.info.length

    # Extract artist information
    try:
        artist = str(mp3.tags['TPE1'].text[0])
        print(f"Artist: {artist}")
    except (KeyError, IndexError):
        artist = 'Unknown'
        print("Artist not found, set to 'Unknown'")

    # Format duration in minutes and seconds
    minutes, seconds = divmod(int(duration_seconds), 60)
    duration = f"{minutes}m {int(seconds)}s"
    print(f"Duration: {duration}")

    # Extract cover art from the MP3 file
    tags = ID3(io.BytesIO(mp3_data))
    cover_art_data = tags.get('APIC:')
    if cover_art_data:
        cover_art = cover_art_data.data
        print("Cover art found")
    else:
        cover_art = None
        print("No cover art found")

    if cover_art:
        # Convert cover art data to JPEG format
        cover_art_img = Image.open(io.BytesIO(cover_art))
        cover_art_bytes = io.BytesIO()
        cover_art_img.save(cover_art_bytes, format='JPEG')
        cover_art_bytes.seek(0)

        # Generate a random character string for the cover art file name
        random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        cover_art_key = f'cover_art/{random_string}_cover_art.jpg'
        print(f"Cover art key: {cover_art_key}")
        s3.put_object(Bucket=cover_art_bucket, Key=cover_art_key, Body=cover_art_bytes.getvalue(), ContentType='image/jpeg')

        # Construct the Object URL for the cover art
        cover_art_url = f'https://{cover_art_bucket}.s3.amazonaws.com/{cover_art_key}'
        print(f"Cover art URL: {cover_art_url}")
    else:
        cover_art_url = None
        print("No cover art URL")

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