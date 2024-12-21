import boto3
from mutagen.mp3 import MP3
import io
from mutagen.id3 import ID3, APIC

s3 = boto3.client('s3')
s3_resource = boto3.resource('s3')

def lambda_handler(event, context):
    # Get the bucket name and key from the event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    # Download the MP3 file from S3
    obj = s3.get_object(Bucket=bucket, Key=key)
    mp3_data = obj['Body'].read()

    # Extract metadata from the MP3 file
    mp3 = MP3(io.BytesIO(mp3_data))
    artist = str(mp3.get('artist', ['Unknown'])[0])
    duration = str(mp3.info.length)

    # Extract cover art from the MP3 file
    tags = ID3(io.BytesIO(mp3_data))
    cover_art = tags.get('APIC:').data

    # Upload cover art to a separate S3 prefix
    cover_art_key = f'cover_art/{key.rsplit("/", 1)[-1]}_cover_art'
    s3_resource.Bucket(bucket).put_object(Key=cover_art_key, Body=cover_art)
    cover_art_url = f's3://{bucket}/{cover_art_key}'

    # Add metadata and cover art URL as tags to the S3 object
    tags = [
        {'Key': 'Artist', 'Value': artist},
        {'Key': 'Duration', 'Value': duration},
        {'Key': 'CoverArt', 'Value': cover_art_url}
    ]
    s3.put_object_tagging(
        Bucket=bucket,
        Key=key,
        Tagging={'TagSet': tags}
    )

    return {
        'statusCode': 200,
        'body': f'Metadata and cover art added to {key}: Artist={artist}, Duration={duration}, CoverArt={cover_art_url}'
    }