from urllib.parse import urlparse, urlunparse

from storages.backends.s3boto3 import S3Boto3Storage


class SupabasePublicStorage(S3Boto3Storage):
    """
    Custom S3 storage backend for Supabase Storage public buckets.

    Overrides ``url()`` so that ``image.url`` returns a Supabase public object URL
    instead of the S3 API endpoint URL.

    Transform:
      https://<project>.storage.supabase.co/storage/v1/s3/<bucket>/path
    → https://<project>.supabase.co/storage/v1/object/public/<bucket>/path
    """

    def url(self, name):
        s3_url = super().url(name)
        # Replace the storage API endpoint with the public object endpoint
        public_url = (
            s3_url
            .replace(".storage.supabase.co", ".supabase.co")
            .replace("/storage/v1/s3/", "/storage/v1/object/public/")
        )
        return public_url
