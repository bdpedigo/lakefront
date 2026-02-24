# %%
import os
import subprocess
import time
from functools import partial

import numpy as np
import pandas as pd
import polars as pl
import requests
from caveclient import CAVEclient
from cloudpathlib import AnyPath as Path
from cloudpathlib import GSPath
from cloudvolume import CloudVolume
from deltalake import DeltaTable, write_deltalake
from deltalake.table import TableOptimizer
from deltalake.writer import BloomFilterProperties, ColumnProperties, WriterProperties
from shapely import wkb


def make_csv_dump_request(table_name: str, client: CAVEclient) -> int:
    """
    Trigger CSV dump for a materialization table.

    Parameters
    ----------
    table_name : str
        Name of the table to dump.
    client : CAVEclient
        An instance of CAVEclient to use for authentication and API access. Should have
        version set.
    """
    base_url = f"{client.info.get_datastack_info()['local_server']}/materialize"
    endpoint = f"/api/v2/materialize/run/dump_csv_table/datastack/{client.datastack_name}/version/{client.version}/table_name/{table_name}/"

    url = base_url + endpoint

    # Headers to match the working curl command
    headers = client.auth.request_header

    print(f"Making request to dump table {table_name} via API...")

    # Make POST request with empty data like curl -d ''
    response = requests.post(url, headers=headers, data="")

    print(f"Response status code: {response.status_code}")

    if response.status_code == 200:
        return 1
    else:
        # Try to extract error message from JSON response
        try:
            error_data = response.json()
            error_message = error_data.get("message", "No error message provided")

            # Handle specific case where another operation is in progress
            if (
                response.status_code == 500
                and "another operation was already in progress" in error_message.lower()
            ):
                print("Another operation is in progress. Server is busy.")
                print("Please try again later.")
                return -1

            # For other 500 errors, show the full response
            elif response.status_code == 500:
                print(f"Full error response: {error_data}")

        except (ValueError, requests.exceptions.JSONDecodeError):
            print("API returned an error but no JSON error message could be parsed")
            print(f"Response text: {response.text}")

        return 0


def trigger_csv_dump(
    table_name: str, client: CAVEclient, max_timeout_minutes=60
) -> int:
    """
    Trigger CSV dump for a materialization table.

    Parameters
    ----------
    table_name : str
        Name of the table to dump.
    client : CAVEclient
        An instance of CAVEclient to use for authentication and API access. Should have
        version set.
    """
    back = 0
    wait_times = 0
    while back != 1 and wait_times < max_timeout_minutes:
        back = make_csv_dump_request(table_name, client)
        if back == -1:
            # If another operation is in progress, wait before retrying
            print("Waiting for 1 minute before retrying...")
            print(f"Waited {wait_times} minutes so far.")
            time.sleep(60)  # Wait for 1 minute before retrying
            wait_times += 1
        elif back == 0:
            # For other errors, you might want to break the loop or handle differently
            print("An error occurred while triggering CSV dump. Exiting.")
            return False

    if back == 1:
        print("CSV dump triggered successfully!")
        return True
    else:
        print(
            f"Failed to trigger CSV dump after waiting for {max_timeout_minutes} minutes. Please check the server status."
        )
        return False


# %%

total_time = time.time()

# %%

# PARAMETERS
# ----------

# ---Table details---

# cloud base path for mat dbs - this is currently not advertised anywhere and you need
# to know where it is for your datastack
# mat_db_cloud_path = "gs://mat_dbs/public/"
mat_db_cloud_path = os.getenv(
    "MAT_DB_CLOUD_PATH", "gs://cave_annotation_bucket/public/"
)

# name of the datastack
# datastack = "zheng_ca3"
datastack = os.getenv("DATASTACK", "v1dd")

# name of the table or view to process
# table_name = "synapses_ca3_v1_filtered_view"
table_name = os.getenv("TABLE_NAME", "synapses_v1dd")
segmentation_postfix = os.getenv("SEGMENTATION_POSTFIX", "__aibs_v1dd")
if segmentation_postfix == "":
    has_segmentation = False
else:
    has_segmentation = True

# materialization version
# version = 357
version = int(os.getenv("VERSION", "1196"))

# columns to drop from the table if seen, no error if any are missing
DROP_COLUMNS = ["created", "deleted", "superceded_id", "valid"]

# ---Processing details---

# number of rows to process and write at a time - bigger is usually better, up to
# memory limits
n_rows_per_chunk = int(os.getenv("N_ROWS_PER_CHUNK", "50000000"))

# where to put the output
out_path = os.getenv(
    "OUT_PATH",
    f"/Users/ben.pedigo/code/meshrep/meshrep/data/{datastack}_{table_name}_deltalake_v{version}",
)

