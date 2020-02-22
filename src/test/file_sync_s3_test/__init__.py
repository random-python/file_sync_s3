"""
"""

import os
import logging

console_date_format = "%Y-%m-%d %H:%M:%S"
console_record_format = "%(asctime)s %(processName)s %(levelname)-.4s %(name)12s:%(lineno)03d  %(funcName)-22s  %(message)s"

logging.basicConfig(
    level=logging.INFO,
    datefmt=console_date_format,
    format=console_record_format,
)

logging.getLogger('boto3').setLevel(logging.INFO)
logging.getLogger('botocore').setLevel(logging.INFO)
logging.getLogger('s3transfer').setLevel(logging.INFO)
logging.getLogger('urllib3').setLevel(logging.INFO)
