# %%
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO

import mmh3
import numpy as np
import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import ray
from cloudfiles import CloudFiles
from cloudpathlib import AnyPath as Path
from scipy.sparse import csr_array
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import AgglomerativeClustering
from sklearn.neighbors import kneighbors_graph
from tqdm.auto import tqdm

INPUT_PATH = "gs://iarpa_microns/minnie/minnie65/embeddings_m943/segclr_nm_coord_public_offset_csvzips"


INPUT_N_SHARDS = 50_000


truncate_embeddings = True
ORIGINAL_N_DIMENSIONS = 128
if truncate_embeddings:
    N_DIMENSIONS = 64
else:
    N_DIMENSIONS = 128

embedding_dtype = "float32"
pl_embedding_dtype = pl.Float32
point_dtype = "float32"


column_names = ["node_id", "x", "y", "z"] + [
    f"{i}" for i in range(ORIGINAL_N_DIMENSIONS)
]
dtypes = {
    "node_id": "uint64",
    "x": point_dtype,
    "y": point_dtype,
    "z": point_dtype,
}
dtypes.update({f"{i}": embedding_dtype for i in range(ORIGINAL_N_DIMENSIONS)})

FEATURE_COLS = [f"{i}" for i in range(N_DIMENSIONS)]

# These are the main hyperparams to tune in terms of how much compression
# lower threshold means more clusters means less compression
# linkage is the clustering func - ward tries to minimize variance within clusters,
# complete minimizes the maximum difference between points in a cluster which sounded
# appealing but wasn't as visually compelling as I had hoped. both worth playing with
distance_threshold = 50
linkage = "ward"

BASE_OUT_PATH = Path("gs://bdp-ssa/segclr")


def mmh3_shard(
    segment_id: int, n_shards: int, byteorder: str = "little", bytewidth: int = 8
) -> int:
    segment_id_bytes = segment_id.to_bytes(bytewidth, byteorder)
    h1, h2 = mmh3.hash64(segment_id_bytes, signed=False)  # two 64-bit halves
    hash_value = h1 ^ h2  # XOR fold into single 64-bit value
    return hash_value % n_shards


def parse_csv_data(data) -> pd.DataFrame:
    embeddings = pd.read_csv(
        StringIO(data), header=None, engine="c", names=column_names, dtype=dtypes
    )

    return embeddings


def construct_knn_graph(points, n_neighbors=3) -> csr_array:
    if points.shape[0] <= n_neighbors:
        # If there are fewer points than n_neighbors, connect all points to each other
        graph = np.ones((points.shape[0], points.shape[0]), dtype=bool)
        np.fill_diagonal(graph, 0)  # Remove self-connections
        return csr_array(graph)
    graph = kneighbors_graph(points, n_neighbors=n_neighbors)
    graph = graph.maximum(graph.T)  # make sure the graph is symmetric
    return graph


def connectivity_agglomeration(features, graph, **kwargs) -> np.ndarray:
    kwargs["n_clusters"] = None

    if features.shape[0] == 1:
        return np.array([0], dtype=np.int32)

    n_components, components = connected_components(graph, directed=False)

    all_labels = np.full(shape=features.shape[0], fill_value=-1, dtype=np.int32)
    max_label = 0
    for i in range(n_components):
        component_indices = np.where(components == i)[0]
        component_embeddings = features[component_indices]
        component_graph = graph[component_indices][:, component_indices]
        clustering = AgglomerativeClustering(connectivity=component_graph, **kwargs)
        sub_labels = clustering.fit_predict(component_embeddings)
        all_labels[component_indices] = sub_labels + max_label
        max_label += sub_labels.max() + 1  # avoid label collision between components

    assert np.array_equal(np.unique(all_labels), np.arange(max_label)), (
        "Labels are not contiguous integers starting from 0."
    )

    return all_labels