# ---Deltalake output details---

# column to use for partitioning when writing to deltalake
# TODO could extend to multiple columns if desired
partition_columns_str = os.getenv("PARTITION_COLUMNS", "pt_root_id")
partition_columns = [
    col.strip() for col in partition_columns_str.split(",") if col.strip()
]

# number of partitions to create
n_partitions = int(os.getenv("N_PARTITIONS", "64"))

# whether to convert ids to segmentation ids before partitioning
# NOTE: I haven't seen any advantage to doing this so far
use_seg_id = False

# Z-order curve columns for optimizing the table after writing
zorder_columns_str = os.getenv("ZORDER_COLUMNS", "post_pt_root_id,id")
zorder_columns = [col.strip() for col in zorder_columns_str.split(",") if col.strip()]

# columns to add bloom filters to, can be empty list
bloom_filter_columns_str = os.getenv("BLOOM_FILTER_COLUMNS", "id")
bloom_filter_columns = [
    col.strip() for col in bloom_filter_columns_str.split(",") if col.strip()
]

# false positive probability for the bloom filters
fpp = float(os.getenv("FPP", "0.001"))

# FOR TESTING

datastack = "v1dd"
version = 1196
table_name = "proofreading_status_and_strategy"
segmentation_postfix = "__aibs_v1dd"
mat_db_cloud_path = "gs://cave_annotation_bucket/public"
n_partitions = 1
zorder_columns = ["pt_root_id", "id"]
bloom_filter_columns = []

# print out all parameters for reference
print()
print("Parameters:")
print("-----------------")
print(f"mat_db_cloud_path: {mat_db_cloud_path}")
print(f"datastack: {datastack}")
print(f"table_name: {table_name}")
print(f"segmentation_postfix: {segmentation_postfix}")
print(f"version: {version}")
print(f"n_rows_per_chunk: {n_rows_per_chunk}")
print(f"out_path: {out_path}")
print(f"partition_columns: {partition_columns}")
print(f"n_partitions: {n_partitions}")
print(f"use_seg_id: {use_seg_id}")
print(f"zorder_columns: {zorder_columns}")
print(f"bloom_filter_columns: {bloom_filter_columns}")
print(f"fpp: {fpp}")
print()


# %%

segmentation_table_name = f"{table_name}{segmentation_postfix}"
table_names = [table_name]
if has_segmentation:
    table_names.append(segmentation_table_name)

for table in table_names:
    success = trigger_csv_dump(table, CAVEclient(datastack, version=version))
    if not success:
        raise RuntimeError(f"Failed to trigger CSV dump for table {table}")

    # TODO need to add a wait here for the time between request and being done
    # exists = CloudFile(
    #     f"{mat_db_cloud_path}{datastack}/v{version}/{table}.csv.gz"
    # ).exists()
    # # assert exists, (
    # #     f"CSV dump for table {table} does not exist at expected path {mat_db_cloud_path}/{datastack}/v{version}/{table}.csv.gz after triggering dump"
    # # )
    # print(
    #     f"CSV dump for table {table} at {mat_db_cloud_path}/{datastack}/v{version}/{table}.csv.gz exists: {exists}"
    # )

# %%


base_cloud_path = GSPath(f"{mat_db_cloud_path}/{datastack}/v{version}")
table_file_name = f"{table_name}.csv.gz"
header_file_name = f"{table_name}_header.csv"
table_cloud_path = base_cloud_path / table_file_name
header_cloud_path = base_cloud_path / header_file_name

table_cloud_paths = {table_name: table_cloud_path}
header_cloud_paths = {table_name: header_cloud_path}

if has_segmentation:
    seg_table_cloud_path = base_cloud_path / f"{segmentation_table_name}.csv.gz"
    seg_table_header_cloud_path = (
        base_cloud_path / f"{segmentation_table_name}_header.csv"
    )
    table_cloud_paths[segmentation_table_name] = seg_table_cloud_path
    header_cloud_paths[segmentation_table_name] = seg_table_header_cloud_path


# %%

# print()
# # check the file sizes and that they exist
# print(f"Table size: {table_cloud_path.stat().st_size / 1e9:.3f} GB")
# print(f"Header size: {header_cloud_path.stat().st_size / 1e3:.3f} KB")
# if has_segmentation:
#     print(
#         f"Segmentation table size: {seg_table_cloud_path.stat().st_size / 1e9:.3f} GB"
#     )
#     print(
#         f"Segmentation header size: {seg_table_header_cloud_path.stat().st_size / 1e3:.3f} KB"
#     )

# print()

# %%
# download the table and header files locally

download_time = time.time()

print("Downloading table and header files...")

