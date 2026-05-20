# %%
import io
import time
import zipfile
from io import StringIO

import lance
import numpy as np
import pandas as pd
import polars as pl
import ray
from cloudfiles import CloudFile, CloudFiles
from cloudpathlib import AnyPath as Path
from deltalake import WriterProperties, write_deltalake
from scipy.sparse import csr_array
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import AgglomerativeClustering
from sklearn.neighbors import kneighbors_graph
from tqdm.auto import tqdm

input_path = "gs://iarpa_microns/minnie/minnie65/embeddings_m943/segclr_nm_coord_public_offset_csvzips"

cf = CloudFiles(input_path)

max_shards = 50_000

# TODO
base_out_path = Path("gs://bdp-ssa/segclr")
raw_delta_out_path = base_out_path / "raw_segclr_deltalake"
lance_out_path = base_out_path / "segclr_lance"
delta_out_path = base_out_path / "condensed_segclr_deltalake"
info_out = base_out_path / "info"

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


writer_properties = WriterProperties(compression="SNAPPY")

FEATURE_COLS = [f"{i}" for i in range(N_DIMENSIONS)]

# These are the main hyperparams to tune in terms of how much compression
# lower threshold means more clusters means less compression
# linkage is the clustering func - ward tries to minimize variance within clusters,
# complete minimizes the maximum difference between points in a cluster which sounded
# appealing but wasn't as visually compelling as I had hoped. both worth playing with


distance_threshold = 60
linkage = "ward"


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


def summarize_condensation(
    embedding_vectors, points, labels, root_id, shard
) -> pl.DataFrame:
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
        pl.lit(shard, dtype=pl.UInt32).alias("shard"),
    )

    return condensed_embeddings


def create_condensation_map(points, labels, root_id, shard) -> pl.DataFrame:
    condensation_map = pl.DataFrame(
        {
            "condensed_id": pl.Series(labels, dtype=pl.UInt32),
            "x": pl.Series(points[:, 0]),
            "y": pl.Series(points[:, 1]),
            "z": pl.Series(points[:, 2]),
        }
    ).with_columns(
        pl.lit(root_id, dtype=pl.UInt64).alias("root_id"),
        pl.lit(shard, dtype=pl.UInt32).alias("shard"),
    )

    return condensation_map


@ray.remote
def process_shard(shard):
    zipped_n_bytes = 0
    info = {"shard": shard}
    timer = time.time()
    back_data = cf.get(f"{shard}.zip")
    info["download_time"] = time.time() - timer

    zipped_n_bytes += len(back_data)
    info["shard_n_bytes"] = len(back_data)
    info["parsing_time"] = 0
    info["knn_time"] = 0
    info["agglomeration_time"] = 0
    info["grouping_time"] = 0
    info["condensation_map_time"] = 0

    all_raw_embeddings = []
    all_condensed_embeddings = []
    all_condensation_maps = []
    with zipfile.ZipFile(io.BytesIO(back_data)) as z:
        file_names = z.namelist()
        for name in tqdm(file_names):
            root_id = int(name.split(".")[0])
            with z.open(name) as c:
                data = c.read().decode("utf-8")
                timer = time.time()
                raw_embeddings = parse_csv_data(data)
                raw_embeddings["root_id"] = root_id
                raw_embeddings["shard"] = shard
                info["parsing_time"] += time.time() - timer

                all_raw_embeddings.append(raw_embeddings)

                timer = time.time()
                points = raw_embeddings[["x", "y", "z"]].values
                graph = construct_knn_graph(points, n_neighbors=3)
                info["knn_time"] += time.time() - timer

                if truncate_embeddings:
                    # TODO ask Sven, have been just assuming the first 64 are minnie
                    raw_embeddings = raw_embeddings.drop(
                        columns=[f"{i}" for i in range(N_DIMENSIONS)]
                    )

                # NOTE: will want to keep this if skeletons become available!
                raw_embeddings = raw_embeddings.drop(columns=["node_id"])

                timer = time.time()
                features = raw_embeddings[FEATURE_COLS].values

                labels = connectivity_agglomeration(
                    features,
                    graph,
                    distance_threshold=distance_threshold,
                )
                info["agglomeration_time"] += time.time() - timer

                timer = time.time()
                condensed_embeddings = summarize_condensation(
                    features, points, labels, root_id, shard
                )
                all_condensed_embeddings.append(condensed_embeddings)
                info["grouping_time"] += time.time() - timer

                timer = time.time()
                condensation_map = create_condensation_map(
                    points, labels, root_id, shard
                )
                all_condensation_maps.append(condensation_map)
                info["condensation_map_time"] += time.time() - timer

        timer = time.time()
        all_raw_embeddings = pd.concat(all_raw_embeddings, ignore_index=True)
        all_raw_embeddings = pl.from_pandas(all_raw_embeddings)
        all_condensed_embeddings = pl.concat(all_condensed_embeddings)
        all_condensation_maps = pl.concat(all_condensation_maps)
        info["concat_time"] = time.time() - timer

        timer = time.time()
        write_deltalake(
            str(raw_delta_out_path / "all_raw_embeddings"),
            all_raw_embeddings,
            partition_by=["shard"],
            mode="append",
            writer_properties=writer_properties,
        )
        info["raw_deltalake_write_time"] = time.time() - timer

        timer = time.time()
        write_deltalake(
            str(delta_out_path / "condensed_embeddings"),
            all_condensed_embeddings,
            partition_by=["shard"],
            mode="append",
            writer_properties=writer_properties,
        )
        write_deltalake(
            str(delta_out_path / "condensation_maps"),
            all_condensation_maps,
            partition_by=["shard"],
            mode="append",
            writer_properties=writer_properties,
        )
        info["deltalake_write_time"] = time.time() - timer

        timer = time.time()
        lance.write_dataset(
            all_condensed_embeddings.to_arrow(),
            str(lance_out_path),
            mode="append",
        )
        info["lance_write_time"] = time.time() - timer

    # write info out
    CloudFile(str(info_out / f"{shard}.json")).put_json(info)


def queue_shards():
    shards = list(range(max_shards))
    info_cf = CloudFiles(str(info_out))
    finished_shards = list(info_cf)
    finished_shards = [int(Path(f).stem) for f in finished_shards]
    shards_to_process = set(shards) - set(finished_shards)
    print(
        f"Total shards: {len(shards)}, Finished: {len(finished_shards)}, To process: {len(shards_to_process)}"
    )
    return list(shards_to_process)


print(max(queue_shards()))
