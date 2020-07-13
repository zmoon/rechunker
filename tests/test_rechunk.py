import pytest

import zarr
import dask.array as dsa

from rechunker import api


_DIMENSION_KEY = "_ARRAY_DIMENSIONS"


@pytest.fixture(params=[(8000, 200), {"y": 8000, "x": 200}])
def target_chunks(request):
    return request.param


@pytest.mark.parametrize("shape", [(8000, 8000)])
@pytest.mark.parametrize("source_chunks", [(200, 8000)])
@pytest.mark.parametrize("dtype", ["f4"])
@pytest.mark.parametrize("max_mem", [25600000])
@pytest.mark.parametrize(
    "dims,target_chunks",
    [
        (None, (8000, 200)),
        # would be nice to support this syntax eventually
        pytest.param(None, (-1, 200), marks=pytest.mark.xfail),
        (["y", "x"], (8000, 200)),
        (["y", "x"], {"y": 8000, "x": 200}),
        # can't infer missing dimension chunk specification
        pytest.param(["y", "x"], {"x": 200}, marks=pytest.mark.xfail),
        # can't use dict syntax without array dims
        pytest.param(None, {"y": 8000, "x": 200}, marks=pytest.mark.xfail),
    ],
)
def test_rechunk_array(
    tmp_path, shape, source_chunks, dtype, dims, target_chunks, max_mem
):

    ### Create source array ###
    store_source = str(tmp_path / "source.zarr")
    source_array = zarr.ones(
        shape, chunks=source_chunks, dtype=dtype, store=store_source
    )
    # add some attributes
    source_array.attrs["foo"] = "bar"
    if dims:
        source_array.attrs[_DIMENSION_KEY] = dims

    ### Create targets ###
    target_store = str(tmp_path / "target.zarr")
    temp_store = str(tmp_path / "temp.zarr")

    delayed = api.rechunk(
        source_array, target_chunks, max_mem, target_store, temp_store=temp_store
    )

    target_array = zarr.open(target_store)

    if isinstance(target_chunks, dict):
        target_chunks_list = [target_chunks[d] for d in dims]
    else:
        target_chunks_list = target_chunks
    assert target_array.chunks == tuple(target_chunks_list)
    assert dict(source_array.attrs) == dict(target_array.attrs)

    delayed.compute()
    a_tar = dsa.from_zarr(target_array)
    assert dsa.equal(a_tar, 1).all().compute()


def test_rechunk_group(tmp_path):
    store_source = str(tmp_path / "source.zarr")
    group = zarr.group(store_source)
    group.attrs['foo'] = 'bar'
    # 800 byte chunks
    a = group.ones('a', shape=(5, 10, 20), chunks=(1, 10, 20), dtype='f4')
    a.attrs['foo'] = 'bar'
    b = group.ones('b', shape=(20,), chunks=(10,), dtype='f4')
    b.attrs['foo'] = 'bar'

    target_store = str(tmp_path / "target.zarr")
    temp_store = str(tmp_path / "temp.zarr")

    max_mem = 1600 # should force a two-step plan for a
    target_chunks = {'a': (5, 10, 4), 'b': (20,)}

    delayed = api.rechunk(
        group, target_chunks, max_mem, target_store, temp_store=temp_store
    )

    target_group = zarr.open(target_store)
    assert 'a' in target_group
    assert 'b' in target_group
    assert dict(group.attrs) == dict(target_group.attrs)
