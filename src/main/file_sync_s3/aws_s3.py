"""
amazon aws s3 file sync support
"""

import os
import asyncio
import logging
import threading

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone

import boto3
from boto3.s3.transfer import TransferConfig

from file_sync_s3.config import CONFIG
from file_sync_s3.logster import logster_duration

logger = logging.getLogger(__name__)

frozen = dataclass(frozen=True)


async def asyncio_exec(func, *args):
    ""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)


@frozen
class AuthBucketS3:
    "account and access identity"

    config_entry = "amazon/access"

    region_name:str
    bucket_name:str
    object_mode:str
    access_key:str
    secret_key:str

    @classmethod
    def default(cls) -> "AuthBucketS3":
        section = CONFIG[cls.config_entry]
        return cls(
            region_name=section['region_name'],
            bucket_name=section['bucket_name'],
            object_mode=section['object_mode'],
            access_key=section['access_key'],
            secret_key=section['secret_key'],
        )


@frozen
class ConfigTransferS3:
    ""

    config_entry = "amazon/transfer"

    max_io_queue:int
    max_concurrency:int
    io_chunksize:int
    multipart_chunksize:int

    @classmethod
    def default(cls) -> TransferConfig:
        ""
        section = CONFIG[cls.config_entry]
        return TransferConfig(
            max_io_queue=section['max_io_queue@int'],
            max_concurrency=section['max_concurrency@int'],
            io_chunksize=section['io_chunksize@int'],
            multipart_chunksize=section['multipart_chunksize@int'],
        )


@frozen
class MetaEntryS3:
    "local/remot resource meta info"

    length: int  # file/object size
    modified:datetime  # file/object time

    def has_none(self) -> bool:
        "detect if this meta represents a 'NONE' value"
        return self.length == 0 and self.modified == SupportFuncS3.convert_unix_time(0)


class SupportFuncS3:
    "map between local and remot meta format"
    "https://docs.aws.amazon.com/AmazonS3/latest/dev/UsingMetadata.html#object-metadata"

    key_Metadata = "Metadata"
    key_entry_length = "entry_length"
    key_entry_modified = "entry_modified"

    @classmethod
    def convert_date_time(cls, date_time:datetime) -> float:
        "map from python date time into unix time"
        return date_time.replace(tzinfo=timezone.utc).timestamp()

    @classmethod
    def convert_unix_time(cls, unix_time:float) -> datetime:
        "map from unix time into python date time"
        unix_secs = int(unix_time)
        base_time = datetime.utcfromtimestamp(unix_secs)
        return base_time.replace(tzinfo=timezone.utc)

    @classmethod
    def meta_encode_args(cls, meta_data:MetaEntryS3) -> dict:
        "map from local meta into remot meta"
        return {
            cls.key_Metadata : {
                cls.key_entry_length : str(meta_data.length),
                cls.key_entry_modified : meta_data.modified.isoformat(),
            }
        }

    @classmethod
    def meta_decode_head(cls, head_object:dict) -> MetaEntryS3:
        "map from remot meta into local meta"
        meta_data = head_object[cls.key_Metadata]
        return MetaEntryS3(
            length=int(meta_data[cls.key_entry_length]),
            modified=datetime.fromisoformat(meta_data[cls.key_entry_modified]),
        )

    @classmethod
    def meta_nothing(cls) -> MetaEntryS3:
        "produce a 'NONE' representation for file meta data"
        return MetaEntryS3(
            length=0,
            modified=SupportFuncS3.convert_unix_time(0),
        )


class ProgressReportS3:
    "transfer progress reporter"

    def __init__(self, total_size:int, perc_step:float=4.0):
        self.update_lock = threading.Lock()
        self.wired_size = 0
        self.total_size = total_size
        self.perc_step = perc_step
        self.percent = 0

    def __call__(self, block_size:int) -> None:
        with self.update_lock:
            self.wired_size += block_size
        percent = 100 * self.wired_size / self.total_size
        if percent - self.percent > self.perc_step:
            self.percent = percent
            self.report_progress()

    def report_progress(self):
        logger.info(f"{self.percent:6.2f}% {self.wired_size:,}")


