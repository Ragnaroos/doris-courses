"""The S3 TVF that reads the course's public bucket, shared by data-loading labs."""

from doris_labkit.db import sql_string

from .doris_client import DorisLab, s3_tvf

COURSE_S3_TVF = s3_tvf(DorisLab.S3_CONFIG)

__all__ = ["COURSE_S3_TVF", "s3_tvf", "sql_string"]
