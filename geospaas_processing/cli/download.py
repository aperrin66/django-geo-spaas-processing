"""
Script for cli of downloading repo. This script accepts the argunemt from sys.args by the
help of python "argparse" and download the dataset files based on the input arguments.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from distutils.util import strtobool
import json
import django
import ast

from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from dateutil.tz import tzutc
from django.contrib.gis.geos import GEOSGeometry

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'geospaas_processing.settings')
django.setup()
from geospaas.catalog.models import Dataset
import geospaas_processing.downloaders as downloaders


def main(arg):
    cumulative_query = {}
    if arg.query:
        query_list = json.loads(arg.query)
        for query in query_list:
            cumulative_query.update(query)
    if arg.rel_time_flag:
        designated_begin = datetime.now().replace(tzinfo=tzutc()) + relativedelta(
            hours=-abs(int(arg.begin)))
        designated_end = datetime.now().replace(tzinfo=tzutc())
    else:
        designated_begin = datetime.strptime(arg.begin, "%Y-%m-%d").replace(tzinfo=tzutc())
        designated_end = datetime.strptime(arg.end, "%Y-%m-%d").replace(tzinfo=tzutc())
    download_manager = downloaders.DownloadManager(
        download_directory=arg.down_dir.rstrip(os.path.sep),
        provider_settings_path=arg.config_file,
        max_downloads=int(arg.number_per_day)*(((designated_end-designated_begin).days)+1),
        use_file_prefix=arg.use_filename_prefix,
        time_coverage_start__gte=designated_begin,
        time_coverage_end__lte=designated_end,
        geographic_location__geometry__intersects=GEOSGeometry(arg.geometry),
        **cumulative_query
    )
    download_manager.download()

def argparse_define():
    parser = argparse.ArgumentParser(
        description='Process the arguments of entry_point (all must be in str)')
    parser.add_argument('-d', '--down_dir', required=True, type=str,
    help="Absolute path for downloading files. If path depends on file date, usage of %Y, %m and "
    "other placeholders interpretable by strftime is accepted")
    parser.add_argument('-b', '--begin', required=True, type=str,
    help="Absolute starting date for download in the format YYYY-MM-DD or (if used together "
    "with '-r') lag in days relative to today")
    parser.add_argument('-e', '--end', required=True, type=str,
    help="Absolute ending date for download in the format YYYY-MM-DD or (if used together "
    "with '-r') has no influence.")
    parser.add_argument('-r', '--rel_time_flag', required=False, action='store_true',
    help="The flag that distinguishes between the two cases of time calcation (1.time-lag from now "
    "2.Two different points in time) based on its ABSENCE or PRESENCE in the arguments.")
    parser.add_argument('-n', '--number_per_day', required=False, type=str, default="400",
    help="limiting number of datasets that are going to be downloaded per day")
    parser.add_argument('-p', '--use_filename_prefix', action='store_true',
    help="The flag that distinguishes between the two cases of having files WITH or WITHOUT file "
    "prefix when downloaded")
    parser.add_argument('-g', '--geometry', required=False, type=str,
    help="The 'wkt' string of geometry which is acceptable by 'GEOSGeometry' of django")
    parser.add_argument('-c', '--config_file', required=False, type=str,
    help="The absolute path to the config file that is needed for configuring the downloading "
    "process. default is the same folder of the 'download.py' file")
    parser.add_argument('-q', '--query', required=False, type=str,
    help="""query exposed by user to confine the search result of database for downloading them."
    "It is a string which must be acceptable by json.loads() to for deserialization of one- or "
    "multi-criteria limitation."
    "After deserialization, it must be a list of query that are readable by django filter."
    "for example a list of elements like {'dataseturi__uri__contains': 'osisaf'}""")
    return parser.parse_args()

if __name__ == "__main__":
    arg = argparse_define()
    main(arg)