class BucketOperatorS3:
    "amazon bucket resource operations"

    def __init__(self,
            config_access:AuthBucketS3=None,
            config_transfer:TransferConfig=None,
        ):
        self.config_access = config_access or AuthBucketS3.default()
        self.config_transfer = config_transfer or ConfigTransferS3.default()
        self.session = boto3.session.Session(
            region_name=self.config_access.region_name,
            aws_access_key_id=self.config_access.access_key,
            aws_secret_access_key=self.config_access.secret_key,
        )

    def client_s3(self) -> "Client":
        "produce aws s3 client"
        return self.session.client('s3')

    def local_meta(self, entry:str) -> MetaEntryS3:
        "discover local file meta data"
        if os.path.isfile(entry):
            length = os.path.getsize(entry)
            modified = SupportFuncS3.convert_unix_time(os.path.getmtime(entry))
        elif os.path.isdir(entry):
            length = 0
            modified = SupportFuncS3.convert_unix_time(os.path.getmtime(entry))
        else:
            length = 0
            modified = SupportFuncS3.convert_unix_time(0)
        return MetaEntryS3(
            length=length,
            modified=modified,
        )

    def remot_meta(self, entry:str) -> MetaEntryS3:
        "discover remot object meta data"
        try:
            head_object = self.client_s3().head_object(
                Bucket=self.config_access.bucket_name,
                Key=entry,
            )
            return SupportFuncS3.meta_decode_head(head_object)
        except:
            return SupportFuncS3.meta_nothing()

    async def resource_delete(self,
            remot_path:str,
        ) -> None:
        "remove file from remot bucket"
        await asyncio_exec(self.resource_delete_sync, remot_path)

    def resource_delete_sync(self,
            remot_path:str,
        ) -> None:
        "remove file from remot bucket"

        logger.info(f"remot: {remot_path}")

        self.client_s3().delete_object(
            Bucket=self.config_access.bucket_name,
            Key=remot_path,
        )

    async def resource_get(self,
            local_path:str,
            remot_path:str,
            use_check:bool=True,
        ) -> None:
        "transfer file from remot into local"
        await asyncio_exec(self.resource_get_sync, local_path, remot_path, use_check)

    @logster_duration
    def resource_get_sync(self,
            local_path:str,
            remot_path:str,
            use_check:bool=True,
        ) -> None:
        "transfer file from remot into local"

        logger.info(f"local: {local_path}")
        logger.info(f"remot: {remot_path}")

        local_meta = self.local_meta(local_path)
        remot_meta = self.remot_meta(remot_path)

        if use_check and (local_meta == remot_meta):
            logger.info(f"no change")
            return

        extra_args = dict()

        total_size = remot_meta.length
        logger.info(f"total: {total_size:,}")

        self.client_s3().download_file(
            Bucket=self.config_access.bucket_name,
            Filename=local_path,
            Key=remot_path,
            ExtraArgs=extra_args,
            Config=self.config_transfer,
            Callback=ProgressReportS3(total_size),
        )

        meta_time = SupportFuncS3.convert_date_time(remot_meta.modified)

        os.utime(local_path, (meta_time, meta_time))

        local_meta = self.local_meta(local_path)
        if local_meta != remot_meta:
            raise RuntimeError(f"wrong transfer")

    async def resource_put(self,
            local_path:str,
            remot_path:str,
            use_check:bool=True,
        ) -> None:
        "transfer file from local into remot"
        await asyncio_exec(self.resource_put_sync, local_path, remot_path, use_check)

    @logster_duration
    def resource_put_sync(self,
            local_path:str,
            remot_path:str,
            use_check:bool=True,
        ) -> None:
        "transfer file from local into remot"

        logger.info(f"local: {local_path}")
        logger.info(f"remot: {remot_path}")

        local_meta = self.local_meta(local_path)
        remot_meta = self.remot_meta(remot_path)

        if use_check and (local_meta == remot_meta):
            logger.info(f"no change")
            return

        extra_args = dict(
            # https://docs.aws.amazon.com/AmazonS3/latest/dev/acl-overview.html#canned-acl
            ACL=self.config_access.object_mode,
        )
        extra_args.update(SupportFuncS3.meta_encode_args(local_meta))

        total_size = local_meta.length
        logger.info(f"total: {total_size:,}")

        self.client_s3().upload_file(
            Bucket=self.config_access.bucket_name,
            Filename=local_path,
            Key=remot_path,
            ExtraArgs=extra_args,
            Config=self.config_transfer,
            Callback=ProgressReportS3(total_size),
        )
