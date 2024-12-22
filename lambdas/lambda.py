import boto3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from PIL import Image
import ffmpeg
import tempfile
import io
import os



s3 = boto3.client('s3')

def lambda_handler(event, context):
    # Get the bucket name and key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    cover_art_bucket = 'cover-art-bucket-777'
    key = event['Records'][0]['s3']['object']['key']
    tmp_file_path = f"/tmp/{os.path.basename(key)}"
    
    # Get the file extension
    file_extension = key.split('.')[-1].lower()

    # Convert the file to MP3 if it's not already in that format
    if file_extension not in ['mp3']:
        # Download the file from S3
        tmp_download_path = f"/tmp/{os.path.basename(key)}"
        s3.download_file(bucket, key, tmp_download_path)

        # Convert the file to MP3
        tmp_mp3_path = f"/tmp/{os.path.splitext(os.path.basename(key))[0]}.mp3"
        stream = ffmpeg.input(tmp_download_path)
        stream = ffmpeg.output(stream, tmp_mp3_path, codec='libmp3lame', qscale=2)
        ffmpeg.run(stream)

        # Replace the original file path with the converted MP3 file path
        tmp_file_path = tmp_mp3_path
    else:
        # Download the MP3 file from S3
        tmp_file_path = f"/tmp/{os.path.basename(key)}"
        s3.download_file(bucket, key, tmp_file_path)

    # Open the downloaded file and read its contents
    with open(tmp_file_path, 'rb') as f:
        mp3_data = f.read()

    # Extract metadata from the MP3 file
    mp3 = MP3(io.BytesIO(mp3_data))
    artist = str(mp3.get('Authors', ['Unknown'])[0])
    duration_seconds = mp3.info.length

    # Format duration in minutes and seconds
    minutes, seconds = divmod(int(duration_seconds), 60)
    duration = f"{minutes}m {int(seconds)}s"

    # Extract cover art from the MP3 file
    tags = ID3(io.BytesIO(mp3_data))
    cover_art_data = tags.get('APIC:')
    if cover_art_data:
        cover_art = cover_art_data.data
    else:
        cover_art = None

    if cover_art:
        # Upload cover art to a separate S3 prefix
        cover_art_key = f'cover_art/{key.rsplit("/", 1)[-1]}_cover_art'
        s3.put_object(Bucket=cover_art_bucket, Key=cover_art_key, Body=cover_art)
        cover_art_url = f's3://{cover_art_bucket}/{cover_art_key}'
    else:
        cover_art_url = None

    # Add metadata and cover art URL as tags to the S3 object
    tags = [
        {'Key': 'Artist', 'Value': artist},
        {'Key': 'Duration', 'Value': duration},
    ]
    if cover_art_url:
        tags.append({'Key': 'CoverArt', 'Value': cover_art_url})

    s3.put_object_tagging(
        Bucket=bucket,
        Key=key,
        Tagging={'TagSet': tags}
    )

    return {
        'statusCode': 200,
        'body': f'Metadata and cover art added to {key}: Artist={artist}, Duration={duration}, CoverArt={cover_art_url}'
    }