temp_path = Path("/tmp/table_to_deltalake")
temp_path.mkdir(exist_ok=True)  # ty: ignore


for table in table_names:
    subprocess.run(
        [
            "gsutil",
            "cp",
            str(table_cloud_paths[table]),
            str(temp_path / table_cloud_paths[table].name),  # ty: ignore
        ]
    )
    subprocess.run(
        [
            "gsutil",
            "cp",
            str(header_cloud_paths[table]),
            str(temp_path / header_cloud_paths[table].name),  # ty: ignore
        ]
    )

print(f"{time.time() - download_time:.3f} seconds elapsed to download files.")
print()

# %%
# unzip the table
# this was more reliable for large files than using pandas/polars unzip directly for me

unzip_time = time.time()

print("Unzipping table file...")

table_local_path = temp_path / table_file_name  # ty: ignore
header_local_path = temp_path / header_file_name  # ty: ignore

table_local_paths = {table_name: table_local_path}
header_local_paths = {table_name: header_local_path}
if has_segmentation:
    seg_table_local_path = temp_path / f"{segmentation_table_name}.csv.gz"  # ty: ignore
    seg_table_header_local_path = (
        temp_path / f"{segmentation_table_name}_header.csv"  # ty: ignore
    )
    table_local_paths[segmentation_table_name] = seg_table_local_path
    header_local_paths[segmentation_table_name] = seg_table_header_local_path

for table in table_names:
    subprocess.run(
        [
            "gunzip",
            str(table_local_paths[table]),
        ]
    )
    table_local_path = temp_path / f"{table}.csv"  # ty: ignore
    table_local_paths[table] = table_local_path

print(f"{time.time() - unzip_time:.3f} seconds elapsed to unzip table.")
print()

# %%

# create a plan for reading in data via polars

write_time = time.time()

print("Reading in table and writing to deltalake...")

SQL_TO_POLARS_DTYPE = {
    "bigint": pl.Int64,
    "integer": pl.Int32,
    "smallint": pl.Int16,
    "real": pl.Float32,
    "double precision": pl.Float64,
    "numeric": pl.Decimal,
    "boolean": pl.Boolean,
    "text": pl.String,
    "varchar": pl.String,
    "character varying": pl.String,
    "date": pl.Date,
    "timestamp without time zone": pl.Datetime,
    "timestamp with time zone": pl.Datetime,
    "user-defined": pl.String,
}


def sql_to_polars_dtype(sql_type: str) -> pl.datatypes.DataType:
    """
    Convert a SQL dtype string to a Polars dtype.
    Raises ValueError if the dtype is not recognized.
    """
    sql_type = sql_type.strip().lower()
    # handle e.g. 'character varying(255)'
    if "(" in sql_type:
        sql_type = sql_type.split("(")[0].strip()
    if sql_type not in SQL_TO_POLARS_DTYPE:
        valid = ", ".join(sorted(SQL_TO_POLARS_DTYPE))
        raise ValueError(
            f"Unrecognized SQL dtype: {sql_type!r}. Valid options: {valid}"
        )
    return SQL_TO_POLARS_DTYPE[sql_type]


def build_polars_schema(schema_df, string_boolean_columns=None):
    """
    Given a DataFrame with columns ['field', 'dtype'],
    return a dict usable as a Polars schema.

    string_boolean_columns: list of column names that should be treated as strings
    first (because they contain "t"/"f" instead of true boolean values)
    """
    schema = {}
    for row in schema_df.itertuples(index=False):
        if (
            row.dtype.strip().lower() == "boolean"
            and string_boolean_columns is not None
            and row.field in string_boolean_columns
        ):
            # Read as string first, we'll convert later
            schema[row.field] = pl.String
        else:
            schema[row.field] = sql_to_polars_dtype(row.dtype)
    return schema


# decoder for WKB point columns, if necessary
# TODO int32 is hard-coded here, make more flexible
def decoder(x: str) -> np.ndarray[np.int32]:
    point = wkb.loads(bytes.fromhex(x))
    out = np.array([point.x, point.y, point.z], dtype=np.int32)
    return out


def id_partition_func(
    id_to_encode: int,
    n_partitions: int = 256,
    use_seg_id: bool = False,
    cv: CloudVolume = None,
) -> np.uint16:
    if id_to_encode == 0:
        return np.uint16(0)
    if use_seg_id:
        id_to_encode = cv.meta.decode_segid(id_to_encode)

    # salt = 123456
    # partition = hash(id_to_encode ^ salt) % n_partitions
    # partition = ((id_to_encode * 2654435761) & 0xFFFFFFFF) % n_partitions

    partition = id_to_encode % n_partitions
    return np.uint16(partition)


