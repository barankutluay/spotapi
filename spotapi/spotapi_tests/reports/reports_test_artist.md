### Artist Initialization

| Metric | Value |
|--------|-------|
| Requires Login | False |
| Base Client | BaseClient |

### Query Artists

| Metric | Value |
|--------|-------|
| Artists Count | 0 |

query_artists raised ArtistError on failure response.

### Get Artist

| Metric | Value |
|--------|-------|
| Artist Name | Test Artist |

get_artist raised ArtistError on failure response.

### Paginate Artists Single Page

| Metric | Value |
|--------|-------|
| Batches | 1 |

### Paginate Artists Multiple Pages

| Metric | Value |
|--------|-------|
| Number of Batches | 2 |

_do_follow success and failure branches tested.

Follow and unfollow methods executed successfully.

Follow/unfollow raised ValueError when login required.

### Integration Artist Info

| Metric | Value |
|--------|-------|
| Artists Count | 10 |

Integration pagination yielded 1 batch(es).

