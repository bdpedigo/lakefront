# %%
import io
import os
import shutil
import time
import zipfile
from io import StringIO
from pathlib import Path

import lance
import numpy as np
import pandas as pd
import polars as pl
import pyvista as pv
from cloudfiles import CloudFiles
from deltalake import DeltaTable, WriterProperties, write_deltalake
from deltalake.table import TableOptimizer
from scipy.sparse import csr_array
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import AgglomerativeClustering
from sklearn.neighbors import kneighbors_graph
from tqdm.auto import tqdm

from meshmash import edges_to_lines

path = "gs://iarpa_microns/minnie/minnie65/embeddings_m943/segclr_nm_coord_public_offset_csvzips"

cf = CloudFiles(path)

max_shards = 50_000

base_local_path = Path("/Users/ben.pedigo/code/meshrep/meshrep/data/")
raw_delta_out_path = base_local_path / "raw_segclr_deltalake"
lance_out_path = base_local_path / "segclr_lance"
delta_out_path = base_local_path / "condensed_segclr_deltalake"

# %%

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


# %%


writer_properties = WriterProperties(compression="SNAPPY")

clear = True
if clear:
    if delta_out_path.exists():
        shutil.rmtree(delta_out_path)
    if lance_out_path.exists():
        shutil.rmtree(lance_out_path)
    if raw_delta_out_path.exists():
        shutil.rmtree(raw_delta_out_path)


FEATURE_COLS = [f"{i}" for i in range(N_DIMENSIONS)]

# These are the main hyperparams to tune in terms of how much compression
# lower threshold means more clusters means less compression
# linkage is the clustering func - ward tries to minimize variance within clusters,
# complete minimizes the maximum difference between points in a cluster which sounded
# appealing but wasn't as visually compelling as I had hoped. both worth playing with
distance_threshold = 60
linkage = "ward"

n_test_shards = 8
infos = []
zipped_n_bytes = 0
for shard in tqdm(range(n_test_shards)):
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
            raw_delta_out_path / "all_raw_embeddings",
            all_raw_embeddings,
            partition_by=["shard"],
            mode="append",
            writer_properties=writer_properties,
        )
        info["raw_deltalake_write_time"] = time.time() - timer

        timer = time.time()
        write_deltalake(
            delta_out_path / "condensed_embeddings",
            all_condensed_embeddings,
            partition_by=["shard"],
            mode="append",
            writer_properties=writer_properties,
        )
        write_deltalake(
            delta_out_path / "condensation_maps",
            all_condensation_maps,
            partition_by=["shard"],
            mode="append",
            writer_properties=writer_properties,
        )
        info["deltalake_write_time"] = time.time() - timer

        timer = time.time()
        lance.write_dataset(
            all_condensed_embeddings.to_arrow(),
            lance_out_path,
            mode="append",
        )
        info["lance_write_time"] = time.time() - timer

        infos.append(info)

# %%