# %%
def scan_csv_with_header(table_path, header_path) -> pl.LazyFrame:
    header = pd.read_csv(header_path, header=None).rename(
        columns={0: "field", 1: "dtype"}
    )
    print(header)

    # Track which columns were boolean in the original schema
    boolean_string_columns = [
        row.field
        for row in header.itertuples(index=False)
        if row.dtype.strip().lower() == "boolean"
    ]

    schema = build_polars_schema(header, string_boolean_columns=boolean_string_columns)

    table = pl.scan_csv(table_path, has_header=False, schema=schema).drop(
        DROP_COLUMNS, strict=False
    )

    # Convert the string boolean columns to actual booleans
    if boolean_string_columns:
        table = table.with_columns(
            [
                pl.when(pl.col(col) == "t")
                .then(True)
                .when(pl.col(col) == "f")
                .then(False)
                .otherwise(None)  # Handle any other values as null
                .alias(col)
                for col in boolean_string_columns
                if col
                in table.collect_schema().names()  # Only process columns that exist after dropping
            ]
        )

    schema = table.collect_schema()

    print("Reading in table with schema:")
    for key, val in schema.items():
        print(f"{key}: {val}")
    print()

    return table


table = scan_csv_with_header(
    table_local_paths[table_name], header_local_paths[table_name]
)

table.collect()


# %%

if has_segmentation:
    seg_table = scan_csv_with_header(
        table_local_paths[segmentation_table_name],
        header_local_paths[segmentation_table_name],
    )
    table = table.join(
        seg_table,
        on="id",
        how="left",
    )


columns = table.collect_schema().names()

for partition_column in partition_columns:
    if partition_column not in columns:
        raise ValueError(
            f"Partition column {partition_column!r} not found in table columns: {columns}"
        )


# %%

# intended to only catch unpacked point columns
position_columns = [c for c in columns if (c.endswith("pt_position"))]
print(f"Found position columns: {position_columns}")
if len(position_columns) > 0:
    print(f"Decoding {len(position_columns)} position columns...")
    table = table.with_columns(
        pl.col(position_columns).map_elements(decoder, return_dtype=pl.List(pl.Int32))
    )

# %%
use_seg_id = False
if use_seg_id:
    client = CAVEclient(datastack, version=version)
    cv = client.info.segmentation_cloudvolume()
else:
    cv = None

partial_id_partition_func = partial(
    id_partition_func,
    n_partitions=n_partitions,
    use_seg_id=use_seg_id,
    cv=cv,
)

partition_by = f"{partition_column}_partition"

table = table.with_columns(
    pl.col(partition_column)
    .map_elements(
        partial_id_partition_func,
        return_dtype=pl.UInt16,
    )
    .alias(partition_by)
)

write_mode = "append"
unfinished = True

start = 0
while unfinished:
    chunk_table = table.slice(start, n_rows_per_chunk).collect()

    # Process the chunk...
    # If the chunk is empty, we're done
    if chunk_table.is_empty():
        unfinished = False
    else:
        print(f"Writing chunk for rows {start:,} to {start + n_rows_per_chunk:,}...")
        write_deltalake(
            out_path,
            chunk_table,
            partition_by=partition_by,
            mode=write_mode,
        )
        start += n_rows_per_chunk

print(f"{time.time() - write_time:.3f} seconds elapsed to read and write table.")
print()

# %%

# delete the temporary files

delete_time = time.time()

print("Cleaning up temporary files...")
for table in table_names:
    subprocess.run(["rm", str(table_local_paths[table])])
    subprocess.run(["rm", str(header_local_paths[table])])
print(f"{time.time() - delete_time:.3f} seconds elapsed to delete temporary files.")
print()

# %%
# optimize the deltalake with z-ordering and bloom filters

optimize_time = time.time()

print("Optimizing deltalake...")
if len(bloom_filter_columns) > 0:
    bloom = BloomFilterProperties(
        set_bloom_filter_enabled=True,
        fpp=fpp,
    )
    column_properties = ColumnProperties(bloom_filter_properties=bloom)
    writer_properties = WriterProperties(
        column_properties={col: column_properties for col in bloom_filter_columns}
    )
else:
    writer_properties = None


dt = DeltaTable(out_path)
to = TableOptimizer(dt)
to.z_order(columns=zorder_columns, writer_properties=writer_properties)
dt.vacuum(dry_run=False, retention_hours=0, enforce_retention_duration=False, full=True)

print(f"{time.time() - optimize_time:.3f} seconds elapsed to optimize deltalake.")
print()

print("Done!")
print("-----------------")
print(f"{time.time() - total_time:.3f} seconds elapsed total.")
print("-----------------")
