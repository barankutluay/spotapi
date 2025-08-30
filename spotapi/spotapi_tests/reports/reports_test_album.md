### Album Initialization

| Metric | Value |
|--------|-------|
| Album ID | testid |
| Album Link | https://open.spotify.com/album/testid |
| Base Client | BaseClient |

### Album Query Structure

| Metric | Value |
|--------|-------|
| operationName | str |
| variables | str |
| extensions | str |

_validate_response accepted a valid mapping.

_validate_response raised AlbumError for invalid response.

### Get Album Info

| Metric | Value |
|--------|-------|
| Tracks Count | 0 |

get_album_info raised AlbumError on failure response.

### Integration Album Info

| Metric | Value |
|--------|-------|
| Tracks Count | 10 |

Integration pagination yielded 1 batch(es).

### Paginate Album Batches

| Metric | Value |
|--------|-------|
| Number of Batches | 3 |