def summarize_condensation(embedding_vectors, points, labels, root_id) -> pl.DataFrame:
    # get the mean embeddings
    group_mean_embeddings = pd.DataFrame(embedding_vectors)
    group_mean_embeddings["label"] = labels
    group_mean_embeddings = group_mean_embeddings.groupby("label", sort=True).mean()
    group_mean_embeddings = pl.Series(
        name="embedding",
        values=group_mean_embeddings.values.tolist(),
        dtype=pl.Array(pl_embedding_dtype, N_DIMENSIONS),
    )

    # compute the physical centroids of the clusters
    group_centroids = pd.DataFrame(points)
    group_centroids["label"] = labels
    group_centroids = group_centroids.groupby("label", sort=True).mean()

    # find the point closest to the centroid for each cluster
    dist_to_centroids = np.linalg.norm(points - group_centroids.values[labels], axis=1)
    rep_points = pd.Series(dist_to_centroids, name="dist_to_centroid").to_frame()
    rep_points["label"] = labels
    label_rep_indices = rep_points.groupby("label", sort=True)[
        "dist_to_centroid"
    ].idxmin()
    label_rep_points = points[label_rep_indices]

    # combine
    group_rep_points = pl.DataFrame(
        {
            "x": label_rep_points[:, 0],
            "y": label_rep_points[:, 1],
            "z": label_rep_points[:, 2],
            "condensed_id": pl.Series(np.unique(labels), dtype=pl.UInt32),
        }
    )

    condensed_embeddings = pl.concat(
        [
            group_mean_embeddings.to_frame(),
            group_rep_points,
        ],
        how="horizontal",
    ).with_columns(
        pl.lit(root_id, dtype=pl.UInt64).alias("root_id"),
    )

    return condensed_embeddings


def create_condensation_map(points, labels, root_id) -> pl.DataFrame:
    condensation_map = pl.DataFrame(
        {
            "condensed_id": pl.Series(labels, dtype=pl.UInt32),
            "x": pl.Series(points[:, 0]),
            "y": pl.Series(points[:, 1]),
            "z": pl.Series(points[:, 2]),
        }
    ).with_columns(
        pl.lit(root_id, dtype=pl.UInt64).alias("root_id"),
    )

    return condensation_map


def get_embeddings(shard: int) -> dict[int, pd.DataFrame]:
    cf = CloudFiles(INPUT_PATH)

    back_data = cf.get(f"{shard}.zip")

    all_raw_embeddings = {}
    with zipfile.ZipFile(io.BytesIO(back_data)) as z:
        file_names = z.namelist()
        for name in tqdm(file_names, disable=True):
            root_id = int(name.split(".")[0])
            with z.open(name) as c:
                data = c.read().decode("utf-8")
                raw_embeddings = parse_csv_data(data)
                raw_embeddings["root_id"] = root_id
                raw_embeddings["shard"] = shard

                if truncate_embeddings:
                    # TODO ask Sven, have been just assuming the first 64 are minnie
                    raw_embeddings = raw_embeddings.drop(
                        columns=[
                            f"{i}" for i in range(N_DIMENSIONS, ORIGINAL_N_DIMENSIONS)
                        ]
                    )

                # NOTE: will want to keep this if skeletons become available!
                raw_embeddings = raw_embeddings.drop(columns=["node_id"])

                all_raw_embeddings[root_id] = raw_embeddings

    return all_raw_embeddings


