"""
config parser support
"""

import datetime
import io
import logging
import os

from configparser import ConfigParser
from configparser import ExtendedInterpolation

from typing import Any
from typing import List
from typing import Mapping

logger = logging.getLogger(__name__)


class EnvironmentInterpolation(ExtendedInterpolation):
    "environment variables support"
    "smart option typing"

    def before_get(self,
            parser:ConfigParser,
            section:str, option:str, value:str, defaults:dict,
        ) -> Any:
        # environment varialbes from ${var}
        value = os.path.expandvars(value)
        # config file variables from ${var}
        value = super().before_get(parser, section, option, value, defaults)
        # parse according to declared option type
        if option.endswith("@int"):
            return int(value)
        if option.endswith("@bool"):
            return bool(value)
        if option.endswith("@float"):
            return float(value)
        if option.endswith("@bool"):
            return ConfigSupport.produce_bool(value)
        if option.endswith("@time"):
            return ConfigSupport.produce_time(value)
        if option.endswith("@timedelta"):
            return ConfigSupport.produce_timedelta(value)
        if option.endswith("@list"):
            return ConfigSupport.produce_list(value)
        if option.endswith("@dict"):
            return ConfigSupport.produce_dict(value)
        #
        return value


class RichConfigParser(ConfigParser):

    def __init__(self):
        super().__init__(self, interpolation=EnvironmentInterpolation())

    def __str__(self):
        text = io.StringIO()
        for section in self.sections():
            text.write(f"[{section}]\n")
            for (key, value) in self.items(section):
                text.write(f"{key}={value}\n")
        return text.getvalue()


class ConfigSupport:
    ""

    @classmethod
    def produce_bool(cls, text:str) -> bool:
        term = text.lower()
        if term in ("yes", "y", "true", "t", "on", "1"):
            return True
        elif term in ("no", "n", "false", "f", "off", "0"):
            return False
        else:
            raise ValueError(f"no bool: {text}")

    @classmethod
    def produce_time(cls, text:str) -> datetime.time:
        return datetime.datetime.strptime(text, "%H:%M:%S").time()

    @classmethod
    def produce_timedelta(cls, text:str) -> datetime.timedelta:
        instant = cls.produce_time(text)
        return datetime.timedelta(
            hours=instant.hour,
            minutes=instant.minute,
            seconds=instant.second,
        )

    @classmethod
    def produce_list(cls, text:str) -> List[str]:
        if "\n" in text:
            invoker = text.splitlines()
        elif "," in text:
            invoker = text.split(",")
        else:
            raise RuntimeError(f"no list: {text}")
        invoker = map(str.strip, invoker)
        invoker = filter(None, invoker)
        return list(invoker)

    @classmethod
    def produce_dict(cls, text:str) -> Mapping[str, str]:
        entry_dict = dict()
        entry_list = cls.produce_list(text)
        for entry in entry_list:
            count = entry.count("=")
            if count != 1:
                raise RuntimeError(f"no entry: {entry}")
            term_list = entry.split("=")
            key = term_list[0].strip()
            value = term_list[1].strip()
            entry_dict[key] = value
        return entry_dict

    @classmethod
    def ensure_environ(cls,) -> None:
        "provide environment variables expected by '*.ini'"
        if not os.environ.get('HOME'):
            os.environ['HOME'] = '/root'
        if not os.environ.get('PWD'):
            os.environ['PWD'] = os.getcwd()

    @classmethod
    def produce_config(cls,) -> RichConfigParser:
        "provide global configuration"

        cls.ensure_environ()

        config_parser = RichConfigParser()

        this_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = f"{this_dir}/etc/file_sync_s3"
        config_path = os.path.join(config_dir, "arkon.ini")
        config_parser.read(config_path)

        config_override_list = config_parser['config']['override@list']
        logger.info(f"config/override_list: {config_override_list}")
        config_parser.read(config_override_list)

        return config_parser


CONFIG = ConfigSupport.produce_config()
