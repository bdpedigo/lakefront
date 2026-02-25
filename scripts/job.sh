#!/bin/bash
# Script to run job on the Ray cluster

export DATASTACK="v1dd"
export VERSION="1196"
export TABLE_NAME="synapses_v1dd"
export PARTITION_COLUMNS="post_pt_root_id"
export N_PARTITIONS="256"
export ZORDER_COLUMNS="post_pt_root_id,id"
export BLOOM_FILTER_COLUMNS="id"
export FPP="0.001"
export N_ROWS_PER_CHUNK="1000000000"
export OUT_PATH="gs://allen-minnie-phase3/mat_deltalakes/v1dd/v1196/synapses_v1dd_deltalake/partition_by_post"

uv run python scratch/table_to_deltalake.py