def process_embeddings(
    raw_embeddings_by_root: dict[int, pd.DataFrame],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    all_condensed_embeddings = []
    all_condensation_maps = []

    for root_id, raw_embeddings in raw_embeddings_by_root.items():
        points = raw_embeddings[["x", "y", "z"]].values
        graph = construct_knn_graph(points, n_neighbors=3)

        features = raw_embeddings[FEATURE_COLS].values
        labels = connectivity_agglomeration(
            features,
            graph,
            distance_threshold=distance_threshold,
        )

        condensed_embeddings = summarize_condensation(features, points, labels, root_id)
        all_condensed_embeddings.append(condensed_embeddings)

        condensation_map = create_condensation_map(points, labels, root_id)
        all_condensation_maps.append(condensation_map)

    all_condensed_embeddings = pl.concat(all_condensed_embeddings)
    all_condensation_maps = pl.concat(all_condensation_maps)

    return all_condensed_embeddings, all_condensation_maps


# %%


# --- Pipeline config ---
BATCH_SIZE = 8  # input shards per worker task
N_OUTPUT_SHARDS = 32  # coarse output bucketing for parquet writes
EMBEDDINGS_OUT = str(BASE_OUT_PATH / "temp_condensed_embeddings")
MAPS_OUT = str(BASE_OUT_PATH / "temp_condensation_maps")
CHECKPOINT_PATH = str(BASE_OUT_PATH / "temp_checkpoints")


def compute_output_shard(table: pa.Table, n_output_shards: int) -> pa.Array:
    """Hash root_id to assign each row to an output shard."""
    root_ids = table.column("root_id").to_pylist()
    shards = [mmh3_shard(rid, n_shards=n_output_shards) for rid in root_ids]
    return pa.array(shards, type=pa.int32())


def batch_key(input_shards: list[int]) -> str:
    """Deterministic short hash of the input shard set."""
    payload = ",".join(str(s) for s in sorted(input_shards))
    h1, h2 = mmh3.hash64(payload.encode(), signed=False)
    return f"{(h1 ^ h2):016x}"


@ray.remote(num_cpus=1, memory=8 * 1024**3)
def process_and_write_batch(input_shards: list[int]) -> int:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logger = logging.getLogger(__name__)

    bkey = batch_key(input_shards)
    n_shards = len(input_shards)
    logger.info(f"[{bkey}] Starting batch: shards={input_shards}")

    # Fan out GCS downloads with threads (I/O-bound)
    with ThreadPoolExecutor(max_workers=len(input_shards)) as pool:
        futures = {pool.submit(get_embeddings, s): s for s in input_shards}
        raw_data = {}
        for i, f in enumerate(as_completed(futures), 1):
            shard = futures[f]
            raw_data[shard] = f.result()
            logger.info(f"[{bkey}] Downloaded shard {shard} ({i}/{n_shards})")

    # Process each shard's embeddings (CPU-bound, sequential)
    all_embeddings = []
    all_maps = []
    for i, (shard, embeddings_by_root) in enumerate(raw_data.items(), 1):
        emb, maps = process_embeddings(embeddings_by_root)
        all_embeddings.append(emb.to_arrow())
        all_maps.append(maps.to_arrow())
        logger.info(f"[{bkey}] Processed shard {shard} ({i}/{n_shards})")

    all_embeddings = pa.concat_tables(all_embeddings)
    all_maps = pa.concat_tables(all_maps)

    # Compute output shard assignments once
    emb_output_shards = compute_output_shard(all_embeddings, N_OUTPUT_SHARDS)
    map_output_shards = compute_output_shard(all_maps, N_OUTPUT_SHARDS)

    # Partition by output shard and write to GCS
    out_cf_emb = CloudFiles(EMBEDDINGS_OUT)
    out_cf_maps = CloudFiles(MAPS_OUT)

    n_files_written = 0
    for output_shard in range(N_OUTPUT_SHARDS):
        mask = pa.compute.equal(emb_output_shards, output_shard)
        emb_partition = all_embeddings.filter(mask)
        if emb_partition.num_rows > 0:
            buf = pa.BufferOutputStream()
            pq.write_table(emb_partition, buf)
            out_cf_emb.put(
                f"output_shard={output_shard}/batch_{bkey}.parquet",
                buf.getvalue().to_pybytes(),
            )
            n_files_written += 1

        map_mask = pa.compute.equal(map_output_shards, output_shard)
        map_partition = all_maps.filter(map_mask)
        if map_partition.num_rows > 0:
            buf = pa.BufferOutputStream()
            pq.write_table(map_partition, buf)
            out_cf_maps.put(
                f"output_shard={output_shard}/batch_{bkey}.parquet",
                buf.getvalue().to_pybytes(),
            )
            n_files_written += 1

    logger.info(
        f"[{bkey}] Wrote {n_files_written} parquet files across {N_OUTPUT_SHARDS} output shards"
    )

    # Checkpoint: mark input shards as complete
    cf = CloudFiles(CHECKPOINT_PATH)
    for s in input_shards:
        cf.put_json(f"{s}.json", {"input_shard": s, "batch_key": bkey})

    logger.info(f"[{bkey}] Done. Checkpointed {n_shards} shards.")
    return len(input_shards)


# --- Driver: orchestration only, no data ---


def get_shards_to_process(total_shards: int) -> list[int]:
    all_shards = list(range(total_shards))
    cf = CloudFiles(CHECKPOINT_PATH)
    finished = [int(Path(f).stem) for f in cf.list()]
    remaining = sorted(set(all_shards) - set(finished))
    print(
        f"Total: {len(all_shards)}, Finished: {len(finished)}, Remaining: {len(remaining)}"
    )
    return remaining


def queue_shard_batches() -> list[list[int]]:
    shards_to_process = get_shards_to_process(INPUT_N_SHARDS)
    return [
        shards_to_process[i : i + BATCH_SIZE]
        for i in range(0, len(shards_to_process), BATCH_SIZE)
    ]


def queue_shard_batches_test() -> list[list[int]]:
    shards_to_process = get_shards_to_process(INPUT_N_SHARDS)
    return [
        shards_to_process[i : i + BATCH_SIZE]
        for i in range(0, len(shards_to_process), BATCH_SIZE)
    ][0:1]
