"""
summary
"""

from os.path import dirname, normpath

import pandas as pd

from src.constants import CONFIGS
from src.exception import CustomException
from src.logger import logger
from src.utils.basic_utils import (
    create_directories,
    get_lat_long,
    get_postcode,
    read_yaml,
)


class DataProcessor:
    """
    summary
    """

    def __init__(self):
        # Read the configuration files
        self.configs = read_yaml(CONFIGS).data_processor

        # Inputs
        self.scraped_data_path = normpath(self.configs.scraped_data_path)

        # Output file paths
        self.processed_data_path = normpath(self.configs.processed_data_path)

    @staticmethod
    def apply_lat_long_fn(row):
        if pd.isnull(row["latitude"]) or pd.isnull(row["longitude"]):
            coordinates = get_lat_long(row["address"])
            latitude, longitude = coordinates["lat"], coordinates["long"]
            return latitude, longitude
        else:
            return row["latitude"], row["longitude"]

    @staticmethod
    def apply_postcode_function(row):
        if pd.isnull(row["postcode"]):
            postcode = get_postcode(row["address"])[0]
            return postcode
        else:
            return row["postcode"]

    def data_transformation(self):
        try:
            # import the dataset
            df = pd.read_csv(self.scraped_data_path)
            logger.info("Dataset imported")

            # Drop duplicate rows
            df_unq = df.drop(columns="scrape_ts").drop_duplicates()
            df = df.loc[df_unq.index]
            logger.info("Duplicate entries dropped")

            # Populate latitude and longitude, if absent
            df["latitude"], df["longitude"] = zip(
                *df.apply(self.apply_lat_long_fn, axis=1)
            )
            logger.info("Latitude and Longitude populated, if absent")

            # Extract state and postcode from address
            df["state"] = df["address"].str.extract(
                r".+?((?:[A-Z]{2,3}|Victoria|Vic|Western Australia))", expand=False
            )
            df["postcode"] = df["address"].str.extract(r".* (\d{4})", expand=False)
            logger.info("State and postcode extracted from the address")

            # Handle inconsistencies in "state" column
            df["state"] = (
                df["state"]
                .str.replace(r"Vic(?:toria)?", "VIC", regex=True)
                .str.replace("Western Australia", "WA")
            )
            logger.info("Handled in the inconsistencies in the state names")

            # Populate postcode, if absent
            df["postcode"] = df.apply(self.apply_postcode_function, axis=1)
            logger.info("Postcode populated, if absent")

            # Add an index column
            custom_index_col = pd.RangeIndex(
                start=1000, stop=1000 + len(df), step=1, name="id"
            )
            df.index = custom_index_col
            df.index = "SVC" + df.index.astype("string")
            df = df.reset_index()
            logger.info("Added a unique row ID for each distinct row")

            # Unpivot "services_offered" column and strip contents
            df["services_offered"] = df["services_offered"].str.split(",")
            df_exploded = df.explode("services_offered")
            df_exploded["services_offered"] = df_exploded[
                "services_offered"
            ].str.strip()
            logger.info("Unpivot service offered column")

            # Use correct datatype for numeric columns
            df_exploded["latitude"] = pd.to_numeric(
                df_exploded["latitude"], errors="coerce"
            )
            df_exploded["longitude"] = pd.to_numeric(
                df_exploded["longitude"], errors="coerce"
            )
            df_exploded["scrape_ts"] = pd.to_datetime(df_exploded["scrape_ts"])
            logger.info("Provided proper datatype to columns")

            # Fixing issue in Longitude
            df_exploded["longitude"] = df_exploded["longitude"].apply(
                lambda x: x + 100 if x < 100 else x
            )
            logger.info("Fixing any source issues in the longitude column")

            # Rearrange columns
            new_col_order = [
                "id",
                "services_offered",
                "service_name",
                "state",
                "postcode",
                "address",
                "latitude",
                "longitude",
                "details_url",
                "scrape_ts"
            ]
            df_rearranged = df_exploded.reindex(columns=new_col_order)
            logger.info("Reordered columns")

            # Rename columns
            new_col_names = {
                "id": "RowID",
                "service_name": "Service Center",
                "address": "Address",
                "latitude": "Latitude",
                "longitude": "Longitude",
                "details_url": "Service Details URL",
                "state": "State",
                "postcode": "Postal Code",
                "services_offered": "Service",
                "scrape_ts": "Data As On",
            }
            df_renamed = df_rearranged.rename(columns=new_col_names)
            logger.info("Renamed columns with user-friendly names")

            # create save directory if not exists
            create_directories([dirname(self.processed_data_path)])

            # Export transformed data
            df_renamed.to_csv(self.processed_data_path, index=False)
            logger.info("Transformed data saved at: %s", self.processed_data_path)
            return None
        except Exception as e:
            logger.error(CustomException(e))
            raise CustomException(e) from e