def measure_directory_size(path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


raw_delta_n_bytes = measure_directory_size(raw_delta_out_path)
delta_n_bytes = measure_directory_size(delta_out_path)
lance_n_bytes = measure_directory_size(lance_out_path)

sizes = {
    "zipped_csv": zipped_n_bytes,
    "raw_delta": raw_delta_n_bytes,
    "condensed_delta": delta_n_bytes,
    "condensed_lance": lance_n_bytes,
}

size_df = pl.DataFrame([sizes])
# size_df = size_df.melt(var_name="format", value_name="size_bytes")
size_df = size_df.unpivot(variable_name="format", value_name="size_bytes")
size_df
# %%
import seaborn as sns

sns.barplot(
    data=size_df,
    x="format",
    y="size_bytes",
)

# %%
import matplotlib.pyplot as plt
import seaborn as sns

# multiply each value by 50000 / n_test_shards to project the size to the full dataset
size_df = size_df.with_columns(
    (pl.col("size_bytes") * (max_shards / n_test_shards) / (1024**3)).alias(
        "projected_size_gigabytes"
    )
)

sns.set_context("talk")
fig, ax = plt.subplots(figsize=(8, 6))
sns.barplot(
    data=size_df,
    x="format",
    y="projected_size_gigabytes",
    ax=ax,
)


for i, row in enumerate(size_df.rows(named=True)):
    ax.text(
        i,
        row["projected_size_gigabytes"],
        f"{int(row['projected_size_gigabytes']):,} GB",
        ha="center",
        va="bottom",
    )

ax.spines[["top", "right"]].set_visible(False)

xticklabels = ax.get_xticklabels()
new_labels = []
for label in xticklabels:
    new_label = label.get_text().replace("_", "\n").capitalize()
    new_labels.append(new_label)
ax.set_xticks(ax.get_xticks())
ax.set_xticklabels(new_labels)

ax.set(xlabel="Format", ylabel="Projected size (GB)")

# %%
info_df = pl.DataFrame(infos)
info_df

# %%

# write_deltalake(
#     delta_out_path / "condensed_embeddings",
#     all_condensed_embeddings,
#     partition_by=["shard"],
#     mode="append",
#     writer_properties=writer_properties,
# )


# from deltalake.schema import ArrayType, Field, PrimitiveType, Schema

# schema = Schema(
#     [
#         Field("embedding", ArrayType(PrimitiveType("float"))),
#         Field("x", PrimitiveType("float")),
#         Field("y", PrimitiveType("float")),
#         Field("z", PrimitiveType("float")),
#         Field("root_id", PrimitiveType("UInt64")),
#         # Field("shard", PrimitiveType("UInt32")),
#     ]
# )


# # DeltaTable.create(delta_out_path / "condensed_embeddings", schema=schema)

pl.scan_delta(delta_out_path / "condensed_embeddings").collect_schema()
pl.scan_delta(delta_out_path / "condensed_embeddings").limit(5).collect()

# %%
pl.scan_delta(delta_out_path / "condensation_maps").collect()


# %%
writer_properties = WriterProperties(
    compression="zstd",  # column_properties={"root_id": }
)
zorder = ["root_id"]
dt = DeltaTable(delta_out_path)
to = TableOptimizer(dt)
to.z_order(columns=zorder)
dt.vacuum(dry_run=False, retention_hours=0, enforce_retention_duration=False)

# %%
all_condensed_embeddings = pl.scan_delta(delta_out_path / "condensed_embeddings")
all_condensation_maps = pl.scan_delta(delta_out_path / "condensation_maps")

# %%
all_condensed_embeddings.filter(pl.col("shard") == 1).group_by("root_id").having(
    pl.len() > 100, pl.len() < 1000
).agg(pl.len()).collect()

# %%
root_id = 864691135700227874
# root_id = 864691136723070574
shard = 1

condensation_map = all_condensation_maps.filter(
    (pl.col("root_id") == root_id) & (pl.col("shard") == shard)
).collect()


points = condensation_map.select(["x", "y", "z"]).to_numpy()
graph = construct_knn_graph(points, n_neighbors=3)
edges = np.stack(graph.nonzero()).T

labels = condensation_map["condensed_id"].to_numpy()


def shuffle_labels(labels):
    labels = np.array(labels)
    unique_labels = np.unique(labels)
    shuffled_labels = np.random.permutation(unique_labels)
    label_mapping = dict(zip(unique_labels, shuffled_labels))
    new_labels = np.array([label_mapping[label] for label in labels])
    return new_labels


lines = edges_to_lines(edges)

poly = pv.PolyData(points, lines=lines)


plotter = pv.Plotter()
plotter.add_points(
    points,
    scalars=shuffle_labels(labels),
    point_size=10,
    render_points_as_spheres=True,
    cmap="glasbey_light",
    show_scalar_bar=False,
)
plotter.add_mesh(poly, color="black", line_width=0.5)
plotter.camera.focal_point = np.array([194602, 123561, 19649]) * np.array([4, 4, 40])
plotter.enable_fly_to_right_click()
plotter.show()


# %%

from caveclient import CAVEclient

client = CAVEclient("minnie65_phase3_v1")
cv = client.info.segmentation_cloudvolume()
mesh = cv.mesh.get(root_id)[root_id]
mesh = (mesh.vertices, mesh.faces)

# %%


from sklearn.decomposition import PCA

pca = PCA(n_components=32)
# points = raw_embeddings[["x", "y", "z"]].values
graph = construct_knn_graph(points, n_neighbors=3)

timer = time.time()
# features = raw_embeddings[FEATURE_COLS].values
# features = pca.fit_transform(features)
labels = connectivity_agglomeration(
    features, graph, distance_threshold=0.008, linkage="complete", metric="cosine"
)
# labels = connectivity_agglomeration(
#     features, graph, distance_threshold=60, linkage="ward"
# )
condensed_embeddings = summarize_condensation(features, points, labels, root_id, shard)

print(len(np.unique(labels)) / features.shape[0])

# %%
labels = shuffle_labels(labels)

# clustering = AgglomerativeClustering(
#     connectivity=graph, distance_threshold=100, linkage="ward", n_clusters=None
# )
# labels = clustering.fit_predict(features)

edges = np.stack(graph.nonzero()).T

lines = edges_to_lines(edges)


pv.set_plot_theme("default")
# pv.global_theme.lighting_params.ambient = 0.35
# pv.global_theme.smooth_shading = True
# pv.global_theme.show_scalar_bar = False


poly = pv.PolyData(points, lines=lines)

plotter = pv.Plotter()
plotter.add_points(
    points,
    scalars=labels.astype(float),
    point_size=20,
    render_points_as_spheres=True,
    cmap="tab20",
)
plotter.add_mesh(poly, color="black", line_width=0.5)
plotter.add_mesh(pv.make_tri_mesh(*mesh), color="grey", opacity=0.3)
# plotter.camera.focal_point = np.array([194602, 123561, 19649]) * np.array([4, 4, 40])
# plotter.camera.focal_point = np.array([158890, 193263, 16667]) * np.array([4, 4, 40])
plotter.camera.focal_point = np.array([148200, 150414, 15025]) * np.array([4, 4, 40])
plotter.enable_fly_to_right_click()
plotter.show()

# plotter.export_html("segclr_agglomeration.html")

# %%
plotter.camera.focal_point / np.array([4, 4, 40])


# %%

import matplotlib.pyplot as plt
import seaborn as sns
from umap import UMAP

# mean_features = pd.DataFrame(features).groupby(labels).mean()

# umap = UMAP(n_components=2)
# mean_umap = umap.fit_transform(mean_features)

# #%%
# fig, ax = plt.subplots(figsize=(6, 6))
# sns.scatterplot(x=mean_umap[:, 0], y=mean_umap[:, 1], ax=ax, s=1)

# %%

mean_features = np.stack(
    condensed_embeddings.select("embedding").to_series().to_list(), axis=0
)

mean_features.shape
# %%
mean_info = condensed_embeddings.to_pandas()
mean_info = raw_embeddings
mean_features = mean_info[FEATURE_COLS].values.astype("float16")
reducer = UMAP(metric="cosine")
zs_umap = reducer.fit_transform(mean_features)
mean_info["umap0"] = zs_umap[:, 0]
mean_info["umap1"] = zs_umap[:, 1]

cluster = AgglomerativeClustering(n_clusters=20, metric="euclidean", linkage="average")
labels = cluster.fit_predict(zs_umap)
mean_info["label"] = labels

mean_umap = mean_info.groupby("label")[["umap0", "umap1"]].mean()
mean_info["dist_to_mean_umap"] = np.linalg.norm(
    mean_info[["umap0", "umap1"]].values - mean_umap.values[mean_info["label"].values],
    axis=1,
)

fig, ax = plt.subplots(figsize=(6, 6))
sns.scatterplot(
    data=mean_info,
    x="umap0",
    y="umap1",
    hue="label",
    palette="tab20",
    ax=ax,
    legend=False,
    s=3,
)
for label, (x, y) in mean_umap.iterrows():
    ax.text(x, y, str(label), fontsize=12, weight="bold", color="black")

# %%
samples = mean_info.groupby("label").sample(20)
samples = samples.sort_values("label")
samples["position"] = list(zip(samples["x"], samples["y"], samples["z"]))
samples["root_id"] = root_id
from nglui.statebuilder import ViewerState


def open_link(samples):
    client = CAVEclient("minnie65_phase3_v1", version=943)

    vs = ViewerState(client=client).add_layers_from_client()
    vs.add_points(
        samples,
        point_column="position",
        data_resolution=[1, 1, 1],
        segment_column="root_id",
        description_column="label",
    )
    vs.to_browser(browser="firefox", shorten=True)


open_link(samples)


# %%

pl.scan_delta(delta_out_path / "condensed_embeddings")

# %%
currtime = time.time()

print(f"{time.time() - currtime:.3f} seconds elapsed.")


# %%

# example = (
#     pl.scan_delta(delta_out_path)
#     .filter(pl.col("shard") == 1)
#     .slice(10900, 10901)
#     .collect()
# )
# example_embedding = example["embedding"][0]

# # %%
# pl.scan_delta(delta_out_path).filter(pl.col("shard") == 1).group_by("root_id").having(
#     pl.len() > 1000
# ).agg(pl.len()).sort("len").collect()

# %%


root_id = 864691135700227874
root_id = 864691135467234918
shard = 1
embeddings = (
    pl.scan_delta(delta_out_path)
    .with_columns(pl.col("embedding").cast(pl.Array(embedding_dtype, 128)))
    .filter(pl.col("shard") == shard, pl.col("root_id") == root_id)
    .collect()
)

# %%
N_DIMENSIONS = 128

currtime = time.time()
points = embeddings.select(["x", "y", "z"]).to_numpy()

times = {"knn": time.time() - currtime}

currtime = time.time()

embedding_vectors = np.stack(embeddings["embedding"].to_list(), dtype="float32")


times

# %%


currtime = time.time()


currtime = time.time()

connectivity_agglomeration(embedding_vectors, graph, distance_threshold=100)

print(f"{time.time() - currtime:.3f} seconds elapsed.")

# %%


# %%
print(f"{time.time() - currtime:.3f} seconds elapsed.")


# %%


# group_mean_embeddings = (
#     pl.DataFrame(embedding_vectors)
#     .with_columns(pl.Series(labels, dtype=pl.UInt32).alias("label"))
#     .group_by("label")
#     .agg(pl.all().mean())
#     .select(pl.col("label"), pl.concat_arr(pl.col(pl.Float32)).alias("embedding"))
# )

# assemble the final frame


# embeddings = embeddings.with_columns(
#     pl.Series(labels, dtype=pl.UInt32).alias("condensed_id")
# )


# condensed_embeddings = embeddings.group_by("condensed_id").agg(
#     pl.col("embedding").arr.mean(),
#     pl.col("x").mean().alias("x"),
#     pl.col("y").mean().alias("y"),
#     pl.col("z").mean().alias("z"),
# )
# condensed_embeddings = condensed_embeddings.with_columns(
#     pl.col("embedding").cast(pl.Array(embedding_dtype, 128))
# )

# %%


import time

lance_data = lance.dataset(lance_out_path)
currtime = time.time()

out = lance_data.to_table(
    nearest={"column": "embedding", "q": example_embedding, "k": 100}
)
out = pl.from_arrow(out)

print(f"{time.time() - currtime:.3f} seconds elapsed.")

# %%
plot_out = out.select(["x", "y", "z", "root_id"])
plot_out = plot_out.with_columns(pl.concat_list(["x", "y", "z"]).alias("point"))

# %%
from caveclient import CAVEclient

client = CAVEclient("minnie65_phase3_v1")
vs = ViewerState(client=client)
vs.add_layers_from_client().add_points(
    plot_out.to_pandas(),
    point_column="point",
    segment_column="root_id",
    data_resolution=[1, 1, 1],
)
vs = vs.to_browser(browser="firefox", shorten=True)


# %%

lance_data.create_index(
    "embedding",
    index_type="IVF_PQ",  # specify the IVF_PQ index type
    num_partitions=256,  # IVF
    num_sub_vectors=16,  # PQ
)

# %%

currtime = time.time()

out = lance_data.to_table(
    nearest={"column": "embedding", "q": example_embedding, "k": 100}
)
out = pl.from_arrow(out)

print(f"{time.time() - currtime:.3f} seconds elapsed.")
